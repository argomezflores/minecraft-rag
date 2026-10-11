from src.scraper import clean_wikitext


def test_brewing_template_with_named_base():
    raw = "{{Brewing\n|head = 1\n|Sugar\n|base = Awkward Potion\n|Potion of Swiftness\n|showvariants=1\n}}"
    assert "Brewing recipe: Sugar + Awkward Potion → Potion of Swiftness." in clean_wikitext(raw)


def test_brewing_template_with_numbered_bases():
    raw = (
        "{{Brewing\n|Gunpowder\n|base2=Potion of Swiftness\n|base1=Potion of Swiftness Extended\n"
        "|Splash Potion of Swiftness Extended\n|Splash Potion of Swiftness\n}}"
    )
    out = clean_wikitext(raw)
    assert "Brewing recipe: Gunpowder + Potion of Swiftness Extended → Splash Potion of Swiftness Extended." in out


def test_brewing_template_legacy_positional():
    raw = "{{Brewing|Nether Wart|Water Bottle|Awkward Potion}}"
    assert "Brewing recipe: Nether Wart + Water Bottle → Awkward Potion." in clean_wikitext(raw)


def test_crafting_template_preserved():
    raw = "{{Crafting|A1=Iron Ingot|C1=Iron Ingot|A2=Iron Ingot|B2=Chest|C2=Iron Ingot|B3=Iron Ingot|Output=Hopper}}"
    assert "→ Hopper." in clean_wikitext(raw)
