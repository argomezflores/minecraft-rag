"""
scrape_wiki.py — CLI para bajar el corpus curado de la Minecraft Wiki.

Uso:
  python scripts/scrape_wiki.py               # full run
  python scripts/scrape_wiki.py --dry         # solo lista qué bajaría, sin bajar
  python scripts/scrape_wiki.py --only "Hostile mobs,Boss mobs"   # solo esas categorías, sin prioritarias

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


# 📚 Categorías curadas. fetch_category NO entra a subcategorías: en la wiki los
# mobs, estructuras y biomas viven en subcategorías (Category:Mobs → Hostile mobs…),
# así que se listan explícitas. No se recorren todas a propósito: traerían
# "Joke mobs", mobs de la película, biomas de Minecraft Dungeons, etc. (eval-log #011).
CATEGORIES = [
    ("Items", 300),                # subimos de 250: más items del late-game
    ("Blocks", 500),               # ⬆️ 220 → 500: captura Hopper, Piston, Repeater, Furnace, etc.
    ("Mobs", 100),                 # solo páginas generales (Mob, Boss, Undead…)
    ("Potions", 60),               # ⬆️ ampliado
    ("Enchantments", 50),
    ("Gameplay", 150),             # ⬆️ 120 → 150: más mecánicas
    ("Redstone circuits", 60),     # ⬆️ 40 → 60
    ("Biomes", 60),                # solo páginas generales
    # 🆕 v6 (#011): subcategorías con el contenido real
    ("Hostile mobs", 80),
    ("Passive mobs", 80),
    ("Neutral mobs", 40),
    ("Boss mobs", 10),
    ("Generated structures", 60),
    ("Dimensions", 20),
    ("Overworld biomes", 80),
    ("Nether biomes", 10),
    ("End biomes", 10),
]

# 📚 Páginas que las subcategorías traen pero que no son del juego normal
# (eval-log #013): bromas de April Fools, contenido eliminado, Minecraft Education
# y features nunca usadas. Giant e Illusioner se quedan: existen en Java vía comandos.
EXCLUDE_TITLES = {
    # Joke features (April Fools)
    "Potato Village", "Potato Geode", "Potato Mineshaft", "Pink Wither", "Redstone Bug",
    "Toxifin Slab", "Ruined Portatol", "Colosseum", "Hash Well", "Lunar Base",
    # Removed features
    "Villager (old)", "Brick Pyramid", "Obsidian Wall", "Sky dimension", "Starting House",
    # Minecraft Education / unused
    "Agent", "NPC", "Elder Guardian Ghost",
}

# 📚 Fallback explícito: páginas críticas que Rogelio necesita en su día a día
# como jugador. Si alguna categoría no las cubre (o cortó por max_pages),
# las bajamos por nombre directamente. Cero duplicación gracias al upsert.
PRIORITY_PAGES = [
    # Redstone components
    "Redstone Repeater", "Redstone Comparator", "Redstone Dust", "Redstone Torch",
    "Piston", "Sticky Piston", "Observer", "Dispenser", "Dropper",
    "Redstone Block", "Daylight Detector", "Tripwire Hook", "Pressure Plate",
    "Button", "Lever", "Detector Rail", "Powered Rail",
    "Redstone Lamp", "Target", "Sculk Sensor", "Calibrated Sculk Sensor",
    "Trapdoor", "Iron Trapdoor", "TNT", "Torch", "Paper",
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
    "The Nether", "The End", "Overworld",
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

    # 📚 --only: corre solo esas categorías (y no las prioritarias). Útil para agregar
    # categorías nuevas sin volver a pedir las ~1,000 páginas ya cacheadas.
    categories = CATEGORIES
    only = None
    if "--only" in sys.argv:
        only = {c.strip() for c in sys.argv[sys.argv.index("--only") + 1].split(",")}
        categories = [(name, n) for name, n in CATEGORIES if name in only]
        unknown = only - {name for name, _ in CATEGORIES}
        if unknown:
            print(f"[warn] no están en CATEGORIES: {sorted(unknown)}")

    print(f"Destino: {WIKI_PATH}")
    print(f"Categorías ({len(categories)}): {[c[0] for c in categories]}")
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
        if article.title in EXCLUDE_TITLES:
            return
        dest = WIKI_PATH / f"{safe_filename(article.title)}.txt"
        if dest.exists():
            total_skipped += 1
            return
        save_article(article, WIKI_PATH)
        total_saved += 1
        if total_saved % 25 == 0:
            print(f"  [progress] {total_saved} nuevos guardados...")

    # 📚 Primero categorías (bulk), después páginas prioritarias (fallback exacto).
    for category_name, max_pages in categories:
        for article in fetch_category(site, category_name, max_pages=max_pages):
            _persist(article)

    if only is None:
        for article in fetch_pages_by_title(site, PRIORITY_PAGES):
            _persist(article)

    print(f"\n✅ Terminado.")
    print(f"   Nuevos guardados: {total_saved}")
    print(f"   Ya existentes:    {total_skipped}")
    print(f"   Total en cache:   {len(list(WIKI_PATH.glob('*.txt')))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
