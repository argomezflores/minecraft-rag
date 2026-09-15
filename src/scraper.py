"""
scraper.py — Descarga artículos de la Minecraft Wiki vía API MediaWiki.

Concepto RAG: la fuente de nuestro corpus. En vez de PDFs, ahora bajamos
wikitext plano usando la API oficial de MediaWiki (https://minecraft.wiki/api.php).

¿Por qué wikitext y no HTML renderizado?
- El wikitext es texto plano con marcado simple ({{templates}}, [[links]], etc.).
- Con mwparserfromhell lo limpiamos a texto legible en 2 líneas.
- HTML renderizado tiene mucho ruido (menús, sidebars, scripts).

¿Por qué mwclient y no requests puro?
- mwclient maneja la paginación, rate limiting, y errores 429 automáticamente.
- API MediaWiki es incómoda a mano (múltiples params, formato JSON anidado).
- 30 líneas menos de código que reinventar.
"""

import time
from pathlib import Path
from typing import Iterator, NamedTuple

import mwclient
import mwparserfromhell

from src.config import WIKI_API_URL, WIKI_USER_AGENT


class WikiArticle(NamedTuple):
    title: str        # ej. "Diamond Pickaxe"
    category: str     # ej. "Items"
    url: str          # ej. https://minecraft.wiki/w/Diamond_Pickaxe
    text: str         # wikitext limpio (sin templates ni HTML)


# 📚 Delay entre requests (segundos). Etiqueta de la wiki: 1-2s es respetuoso.
RATE_LIMIT_DELAY = 1.0


def _get_site() -> mwclient.Site:
    """Cliente MediaWiki configurado con User-Agent identificable (requerido)."""
    # 📚 WIKI_API_URL viene como https://minecraft.wiki/api.php
    # mwclient necesita el host separado del path.
    from urllib.parse import urlparse

    parsed = urlparse(WIKI_API_URL)
    return mwclient.Site(
        parsed.netloc,
        path=parsed.path.rsplit("/", 1)[0] + "/",
        scheme=parsed.scheme,
        clients_useragent=WIKI_USER_AGENT,
    )


# 📚 Slots posibles en templates {{Crafting}} de la wiki:
# 3x3 grid con letras A/B/C (columnas) y números 1/2/3 (filas).
# Ejemplo: A1=top-left, C3=bottom-right, B2=center.
_CRAFTING_SLOTS = [f"{col}{row}" for row in "123" for col in "ABC"]


def _template_param(template, name: str) -> str:
    """Extrae un parámetro de un template como texto limpio, o '' si no existe."""
    if not template.has(name):
        return ""
    return str(template.get(name).value.strip_code()).strip()


def _convert_crafting_template(template) -> str:
    """
    Convierte {{Crafting|A1=X|B1=Y|...|Output=Z}} → frase legible.

    📚 Por qué esto: mwparserfromhell.strip_code() borra el template entero.
    Nuestro texto "limpio" quedaba sin las recetas. Este pre-procesamiento
    las convierte a lenguaje natural que sí sobrevive el strip.
    """
    # Recolectamos los slots ocupados en orden de lectura (A1, B1, C1, A2, ...).
    ingredients = []
    for slot in _CRAFTING_SLOTS:
        item = _template_param(template, slot)
        if item:
            ingredients.append(item)

    if not ingredients:
        return ""  # Template vacío, dejamos que strip_code lo elimine.

    output = _template_param(template, "Output") or "unknown item"
    shapeless = _template_param(template, "Shapeless").lower() in {"1", "yes", "true"}

    if shapeless:
        return f"Crafting recipe (shapeless): {', '.join(ingredients)} → {output}."

    return f"Crafting recipe: {', '.join(ingredients)} arranged in the crafting grid → {output}."


def _convert_smelting_template(template) -> str:
    """
    Convierte {{Smelting|Input|Output|XP|Time}} → texto.

    📚 Los parámetros posicionales en templates de MediaWiki se acceden con "1", "2", etc.
    """
    input_item = _template_param(template, "1") or _template_param(template, "Input")
    output_item = _template_param(template, "2") or _template_param(template, "Output")
    if not (input_item and output_item):
        return ""
    xp = _template_param(template, "3") or _template_param(template, "XP")
    xp_str = f", XP: {xp}" if xp else ""
    return f"Smelting recipe: {input_item} → {output_item}{xp_str}."


def _convert_brewing_template(template) -> str:
    """
    Convierte {{Brewing|Ingredient|Base|Result}} → texto.
    """
    ingredient = _template_param(template, "1") or _template_param(template, "Ingredient")
    base = _template_param(template, "2") or _template_param(template, "Base")
    result = _template_param(template, "3") or _template_param(template, "Result")
    if not (ingredient and base and result):
        return ""
    return f"Brewing recipe: {ingredient} + {base} → {result}."


# 📚 Mapa de nombres de template → función que lo convierte a texto.
# Case-insensitive: matcheamos por lowercase.
_RECIPE_CONVERTERS = {
    "crafting": _convert_crafting_template,
    "smelting": _convert_smelting_template,
    "brewing": _convert_brewing_template,
}


def _preserve_recipe_templates(wikicode) -> None:
    """
    Mutación in-place: reemplaza cada template de receta reconocido por su
    versión en texto plano. Los templates que no son recetas quedan intactos
    (los borrará strip_code() después).
    """
    for template in list(wikicode.filter_templates()):
        name = str(template.name).strip().lower()
        converter = _RECIPE_CONVERTERS.get(name)
        if converter is None:
            continue
        replacement = converter(template)
        if replacement:
            # 📚 Añadimos saltos de línea para que quede como párrafo propio.
            wikicode.replace(template, f"\n\n{replacement}\n\n")


def clean_wikitext(raw: str) -> str:
    """
    Convierte wikitext crudo en texto plano legible.

    Preserva:
      - Recetas {{Crafting}}, {{Smelting}}, {{Brewing}} — convertidas a frases.

    Elimina:
      - Templates {{Infobox item|...}} — cajas de datos que dan ruido
      - Links [[Diamond|diamond]] → "diamond" (usamos el texto visible)
      - HTML tags <ref>...</ref>
      - Categorías [[Category:Items]]
      - Comentarios <!-- ... -->
    """
    wikicode = mwparserfromhell.parse(raw)

    # 📚 ORDEN CRÍTICO: preservar recetas ANTES de strip_code(), porque
    # strip_code() borra los templates enteros sin distinguir cuáles son
    # infoboxes vs recetas. Nuestra función selectiva las convierte primero.
    _preserve_recipe_templates(wikicode)

    # 📚 strip_code() hace todo el trabajo pesado. Le pasamos normalize=True
    # para que colapse espacios múltiples.
    text = wikicode.strip_code(normalize=True, collapse=True)

    # 📚 Limpiamos líneas vacías consecutivas para que los chunks salgan más limpios.
    lines = [ln.strip() for ln in text.splitlines()]
    cleaned = []
    prev_empty = False
    for ln in lines:
        if not ln:
            if not prev_empty:
                cleaned.append("")
            prev_empty = True
        else:
            cleaned.append(ln)
            prev_empty = False

    return "\n".join(cleaned).strip()


def _process_page(page, category_label: str) -> WikiArticle | None:
    """Convierte una página de mwclient a WikiArticle (o None si no aplica)."""
    if page.namespace != 0 or page.redirect:
        return None
    try:
        raw = page.text()
    except Exception as e:
        print(f"  [skip] {page.name}: {e}")
        return None
    if len(raw) < 200:
        return None
    clean = clean_wikitext(raw)
    if len(clean) < 200:
        return None
    url = f"https://minecraft.wiki/w/{page.name.replace(' ', '_')}"
    return WikiArticle(title=page.name, category=category_label, url=url, text=clean)


def fetch_pages_by_title(
    site: mwclient.Site,
    titles: list[str],
    category_label: str = "Priority",
) -> Iterator[WikiArticle]:
    """
    Baja páginas específicas por título (fallback para páginas que no viven
    en las categorías que scrapeamos, o que quedaron cortadas por max_pages).

    📚 Diferencia con fetch_category: no navega categorías, va directo por
    nombre. Útil para asegurar cobertura de páginas críticas (Repeater, Hopper, etc.).
    """
    print(f"\n[wiki] Páginas prioritarias ({len(titles)})")
    count = 0
    for title in titles:
        try:
            page = site.pages[title]
            if not page.exists:
                print(f"  [404] {title}")
                time.sleep(RATE_LIMIT_DELAY)
                continue
        except Exception as e:
            print(f"  [FAIL] {title}: {e}")
            continue

        article = _process_page(page, category_label)
        if article is not None:
            yield article
            count += 1
        time.sleep(RATE_LIMIT_DELAY)
    print(f"  [done] {count}/{len(titles)} páginas prioritarias descargadas")


def fetch_category(
    site: mwclient.Site,
    category_name: str,
    max_pages: int = 200,
) -> Iterator[WikiArticle]:
    """
    Itera sobre las páginas de una categoría, devolviendo WikiArticles listos.

    max_pages: tope de páginas por categoría (para no bajarnos artículos triviales
    o versiones antiguas si la categoría es enorme).
    """
    print(f"\n[wiki] Categoría: {category_name}")
    try:
        category = site.categories[category_name]
    except Exception as e:
        print(f"  [FAIL] no se pudo abrir la categoría: {e}")
        return

    count = 0
    for page in category:
        if count >= max_pages:
            print(f"  [stop] alcanzamos max_pages={max_pages}")
            break

        article = _process_page(page, category_name)
        if article is None:
            time.sleep(RATE_LIMIT_DELAY)
            continue

        yield article
        count += 1

        # 📚 Respetamos rate limit para no ser bloqueados.
        time.sleep(RATE_LIMIT_DELAY)

    print(f"  [done] {count} artículos en '{category_name}'")


def safe_filename(title: str) -> str:
    """Sanea un título de wiki para uso como nombre de archivo cross-platform.

    📚 Windows prohíbe: < > : " / \\ | ? * y caracteres 0-31.
    Los reemplazamos todos por _ para evitar OSError [Errno 22].
    """
    import re
    return re.sub(r'[<>:"/\\|?*\x00-\x1f\s]+', "_", title).strip("_")


def save_article(article: WikiArticle, out_dir: Path) -> Path:
    """Guarda un artículo como archivo .txt con metadata en la primera línea."""
    safe_title = safe_filename(article.title)
    dest = out_dir / f"{safe_title}.txt"

    # 📚 Guardamos metadata como headers al inicio (fácil de parsear después).
    header = f"TITLE: {article.title}\nCATEGORY: {article.category}\nURL: {article.url}\n---\n"
    dest.write_text(header + article.text, encoding="utf-8")
    return dest


def load_article(txt_path: Path) -> WikiArticle:
    """Lee un .txt guardado por save_article y reconstruye el WikiArticle."""
    content = txt_path.read_text(encoding="utf-8")
    header, _, body = content.partition("\n---\n")

    meta = {}
    for line in header.splitlines():
        if ": " in line:
            k, _, v = line.partition(": ")
            meta[k.strip()] = v.strip()

    return WikiArticle(
        title=meta.get("TITLE", txt_path.stem),
        category=meta.get("CATEGORY", ""),
        url=meta.get("URL", ""),
        text=body.strip(),
    )
