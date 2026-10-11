"""
scrape_priority.py — Baja SOLO las páginas prioritarias (Piston, Repeater, Hopper, etc.)

Uso rápido cuando ya tienes las categorías bulk pero faltan páginas específicas
que quedaron fuera por max_pages.

Uso:
  python scripts/scrape_priority.py                        # baja prioritarias que falten
  python scripts/scrape_priority.py --refresh-matching brew
      # re-baja y SOBREESCRIBE los artículos del cache que contienen "brew"
      # (útil cuando cambia clean_wikitext: el cache guarda texto ya limpio)
"""

import sys
import truststore
from pathlib import Path

truststore.inject_into_ssl()

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.config import WIKI_PATH
from src.scraper import _get_site, fetch_pages_by_title, save_article, safe_filename, load_article
from scripts.scrape_wiki import PRIORITY_PAGES


def _cached_matching(keyword: str) -> dict[str, str]:
    """{title: category} de los artículos del cache cuyo texto contiene `keyword`."""
    matches = {}
    for txt in sorted(WIKI_PATH.glob("*.txt")):
        article = load_article(txt)
        if keyword.lower() in article.text.lower():
            matches[article.title] = article.category
    return matches


def main() -> int:
    WIKI_PATH.mkdir(parents=True, exist_ok=True)
    print(f"Destino: {WIKI_PATH}")

    refresh = None
    if "--refresh-matching" in sys.argv:
        refresh = _cached_matching(sys.argv[sys.argv.index("--refresh-matching") + 1])
        titles = list(refresh)
        print(f"Refrescando {len(titles)} artículos del cache\n")
    else:
        titles = PRIORITY_PAGES
        print(f"Páginas prioritarias: {len(titles)}\n")

    site = _get_site()
    print(f"Conectado a {site.host}\n")

    saved, skipped = 0, 0
    for article in fetch_pages_by_title(site, titles):
        dest = WIKI_PATH / f"{safe_filename(article.title)}.txt"
        if refresh is not None:
            # 📚 Conservamos la categoría original (fetch_pages_by_title pone "Priority").
            article = article._replace(category=refresh.get(article.title, article.category))
        elif dest.exists():
            skipped += 1
            continue
        save_article(article, WIKI_PATH)
        saved += 1

    print(f"\n✅ Terminado. {saved} guardados, {skipped} ya existentes.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
