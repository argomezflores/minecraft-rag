"""
corpus_filters.py — Blocklist de artículos ruido/meta detectados en producción.

Concepto: los embeddings + re-ranking no pueden compensar chunks basura. Algunos
artículos de la wiki tienen vocabulario disperso o son meta-páginas (Language,
Achievement, listados históricos) que aparecen frecuentemente como top-1 falso.

Fuente de datos: 19 queries reales de Rogelio en el widget mostraron que estos
artículos dominaban las respuestas fallidas. En vez de re-scrapear (perder los
datos), simplemente los filtramos en el retriever.

Ventajas del filtrado en runtime:
- Reversible con env var (cambio de idea instantáneo)
- No requiere re-ingest de 113k chunks
- Auditable (una línea = una decisión de exclusión)
- Extensible cuando detectemos más ruido en futuros logs

Convención: para comparación case-sensitive del title exacto de MediaWiki.
"""

import re


# 📚 Blocklist explícita basada en logs reales del 2026-08-28.
# Cada entrada tiene un motivo claro para excluirla.
META_BLOCKLIST_TITLES: set[str] = {
    # --- Meta-páginas de vocabulario disperso (aparecen en TODO)
    "Language",              # Sistema de idiomas del juego; matchea cualquier palabra
    "Chat",                  # Sistema de chat; keyword espurio en "chat de comandos"
    "Achievement",           # Lista de todos los logros; keyword denso
    "Advancement",           # Lista de avances (Java Edition); keyword denso
    "Death messages",        # Lista de mensajes de muerte; vocabulario disperso
    "Server",                # Sistema de servidores; no aporta a queries de items
    "Player",                # Página del jugador; keyword espurio en mecánicas
    "Gameplay",              # Página raíz de gameplay; disperso
    "Blocking",              # Mecánica antigua eliminada; matchea "bloque" falsamente

    # --- Recopilaciones que dominan por densidad léxica
    "Mine Ingredient",       # Página específica de Bedrock, muy densa
    "Cooking",               # Lista de recetas; keyword denso

    # --- Artículos cortos con matcheo espurio
    "Cactus",                # Corto y denso; aparece constantemente
    "Cake",                  # Corto y denso; aparece constantemente
    "Fluid",                 # Página genérica de fluidos
    "Banner",                # Aparece como falso positivo en logs

    # --- Easter eggs / April Fools (no son mecánicas reales)
    "Funky Portal",          # April Fools
    "Copper Golem Statue",   # April Fools
    "A Very Fine Item",      # Easter egg
    "Air (April Fools' joke)",
    "Amber Gem",             # Easter egg
    "An Ant",                # Easter egg
    "Ankle Monitor",         # Easter egg
    "3D",                    # Página meta

    # --- Otros ruidos detectados
    "Compound",              # Elemento de laboratorio educativo (Bedrock)
    "Achievement",           # Duplicado intencional (por si acaso)
}

# 📚 Patrones regex para grupos de páginas (más eficiente que listar cada una).
META_PATTERNS: list[re.Pattern] = [
    re.compile(r"^Biome/Before", re.IGNORECASE),   # Páginas históricas de biomas
    re.compile(r"April Fools", re.IGNORECASE),      # Cualquier April Fools
    re.compile(r"^Sound event", re.IGNORECASE),     # Listas de audio
    re.compile(r"^Music disc", re.IGNORECASE),      # Discos de música
    re.compile(r"^Version history/", re.IGNORECASE),  # Historial de versiones
]


def is_blocked(title: str) -> bool:
    """
    True si el artículo debe excluirse del retrieval.

    Chequea dos cosas:
    1. Título en la blocklist explícita.
    2. Título matchea alguno de los patrones regex.
    """
    if not title:
        return False
    if title in META_BLOCKLIST_TITLES:
        return True
    return any(p.search(title) for p in META_PATTERNS)


def filter_hits(hits: list) -> list:
    """
    Filtra una lista de Hits (o dicts con clave 'title') removiendo los bloqueados.

    Genérico para no importar Hit acá y romper el ciclo.
    """
    return [h for h in hits if not is_blocked(getattr(h, "title", None) or (h.get("title") if isinstance(h, dict) else ""))]
