"""
scrape_wiki.py — CLI para bajar el corpus curado de la Minecraft Wiki.

Uso:
  python scripts/scrape_wiki.py               # full run
  python scripts/scrape_wiki.py --dry         # solo lista qué bajaría, sin bajar

Se guarda cada artículo como data/wiki/{title}.txt con headers de metadata.
Los archivos existentes se saltan (idempotente) — para forzar re-descarga,
borra la carpeta `data/wiki/`.
"""

import sys
import truststore
from pathlib import Path

# 📚 truststore usa los certs nativos de Windows (fix SSL en Win).
truststore.inject_into_ssl()

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.config import WIKI_PATH
from src.scraper import _get_site, fetch_category, fetch_pages_by_title, save_article, safe_filename


# 📚 Categorías curadas — corpus expandido v3.
# Foco de Rogelio: crafteo, redstone, mecánicas, hornos, pociones. NO estructuras.
CATEGORIES = [
    ("Items", 300),                # subimos de 250: más items del late-game
    ("Blocks", 500),               # ⬆️ 220 → 500: captura Hopper, Piston, Repeater, Furnace, etc.
    ("Mobs", 100),
    ("Potions", 60),               # ⬆️ ampliado
    ("Enchantments", 50),
    ("Gameplay", 150),             # ⬆️ 120 → 150: más mecánicas
    ("Redstone circuits", 60),     # ⬆️ 40 → 60
    ("Redstone components", 80),   # 🆕 categoría específica de componentes
    ("Utility blocks", 60),        # 🆕 furnace, brewing stand, cauldron, etc.
    ("Mechanics", 80),             # 🆕 hunger, XP, sleep, brewing mechanics
    ("Farming", 50),               # 🆕 cultivos, breeding
    ("Biomes", 60),
]

# 📚 Fallback explícito: páginas críticas que Rogelio necesita en su día a día
# como jugador. Si alguna categoría no las cubre (o cortó por max_pages),
# las bajamos por nombre directamente. Cero duplicación gracias al upsert.
PRIORITY_PAGES = [
    # Redstone components
    "Redstone Repeater", "Redstone Comparator", "Redstone Dust", "Redstone Torch",
    "Piston", "Sticky Piston", "Observer", "Dispenser", "Dropper",
    "Redstone Block", "Daylight Detector", "Tripwire Hook", "Pressure Plate",
    "Button", "Lever", "Detector Rail", "Powered Rail",
    # Item transport
    "Hopper", "Chest", "Trapped Chest", "Ender Chest", "Shulker Box",
    "Minecart", "Minecart with Hopper", "Minecart with Chest",
    # Utility blocks
    "Furnace", "Blast Furnace", "Smoker", "Brewing Stand", "Cauldron",
    "Crafting Table", "Enchanting Table", "Anvil", "Grindstone",
    "Loom", "Stonecutter", "Cartography Table", "Smithing Table",
    "Fletching Table", "Beacon", "Conduit", "Composter", "Barrel",
    "Lodestone", "Respawn Anchor",
    # Combat/farming favorites
    "Diamond Pickaxe", "Netherite Pickaxe", "Diamond Sword", "Netherite Sword",
    "Bow", "Crossbow", "Trident", "Shield", "Elytra",
    "Totem of Undying", "Ender Pearl", "Eye of Ender",
    # Portals & travel
    "Nether portal", "End portal", "Bed", "Boat", "Horse",
    # Brewing/potions core
    "Potion", "Splash Potion", "Lingering Potion", "Tipped Arrow",
    "Blaze Powder", "Nether Wart", "Glass Bottle", "Water Bottle",
    "Awkward Potion", "Mundane Potion", "Thick Potion",
    # Enchantments favoritas
    "Fortune", "Silk Touch", "Efficiency", "Unbreaking", "Mending",
    "Sharpness", "Looting", "Power", "Infinity", "Feather Falling",
    # Mecánicas
    "Crafting", "Brewing", "Smelting", "Enchanting",
    "Experience", "Hunger", "Sleep", "Trading", "Villager",
]


def main() -> int:
    dry = "--dry" in sys.argv
    WIKI_PATH.mkdir(parents=True, exist_ok=True)

    print(f"Destino: {WIKI_PATH}")
    print(f"Categorías ({len(CATEGORIES)}): {[c[0] for c in CATEGORIES]}")
    print(f"Páginas prioritarias ({len(PRIORITY_PAGES)}): {PRIORITY_PAGES[:8]}...")
    if dry:
        print("\n[DRY RUN] no se descargará nada.\n")
        return 0

    site = _get_site()
    print(f"Conectado a {site.host} (versión {site.version})\n")

    total_saved = 0
    total_skipped = 0

    def _persist(article) -> None:
        nonlocal total_saved, total_skipped
        dest = WIKI_PATH / f"{safe_filename(article.title)}.txt"
        if dest.exists():
            total_skipped += 1
            return
        save_article(article, WIKI_PATH)
        total_saved += 1
        if total_saved % 25 == 0:
            print(f"  [progress] {total_saved} nuevos guardados...")

    # 📚 Primero categorías (bulk), después páginas prioritarias (fallback exacto).
    for category_name, max_pages in CATEGORIES:
        for article in fetch_category(site, category_name, max_pages=max_pages):
            _persist(article)

    for article in fetch_pages_by_title(site, PRIORITY_PAGES):
        _persist(article)

    print(f"\n✅ Terminado.")
    print(f"   Nuevos guardados: {total_saved}")
    print(f"   Ya existentes:    {total_skipped}")
    print(f"   Total en cache:   {len(list(WIKI_PATH.glob('*.txt')))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
