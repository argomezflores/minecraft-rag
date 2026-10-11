from src.ingest import recipe_chunks
from src.scraper import WikiArticle


def test_recipe_lines_become_titled_chunks():
    article = WikiArticle(
        title="Redstone Comparator",
        category="Blocks",
        url="https://minecraft.wiki/w/Redstone_Comparator",
        text=(
            "Natural generation\n2–9 Redstone comparators generate in ancient cities.\n\n"
            "Crafting recipe: Redstone Torch, Redstone Torch, Nether Quartz, Redstone Torch, "
            "Stone, Stone, Stone arranged in the crafting grid → Redstone Comparator.\n\n"
            "Crafting recipe: Redstone Torch, Redstone Torch, Nether Quartz, Redstone Torch, "
            "Stone, Stone, Stone arranged in the crafting grid → Redstone Comparator.\n"
        ),
    )
    chunks = recipe_chunks(article)
    assert len(chunks) == 1  # líneas idénticas se deduplican
    assert chunks[0].startswith("How to make Redstone Comparator (crafting): Crafting recipe: Redstone Torch")


def test_recipe_chunk_uses_recipe_output_not_article_title():
    article = WikiArticle(
        title="Sugar",
        category="Items",
        url="",
        text="Brewing recipe: Sugar + Awkward Potion → Potion of Swiftness.",
    )
    assert recipe_chunks(article) == [
        "How to make Potion of Swiftness (brewing): Brewing recipe: Sugar + Awkward Potion → Potion of Swiftness."
    ]


def test_article_without_recipes_has_no_recipe_chunks():
    article = WikiArticle(title="Biome", category="Gameplay", url="", text="A biome is a region.")
    assert recipe_chunks(article) == []
