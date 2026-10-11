# Wiki corpus

Plain-text copies of 1,046 articles from the [Minecraft Wiki](https://minecraft.wiki), downloaded through its MediaWiki API with `scripts/scrape_wiki.py` and `scripts/scrape_priority.py`. Each file begins with a `TITLE` / `CATEGORY` / `URL` header that links back to the original article.

**License:** the content belongs to the Minecraft Wiki contributors. It is licensed under [CC BY-NC-SA 3.0](https://creativecommons.org/licenses/by-nc-sa/3.0/) and is redistributed here, under that same license, for non-commercial and educational use. Templates were flattened to text: crafting, smelting and brewing recipes became sentences, and infoboxes and tables were removed.

This folder is versioned so that the project can be run without re-scraping. Building the vector index only takes `python scripts/ingest_all.py --reset`.
