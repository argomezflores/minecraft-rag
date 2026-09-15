# Guía técnica — Cómo funciona el RAG de Minecraft

Un tour narrativo por el proyecto. Se lee en orden, siguiendo el flujo real de los datos: de la Minecraft Wiki hasta una respuesta con citas en el chat del juego.

---

## 1. ¿Qué es RAG y por qué existe?

**Retrieval-Augmented Generation** = "Generación asistida por recuperación". Un LLM (como Claude) es muy bueno redactando pero no conoce tu información específica (aquí: todos los items, mobs y mecánicas de Minecraft actualizados a la última versión).

**Solución RAG**: antes de responder, buscamos los fragmentos más relevantes en TU corpus (la wiki oficial) y se los damos al LLM como contexto. El LLM ya no inventa — sintetiza lo que le pasaste.

Dos fases:

- **Ingesta (offline)** — scrapear la wiki una vez y guardar vectores en base de datos.
- **Query (runtime)** — cada pregunta usa esos vectores para encontrar contexto y generar respuesta.

---

## 2. Recorrido del código: Ingesta

Punto de entrada: `python scripts/scrape_wiki.py` seguido de `python scripts/ingest_all.py --reset`.

### 2.1. Scraping → [scripts/scrape_wiki.py](../scripts/scrape_wiki.py) + [src/scraper.py](../src/scraper.py)

Bajamos artículos de 8 categorías curadas de minecraft.wiki:

- Items (~250 páginas)
- Blocks (~220)
- Mobs (~100)
- Potions, Enchantments, Biomes, Gameplay, Redstone (~300 combinado)

**Total: ~800 artículos**.

📚 **¿Cómo funciona el scraping?** No es un bot con navegador — usamos la API MediaWiki (`https://minecraft.wiki/api.php`) que devuelve JSON estructurado. La librería `mwclient` la envuelve. Le pedimos "dame los artículos de la categoría Items" y nos itera cada uno.

📚 **Ética obligatoria**:
- User-Agent identificable (sin esto te bloquean)
- Delay de 1s entre requests
- Sin paralelismo
- Cache local — no re-descargamos lo que ya tenemos

📚 **Wikitext, no HTML**: la API devuelve el "código fuente" del artículo con marcado tipo `{{Infobox item|...}}` y `[[Diamond|diamond]]`. `mwparserfromhell` lo limpia a texto plano legible. Es mucho más limpio que scrapear HTML renderizado con JavaScript y menús.

📚 **Preservación de recetas** (v4): antes, `strip_code()` borraba **todos** los templates — incluidas las recetas de crafting `{{Crafting|A1=X|...|Output=Z}}`. Nuestro texto "limpio" quedaba sin recetas y el bot decía "no tengo info" para "¿cómo craftear una mesa?" aunque el artículo estaba indexado. **Fix**: iteramos sobre `wikicode.filter_templates()` y para `{{Crafting}}`, `{{Smelting}}`, `{{Brewing}}` los convertimos a frases legibles ANTES del `strip_code()`. Ejemplo: `{{Crafting|A1=Oak Planks|B1=Oak Planks|A2=Oak Planks|B2=Oak Planks|Output=Crafting Table}}` → `"Crafting recipe: Oak Planks, Oak Planks, Oak Planks, Oak Planks arranged in the crafting grid → Crafting Table."`. Los templates no reconocidos siguen cayendo al fallback (se eliminan).

Cada artículo se guarda como `data/wiki/<title>.txt` con headers de metadata al inicio:
```
TITLE: Diamond Pickaxe
CATEGORY: Items
URL: https://minecraft.wiki/w/Diamond_Pickaxe
---
<texto limpio>
```

### 2.2. Chunking → [src/chunker.py](../src/chunker.py)

`split_text(text, chunk_size=800, overlap=150)`.

**¿Por qué 800 caracteres?** El modelo de embeddings tiene límite de ~512 tokens ≈ 2000 chars. 800 caracteres ≈ un párrafo grande = una idea completa por chunk.

**¿Por qué overlap de 150?** Para no cortar ideas a la mitad. Si un chunk termina "the Beacon requires a base of", el siguiente empezará "of 3×3 Iron blocks..." para no perder el número.

**Estrategia de corte**: buscamos separadores "limpios" (`\n\n` > `\n` > `. ` > ` `) para respetar la estructura.

### 2.3. Embeddings → [src/embedder.py](../src/embedder.py)

Un **embedding** es un vector de 384 números que representa el *significado* de un texto. Textos con significado similar quedan cerca en ese espacio de 384 dimensiones.

Usamos `all-MiniLM-L6-v2` porque:
- **Inglés puro** — la wiki está en inglés, y modelos monolingües rinden mejor que multilingües en su idioma nativo.
- Es **local** (sin API, sin latencia de red)
- Es **rápido** (~200 chunks/segundo en CPU)
- Es **gratis**

`normalize_embeddings=True` hace que los vectores tengan norma 1, lo que permite usar producto punto = cosine similarity (más rápido).

### 2.4. Vector store → [src/ingest.py](../src/ingest.py)

Metemos todo en **ChromaDB** (base vectorial embebida, persistente en `data/chroma/`).

Cada chunk se guarda con:
- `id` — clave única e idempotente (`Diamond_Pickaxe_c0`, `Diamond_Pickaxe_c1`, ...)
- `document` — el texto del chunk
- `embedding` — el vector de 384 dims
- `metadata` — `{title, category, url, chunk_index}`

`hnsw:space=cosine` le dice a Chroma que use cosine similarity para las búsquedas.

---

## 3. Recorrido del código: Query

Punto de entrada: `POST /query {"question": "..."}` → [src/api.py](../src/api.py).

### 3.1. Retrieval → [src/retriever.py](../src/retriever.py)

1. La pregunta se convierte al **mismo espacio vectorial** que los chunks.
2. ChromaDB busca los **K vectores más cercanos** (default K=5).
3. 🆕 **v5: Blocklist post-Chroma**. Filtramos chunks de artículos "ruido" detectados en logs reales (`Language`, `Cactus`, `Cake`, `Biome/Before*`, `Achievement`, etc.). Ver [src/corpus_filters.py](../src/corpus_filters.py). Se sobre-pide `n_results = k * 3` para compensar los que serán filtrados.
4. Devolvemos texto + metadata + `score` (0-1, más alto = más similar).

📚 **Score no distance**: Chroma devuelve *distancia* coseno (0=idéntico, 2=opuesto). La convertimos a *score* con `1 - dist/2` porque es más intuitivo para el frontend.

### 3.1.5. Query Rewriting → [src/query_rewriter.py](../src/query_rewriter.py) 🆕 v3

Antes del retrieval, Claude Haiku genera 3 variaciones de la pregunta. Cada una captura un ángulo semántico distinto. Se busca con las 3 y se hace merge deduplicado.

📚 **Por qué**: los embeddings comparan vectores independientes. Si la query es corta o está en español pero el corpus en inglés, puede fallar. Multi-query da cobertura semántica.

📚 **Modelo Haiku**: 10x más barato, 3x más rápido que Sonnet. Suficiente para reformular.

📚 **Fallback silencioso**: si Haiku falla, devuelve solo la query original — el pipeline no rompe.

📚 **Opt-out**: `QUERY_REWRITE=false` para desactivar (útil para A/B testing).

### 3.1.6. Re-ranking → [src/reranker.py](../src/reranker.py) 🆕 v3

Después del retrieval inicial (top-20 por cada variación), un cross-encoder re-puntúa cada chunk viendo (query, chunk) COMO PAR — mucho más preciso que el bi-encoder.

📚 **Bi-encoder vs cross-encoder**:
- Bi-encoder (embedder): rápido, compara vectores independientes. Bueno para "candidatos".
- Cross-encoder (reranker): lento pero preciso. Bueno para "top final".
- Arquitectura estándar desde 2021: bi-encoder para 85k → cross-encoder para 20 → top-5.

📚 **Modelo**: `cross-encoder/ms-marco-MiniLM-L-6-v2` — local, gratis, ~90 MB.

📚 **Impacto real**: la query "Diamond Pickaxe" que antes traía chunks de Anvil (porque el yunque menciona diamond), ahora trae chunks del artículo Diamond Pickaxe en top-3.

📚 **Opt-out**: `RERANK=false`.

### 3.1.7. Orquestador → [src/pipeline.py](../src/pipeline.py) 🆕 v3

Un solo entry point (`answer_question()`) que encadena rewriter → retriever → merger → reranker → generator. Es el ÚNICO lugar donde se decide qué mejora aplicar.

Le API y CLI llaman esta función — no duplican lógica.

### 3.2. Generation → [src/generator.py](../src/generator.py)

Prompt con:
- **System**: "Eres experto en Minecraft. Responde SOLO con el contexto. Traduce al español. Máx 4-5 líneas. Cita fuentes con [N]."
- **Context**: los K chunks numerados con `[1] (Wiki: Beacon) <texto>`
- **User**: la pregunta original

Claude responde en español aunque el contexto esté en inglés. Le dijimos explícitamente que traduzca al responder — un solo call, sin traductor intermedio.

📚 **Anti-alucinación endurecida** (v4): en pruebas encontramos que Claude a veces contradecía su propia declaración: *"No tengo esa info... **sin embargo, necesitas 3 Diamonds y 2 Sticks**"*. El LLM colaba conocimiento pre-entrenado sobre Minecraft. Reglas agregadas al `SYSTEM_PROMPT_FULL`: (a) NO usar conocimiento pre-entrenado, (b) si dices "no tengo info", PARA AHÍ, no añadas "sin embargo", (c) honestidad > utilidad. Reduce ~70% de casos; para eliminación total se necesitaría guardrail post-generation (Fase C futura).

📚 **Dos modos de respuesta** (v4): la API acepta `format="full"` (widget web, markdown, citas [N], 512 tokens) o `format="chat"` (bot in-game, texto plano corto, sin citas, 256 tokens). Cada uno tiene su propio `SYSTEM_PROMPT_*`. El bot Mineflayer envía `format:"chat"` para que Claude genere directamente respuestas más útiles en el chat de MC (evita post-processing y ahorra ~1s de latencia).

### 3.3. API → [src/api.py](../src/api.py)

FastAPI envuelve todo en HTTP:
- `POST /query` — endpoint principal
- `GET /health` — monitoring
- `POST /ingest` — re-indexar
- `GET /docs` — Swagger UI

CORS abierto para widget + bot.

### 3.4. Widget web → [widget/chat-widget.js](../widget/chat-widget.js)

JS puro (sin frameworks) con tema Minecraft (verde grass, marrón dirt, sombras pixel). Se embebe en cualquier página:

```html
<link rel="stylesheet" href="/widget/chat-widget.css">
<script src="/widget/chat-widget.js" data-api="https://tu-api.com"></script>
```

Cada fuente se muestra como link a la wiki original (atribución CC BY-SA).

### 3.4.1 🆕 v4 — Traducción ES→EN determinística → [src/mc_glossary.py](../src/mc_glossary.py)

Diccionario manual de ~90 términos de Minecraft en español → inglés oficial. Se aplica en el rewriter como **variación garantizada** además de las de Haiku. Esto asegura que "tolva" siempre tenga "Hopper" en las variaciones aunque Haiku no lo genere.

📚 **Por qué manual vs. dinámico**: determinístico, cero costo, cero latencia. Se extiende agregando líneas al dict. Cubre los términos más comunes que un jugador mexicano usa.

### 3.5. Bot in-game → [minecraft_bot/bot.js](../minecraft_bot/bot.js)

Node.js + `mineflayer`. El bot (**MineRag** desde v4) se conecta al mundo abierto a LAN como un jugador falso. Cuando alguien escribe `!rag <pregunta>` en el chat, el bot:

1. Extrae la pregunta.
2. Llama al FastAPI local (`POST /query` con `format:"chat"`).
3. **Limpia el texto** (`cleanMarkdown()`): quita `**bold**` → `§l§r`, elimina `*italic*`, quita citas `[N]`, quita emojis.
4. Aplica **códigos de color MC** `§`:
   - `§a` (verde) para el prefijo `→`
   - `§f` (blanco) para el texto de respuesta
   - `§8` (gris oscuro) para la fuente
   - `§7§o` (gris cursivo) para el "Minando la respuesta..."
5. Divide la respuesta en chunks de <240 chars (límite del chat MC).
6. Publica cada chunk con 700ms de pausa para no ser kickeado por anti-spam.
7. Cita la fuente principal al final (compacta, sin score).

📚 **¿Por qué Mineflayer y no un mod Fabric?** Fabric es Java + Gradle + curva pronunciada. Mineflayer es ~150 líneas de Node.js que funcionan con Minecraft vanilla. Trade-off: no puedes registrar un slash-command real (`/rag`), usas prefijo custom (`!rag`).

📚 **Sobre el skin de MineRag**: en LAN con `auth: "offline"` el skin queda default (Steve/Alex). Para skin custom se necesitaría un server Paper con `SkinsRestorer` plugin — decisión: no vale la pena el setup extra para v4.

---

## 4. 🆕 v4 — Observabilidad + Benchmark

### 4.1. Query Logger → [src/query_log.py](../src/query_log.py)

Cada request a `/query` se guarda en `data/logs/queries.jsonl` (append-only). Formato: 1 objeto JSON por línea con: timestamp, source (widget/bot/cli), question, format, rewrites, sources devueltas, answer completa, latencia, count de chunks.

📚 **Por qué JSONL sin DB**: portable, versionable en git, exportable a pandas con 1 línea, sin infra (SQLite/Postgres). Perfecto para <100k entries.

📚 **Best-effort**: si el disco falla, log a stderr pero **NO rompe** la respuesta al usuario.

### 4.2. Benchmark → [scripts/benchmark.py](../scripts/benchmark.py)

Ejecuta un conjunto de queries reales (backfill del historial de desarrollo + acumuladas del logger) y produce métricas objetivas: source hit rate, answer hit ratio, latencia p50/p95. Salida: `data/benchmarks/results_v4_<ts>.json` + resumen en stdout.

📚 **Backfill del historial real vs. golden set fabricado**: usamos queries que YA fallaron o funcionaron durante desarrollo. Más honesto y matchea el uso real.

### 4.3. Timeline visual → [docs/timeline.html](timeline.html)

HTML self-contained con las 4 iteraciones del proyecto (v1-v4). Cada card tiene: objetivo, decisiones de orquestación, bugs detectados probando, aprendizajes. Termina con manifiesto sobre el rol del ingeniero en la era AI-assisted coding. **Pieza clave del portafolio.**

---

## 5. Decisiones técnicas importantes

### ¿Por qué ChromaDB y no FAISS?
- FAISS es más rápido en millones de vectores, pero requiere manejar índices/persistencia manualmente.
- Chroma es más simple: cliente persistente que guarda todo en disco, con metadata y filtros incluidos.
- Para <100k chunks (nuestro caso), la diferencia de velocidad es imperceptible.

### ¿Por qué `all-MiniLM-L6-v2` y no OpenAI/Cohere embeddings?
- Local = gratis, sin latencia de red, sin API keys.
- Inglés puro = mejor calidad que multilingüe en textos en inglés.
- Portable: mismo modelo en dev y prod, sin sorpresas.

### ¿Por qué Claude y no otro LLM?
- Ya en el stack (NYRO usa Claude API para todo).
- Excelente al traducir contexto EN → respuesta ES en un solo call.
- Sigue instrucciones estrictas ("no inventes") mejor que Groq/Llama.

### ¿Por qué chunks de 800?
- 500 = ideas cortadas, retrieval pierde contexto vecino.
- 1500 = mucho ruido, retrieval menos preciso.
- 800 es el sweet spot.

### ¿Por qué top-K=5?
- K=1: si el mejor chunk no tiene la respuesta, el LLM no tiene otra opción.
- K=10+: mucho contexto = más tokens al LLM = más caro y más ruido.
- 5 balancea recall (encontrar la info) con precision (no meter ruido).

### ¿Por qué scrape + cache local en lugar de scrapear en runtime?
- Runtime queries deben ser <2s. Un scrape live tarda 3-5s por artículo.
- La wiki cambia poco día a día — cachear es sano.
- Aísla el sistema de outages de minecraft.wiki.

---

## 5. Cómo modificar cosas comunes

### Agregar más categorías al scraping
Edita [scripts/scrape_wiki.py](../scripts/scrape_wiki.py) y agrega a `CATEGORIES`:
```python
CATEGORIES = [
    ...
    ("Structures", 60),   # ejemplo
]
```
Luego `python scripts/scrape_wiki.py` (incremental — solo baja lo nuevo).

### Cambiar el modelo de embeddings
En `.env`:
```
EMBEDDING_MODEL=BAAI/bge-large-en-v1.5   # más potente pero más lento
```
Luego `python scripts/ingest_all.py --reset` (obligatorio: los vectores viejos son incompatibles).

### Ajustar top-K por request
```
POST /query {"question": "...", "k": 8}
```

### Cambiar el prompt del LLM
Edita `SYSTEM_PROMPT` en [src/generator.py](../src/generator.py).

### Cambiar el prefijo del bot
En `minecraft_bot/bot.js`:
```javascript
$env:COMMAND_PREFIX = "!mc "     # ahora es "!mc <pregunta>"
```

---

## 6. Cómo evolucionar a "Agentic RAG" (Fase B)

Este RAG es reactivo: pregunta → búsqueda → respuesta.

Un **RAG agentic** es un grafo de decisiones donde el sistema puede:
- Clasificar el tipo de pregunta (crafting recipe vs mob stats vs mechanics).
- Buscar en múltiples índices (wiki + Reddit + patch notes).
- Detectar respuestas incompletas y reformular la query.
- Pedir aclaración al humano.

**Herramienta**: [LangGraph](https://langchain-ai.github.io/langgraph/). Solo LangGraph (no LangChain), envolviendo las funciones existentes como nodos:

```python
def rag_node(state):
    hits = search(state["question"])
    if max(h.score for h in hits) < 0.6:
        return {"next": "reformulate"}   # score bajo → intentar otra query
    return {"answer": generate_answer(state["question"], hits), "next": "END"}
```

Es proyecto separado — este RAG clásico es la fundación sobre la que se construye.
