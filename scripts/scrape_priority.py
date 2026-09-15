"""
scrape_priority.py — Baja SOLO las páginas prioritarias (Piston, Repeater, Hopper, etc.)

Uso rápido cuando ya tienes las categorías bulk pero faltan páginas específicas
que quedaron fuera por max_pages.
"""

import sys
import truststore
from pathlib import Path

truststore.inject_into_ssl()

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.config import WIKI_PATH
from src.scraper import _get_site, fetch_pages_by_title, save_article, safe_filename
from scripts.scrape_wiki import PRIORITY_PAGES


def main() -> int:
    WIKI_PATH.mkdir(parents=True, exist_ok=True)
    print(f"Destino: {WIKI_PATH}")
    print(f"Páginas prioritarias: {len(PRIORITY_PAGES)}\n")

    site = _get_site()
    print(f"Conectado a {site.host}\n")

    saved, skipped = 0, 0
    for article in fetch_pages_by_title(site, PRIORITY_PAGES):
        dest = WIKI_PATH / f"{safe_filename(article.title)}.txt"
        if dest.exists():
            skipped += 1
            continue
        save_article(article, WIKI_PATH)
        saved += 1

    print(f"\n✅ Terminado. {saved} nuevos, {skipped} ya existentes.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
