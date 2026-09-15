# RAG Minecraft Wiki ⛏️

Sistema RAG (Retrieval-Augmented Generation) en Python que responde preguntas sobre Minecraft usando la [Minecraft Wiki oficial](https://minecraft.wiki) (licencia CC BY-SA). Sin LangChain, con FastAPI, widget web embebible, y **bot in-game (MineRag) vía Mineflayer** para hacerle preguntas directamente desde el chat del juego.

## ¿Qué hace?

Tres formas de consultar el mismo cerebro:

1. **Widget web** — chat flotante embebible en cualquier página.
2. **API REST** — endpoints HTTP para integrar donde quieras.
3. **MineRag bot in-game** — bot que se conecta a tu mundo por LAN, escuchas su respuesta en el chat con `!rag <pregunta>`. Respuesta con colores nativos de MC y sin markdown.

## Stack (v3)

| Capa | Librería |
|---|---|
| Wiki scraping | `mwclient` + `mwparserfromhell` (API MediaWiki) |
| Chunking | Implementación propia (~40 líneas) |
| Embeddings | `sentence-transformers` con `all-MiniLM-L6-v2` (inglés, local, gratis) |
| Vector store | ChromaDB (persistente) |
| **Query rewriting** 🆕 | **Claude Haiku 4.5** (multi-query, 3 variaciones) |
| **Re-ranking** 🆕 | **CrossEncoder `ms-marco-MiniLM-L-6-v2`** (local, gratis) |
| LLM generación | Claude Sonnet 4.5 (Anthropic SDK) |
| API | FastAPI + uvicorn |
| Widget | HTML + vanilla JS (tema Minecraft) |
| Bot in-game | Node.js + `mineflayer` + `axios` |

## Setup rápido

```powershell
# 1. Crear venv con Python 3.12
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1

# 2. Instalar deps
pip install -r requirements.txt

# 3. Configurar API key de Anthropic
copy .env.example .env
# Edita .env y pon tu ANTHROPIC_API_KEY

# 4. Scrape la wiki (~15-30 min con rate limit educado)
python scripts/scrape_wiki.py

# 5. Indexar (~15 min de embeddings)
python scripts/ingest_all.py --reset

# 6. Levantar API
uvicorn src.api:app --reload

# 7. Abrir widget web
# http://localhost:8000/widget/
```

Para el bot in-game, ver [minecraft_bot/README.md](minecraft_bot/README.md).

## Estructura

- [src/](src/) — Pipeline: scraper, chunker, embedder, retriever, generator, API
- [widget/](widget/) — Chat widget HTML/JS embebible (tema Minecraft)
- [minecraft_bot/](minecraft_bot/) — Bot Mineflayer para chat in-game
- [scripts/](scripts/) — CLIs (scrape, ingest, prueba de retrieval)
- [docs/GUIDE.md](docs/GUIDE.md) — **Tour pedagógico del proyecto** (lee esto para entender cómo funciona)
- [notebook/rag_pipeline.ipynb](notebook/rag_pipeline.ipynb) — Pipeline paso a paso en Jupyter
- [data/wiki/](data/wiki/) — Cache de artículos scrapeados
- [data/chroma/](data/chroma/) — Vector store persistente

## Endpoints API

- `GET /health` — healthcheck
- `POST /query` — body `{"question": "...", "format": "full" | "chat", "source": "widget|bot|cli"}` → `{"answer": "...", "sources": [...], "rewrites": [...], "debug": {...}}`
  - `format` (opcional, default `"full"`): `"full"` da markdown + citas [N] para widget web; `"chat"` da texto plano corto sin citas para el bot in-game.
  - `source` (opcional, default `"unknown"`): identifica el origen para el log persistente y el benchmark.
  - Cada source incluye: `title`, `url` (link a la wiki), `category`, `score`, `excerpt`.
- `GET /logs/recent?n=20` 🆕 — últimas N queries logueadas (útil para debug + demo).
- `POST /ingest?reset=false` — re-indexar (admin).
- `GET /docs` — Swagger UI.

## 📊 Observabilidad + Benchmark (v4)

Cada request a `/query` se guarda automáticamente en `data/logs/queries.jsonl` (JSONL append-only). Cada entrada incluye: timestamp, source, question, format, rewrites, sources devueltas, answer, latencia, count de chunks.

**Ver logs recientes:**
```powershell
curl http://localhost:8000/logs/recent?n=10
# o directo al archivo:
Get-Content data\logs\queries.jsonl -Tail 5
```

**Correr benchmark contra el pipeline actual:**
```powershell
.\.venv\Scripts\python.exe scripts\benchmark.py --version v4
# genera data\benchmarks\results_v4_<timestamp>.json + resumen en stdout
```

El benchmark hace **backfill de queries reales** del historial de desarrollo (Crafting Table, Diamond Pickaxe, Hopper, Beacon, Repeater, Smoker, etc.) más las queries acumuladas del logger. Métricas: **hit rate** (top-1 = artículo esperado), latencia p50/p95, respuesta contiene términos esperados.

## Deploy

```bash
docker compose up --build
```

Configura `ANTHROPIC_API_KEY` en `.env` o pásala como env var.

## Ética del scraping

Este proyecto respeta las políticas de la Minecraft Wiki:
- User-Agent identificable en cada request (`RAG-Minecraft/1.0 (contact: ...)`)
- Delay de 1s entre requests (no paralelismo)
- Cache local — no re-scrapeamos artículos ya bajados
- Contenido bajo CC BY-SA — atribución en las respuestas via URL de la fuente

## Documentación

- **[docs/timeline.html](docs/timeline.html)** 🌟 — **Timeline visual del proyecto** (v1 → v4) con decisiones de orquestación, bugs detectados y aprendizajes por versión. Termina con manifiesto sobre el rol del ingeniero en la era AI-assisted. **La primera lectura recomendada** si quieres entender el "por qué" del proyecto.
- **[docs/pipeline.html](docs/pipeline.html)** — **Pipeline técnico capa por capa** con código real, tradeoffs, ejemplos. Ábrelo en el navegador. Es la lectura recomendada para entender qué hace cada pieza técnicamente.
- **[docs/GUIDE.md](docs/GUIDE.md)** — Guía técnica narrativa (formato Markdown).
- **[minecraft_bot/README.md](minecraft_bot/README.md)** — Cómo correr el bot in-game paso a paso.
- **[notebook/rag_pipeline.ipynb](notebook/rag_pipeline.ipynb)** — Pipeline completo ejecutable celda por celda.

## Env vars nuevas

```
# v3 — Query rewriting + re-ranking
QUERY_REWRITE=true                                       # activar multi-query
RERANK=true                                              # activar cross-encoder
RETRIEVAL_TOP_N=20                                       # cast wide antes de rerank
RERANK_MODEL=cross-encoder/ms-marco-MiniLM-L-6-v2         # modelo local
HAIKU_MODEL=claude-haiku-4-5-20251001                    # rewriter

# v5 — Corpus filtering + score floor
TITLE_BOOST=0.3                # boost al score si título aparece en query
MIN_ACCEPTABLE_SCORE=0.15      # score floor: si nada supera esto, respuesta honesta
```

Todos los flags se pueden ajustar (`=false` / `=0`) para A/B testing o debug.
