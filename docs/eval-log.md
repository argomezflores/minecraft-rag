# Bitácora de evaluación

Una entrada por hallazgo: **síntoma → evidencia → causa → opciones → decisión → resultado medido**.
Eval set: [`data/eval/eval_set.json`](../data/eval/eval_set.json) (30 preguntas: pociones, redstone, crafteo, 3 negativas).
Correr: `python scripts/benchmark.py --eval-set data/eval/eval_set.json --version <tag>`

---

## 001 — El chunker duplica el mismo párrafo cientos de veces

**Síntoma.** Preguntas simples ("¿qué hace una tolva?", "poción de fuerza") devolvían como fuentes *Language, Achievement, Cactus, Biome/Before Beta 1.8*. Cuando sí traía el artículo correcto, las 5 fuentes eran el mismo título ("Hopper, Hopper, Hopper") y aun así la respuesta era "no lo encontré".

**Evidencia.**
- El corpus tiene 3.9M caracteres. Con chunks de 800 y overlap de 150 deberían salir ~6K chunks. Salieron **113,584** (19x), en un índice de 708 MB.
- `Death messages` (51K caracteres) → 2,392 chunks. Un tramo real:
  ```
  #40 start=2911 len=114 | 'yIntoWall.player\nAppears when the player is hurt...'
  #41 start=2912 len=113 | 'IntoWall.player\nAppears when the player is hurt...'
  #42 start=2913 len=112 | 'ntoWall.player\nAppears when the player is hurt...'
  ```
  Es el mismo párrafo, recorrido 1 letra cada vez.

**Qué hacía el código** ([src/chunker.py](../src/chunker.py), versión original):
```python
for sep in ["\n\n", "\n", ". ", " "]:
    idx = text.rfind(sep, start, end)      # último separador de ESE tipo en la ventana
    if idx > start:
        split_at = idx + len(sep); break
...
start = max(split_at - overlap, start + 1)
```

**Qué hicimos mal (la causa).** Fueron tres errores que juntos producen el bug:

1. **"Mejor separador" se definió por tipo, no por posición.** El loop toma el primer *tipo* de separador que exista en la ventana, aunque esté al principio. Si la ventana de 800 tiene un `\n\n` en el carácter 112 y un `\n` en el 790, gana el `\n\n` y el chunk queda de 114 caracteres. Asumimos sin darnos cuenta que los párrafos siempre miden menos de 800 caracteres, así que un `\n\n` siempre caería cerca del final. En la wiki eso no se cumple: hay listas y tablas largas sin línea en blanco (Death messages, Language, Mob spawning).
2. **El overlap se aplicó sin revisar que el chunk fuera más largo que el overlap.** El siguiente inicio es `corte − 150`. Si el chunk midió 114, ese inicio cae *antes* de donde empezamos. Para que no se quedara en un loop infinito se puso `max(..., start + 1)`, que convirtió el loop infinito en un avance de **1 carácter por iteración**. Cada iteración vuelve a encontrar el mismo `\n\n`, corta en el mismo punto y genera el mismo chunk con una letra menos. Se repite ~110 veces hasta que la ventana deja atrás ese salto. El guard evitó que el programa se colgara, pero escondió el error en vez de hacerlo visible.
3. **No había ninguna verificación del resultado.** Ni un test ni una regla de "chunks esperados ≈ caracteres / 650". Las señales estaban ahí: 113K chunks para 4 MB de texto, índice de 708 MB, ingest de 15 min, top-5 con el mismo título. Se leyeron como "corpus grande" y no como bug.

**Por qué rompía las respuestas.**
- Los artículos tipo lista se volvieron miles de vectores casi idénticos. En una búsqueda por similitud, un artículo con 2,000 copias aparece cerca de casi cualquier pregunta por pura cantidad. Por eso "Language" salía en preguntas de pociones.
- Cuando el artículo correcto sí llegaba, los 5 chunks eran el mismo pedazo repetido. El dedup del pipeline compara los primeros 60 caracteres y no los detecta, porque cada copia empieza una letra después. Así la receta, que estaba en otro pedazo del artículo, nunca le llegaba a Claude.
- Las versiones v4/v5 atacaron el síntoma más abajo en el pipeline: blocklist de títulos, title boost, score floor y ajustes de prompt. Ayudaron en el benchmark, pero el problema seguía en el índice.

**Fix.** Un corte solo es válido si cae en la segunda mitad de la ventana (`≥ start + chunk_size // 2`). Si el `\n\n` está antes, se prueba `\n`, luego `. `, luego espacio, y si nada sirve se corta duro en 800. Con eso cada chunk mide ≥400 caracteres y la ventana siempre avanza ≥250. Los tests en `tests/test_chunker.py` fijan las dos invariantes: el avance y un conteo razonable.

**Lección.** Antes de tunear retrieval (rerank, boosts, prompts), inspecciona los chunks: cuántos son, de qué tamaño y si se repiten.

**Resultado** (medido junto con #002 y las 9 páginas nuevas de redstone, misma corrida):

| Métrica | Baseline | Con fixes |
|---|---|---|
| Chunks en el índice | 113,584 | 7,619 |
| Tiempo de ingest | ~15 min | 2m43s |
| Fuente top-1 correcta | 14/27 (52%) | 18/27 (67%) |
| Términos esperados en la respuesta | 0.59 | 0.78 |
| Falsas abstenciones | 8 | 5 |
| Abstención correcta (negativas) | 3/3 | 3/3 |

Archivos: `data/benchmarks/results_baseline_*.json` vs `results_fixed_*.json`.

---

## 002 — Las recetas base de pociones nunca se guardaron

**Síntoma.** "¿Cómo hago una poción de velocidad?" → "La wiki no incluye la receta de brewing", aunque la fuente era *Potion of Swiftness*.

**Evidencia.** `data/wiki/Potion_of_Swiftness.txt` solo trae las recetas de splash y lingering. Falta `Sugar + Awkward Potion`. Solo 10 de los 1,039 archivos tienen alguna `Brewing recipe`.

**Qué hicimos mal.** El converter de [src/scraper.py](../src/scraper.py) se escribió suponiendo el formato `{{Brewing|ingrediente|base|resultado}}` (3 posicionales). La wiki real usa un parámetro con nombre:
```
{{Brewing
|head = 1
|Sugar
|base = Awkward Potion
|Potion of Swiftness
}}
```
En MediaWiki los parámetros con nombre (`head=`, `base=`) **no cuentan** en la numeración posicional. Por eso `1` = Sugar, `2` = Potion of Swiftness y `3` no existe. El converter leía la base del posicional `2` y el resultado del `3`; como `3` venía vacío, regresaba `""` y `strip_code()` borraba el template completo, sin ningún aviso.
Las splash/lingering sí pasaban porque traen 3+ posicionales, pero salían mal armadas: la base era una variante equivocada.

**Fix.** Si viene `base=`/`base1=`, esa es la base y el resultado es el posicional `2`. Si no viene, se mantiene el formato viejo. Hay que volver a bajar las páginas afectadas (`scrape_priority.py --refresh-matching brew`), porque el cache guarda texto ya limpio y no el wikitext original. Test en `tests/test_scraper.py`.

**Lección.** Un parser que falla regresando `""` sin avisar es invisible. Valida contra un ejemplo real del formato antes de confiar en él.

**Resultado.** Los archivos con `Brewing recipe` pasaron de 10 a 42 (77 páginas re-bajadas). `Potion_of_Swiftness.txt` ya trae `Sugar + Awkward Potion → Potion of Swiftness`. La mejora en respuestas está medida junto con #001.

---

## 003 — El re-ranker está ciego con preguntas en español

**Síntoma.** Después de #001/#002, 9 de 27 preguntas siguen fallando en la fuente top-1. Varios `top_score` son exactamente **0.3** o **0.2**.

**Evidencia.** Esos números son el `TITLE_BOOST` (0.3 × factor por largo del título) sumado a un score del cross-encoder de **0.000**. Prueba directa con el chunk de la receta del Hopper:

| Query al cross-encoder | Chunk receta Hopper | Chunk de otra receta |
|---|---|---|
| `¿Cómo hago una tolva?` | 0.000 | 0.000 |
| `How do I craft a hopper?` | 0.999 | 0.001 |

**Causa.** `cross-encoder/ms-marco-MiniLM-L-6-v2` solo se entrenó en inglés. En [src/pipeline.py](../src/pipeline.py) le pasamos la pregunta **original** (`rerank(question, ...)`), que viene en español, así que califica todo con ~0. El orden final lo decide entonces solo el title boost (#004). Desde la v3 el re-ranker no estaba aportando nada para usuarios en español; el benchmark viejo no lo detectaba porque solo medía el top-1.

**Opciones.**
- **A. Re-rankear con el máximo sobre todas las variantes** (original + reformulaciones). Es simple, pero las reformulaciones a veces traen ingredientes inventados por Haiku (#005) y puntuarían alto chunks equivocados. Costo: ~5x pares en el cross-encoder (~1 s más).
- **B. Pedirle a Haiku una traducción fiel al inglés y re-rankear con ella** (sin agregar ingredientes ni hechos). Toca el prompt del rewriter y el pipeline. Costo: ~0, es la misma llamada.
- **C. Cambiar a un cross-encoder multilingüe** (`mmarco-mMiniLMv2`). Implica ~470 MB de descarga (y Norton bloquea HF), más latencia y más complejidad.

**Decisión.** B (Rogelio). La #1 de Haiku es ahora una traducción fiel al inglés; el prompt prohíbe agregar ingredientes o datos. `rewrite_query` regresa `(queries, english)` y el pipeline re-rankea con `english`. Si Haiku falla, usa la traducción del glosario y luego la original.

**Resultado** (`results_rerank-en_*.json`). Se recalcularon las corridas previas con la métrica de #006:

| Métrica | Baseline | Fix #001/#002 | + rerank en inglés |
|---|---|---|---|
| Fuente top-1 correcta | 52% | 67% | **93%** (25/27) |
| Fuente en top-5 | 78% | 85% | **100%** |
| Términos esperados en la respuesta | 0.59 | 0.78 | **0.87** |
| Falsas abstenciones | 7 | 4 | **2** |
| Abstención correcta (negativas) | 3/3 | 3/3 | 3/3 |
| Latencia p50 | 6.4 s | 7.4 s | 6.9 s |

---

## 004 — El title boost premia artículos equivocados

**Síntoma.** "¿Cómo hago una tolva?" → top-5 = `Crafting` ×5. "¿Cómo crafteo un observer?" → `Redstone Dust` ×4.

**Causa.** [src/reranker.py](../src/reranker.py) suma el boost si el título aparece en **cualquier** variante, incluidas las reformulaciones libres de Haiku. Esas reformulaciones dicen "crafting recipe", "Redstone Dust" o "brewing stand", así que se impulsan los artículos *Crafting*, *Redstone Dust* y *Brewing Stand*. Con el re-ranker ciego (#003), ese boost es la única señal que queda.

**Opciones.** Limitar el boost a la pregunta original + la variante del glosario/traducción fiel, o bajarlo. Conviene decidir **después** de #003: con el cross-encoder funcionando, el boost pasa a ser solo un desempate.

**Decisión.** Se cerró dentro de #007: el boost se queda, sin recorte. Las reformulaciones ya no agregan ingredientes (#005) y el cross-encoder vuelve a ordenar.

---

## 005 — Haiku inventa ingredientes en las reformulaciones

**Evidencia.** "¿Cómo hago una poción de velocidad?" → reformulación `"Speed Potion brewing Fermented Spider Eye Awkward Potion"`. Fermented Spider Eye es incorrecto: la receta es Sugar. El prompt del rewriter incluso da como ejemplo `"Hopper crafting recipe Iron Ingots Chest"`, lo que invita a listar ingredientes de memoria.

**Impacto.** Trae chunks del ingrediente equivocado y alimenta #004. Se resuelve con la opción B de #003 si el prompt prohíbe agregar hechos.

---

## 006 — Ruido en la propia medición

- **Fuente top-1 es estricta.** En pistón, observer, dispensador y curación la respuesta es **correcta** (2/2 términos), pero el top-1 fue *Crafting* o *Redstone Dust* y cuenta como falla.
- **El detector de abstención marca respuestas parciales.** "Poción de fuerza" da la receta correcta (2/2) pero dice "no se menciona X" en otra parte, y se cuenta como abstención.
- **Algunos términos esperados están mal elegidos.** Para Redstone Torch esperaba "apag"; la respuesta dice "se desactiva".

**Decisión** (Rogelio): se agregó *fuente en top-5*, y la falsa abstención ahora cuenta solo si además faltan términos esperados. Las preguntas y los términos no se tocaron. Las corridas previas se recalcularon con `_summary` sobre sus JSON guardados.

**Ruido que queda** (no se corrige; se reporta):
- Repeater: la respuesta habla de "delay" y no menciona "tick".
- Redstone Torch: dice "se desactiva" y no "apaga"; además el top-1 es *Redstone circuits*.
- Brewing Stand: el top-1 es *Brewing*.

En los tres casos la respuesta es correcta.

---

## 007 — El boost recortado a 1.0 empata los mejores chunks

**Síntoma.** "¿Cómo hago un comparador de redstone?" y "¿Cómo hago un horno?" → "la wiki menciona una sección Crafting pero no los materiales", aunque la receta **sí** está en el cache.

**Evidencia.** Con la query en inglés, el cross-encoder pone el chunk de la receta en **#1 (0.999)**. Pero 7 chunks de *Redstone Comparator* tienen sigmoide ≥ 0.7, y con `min(1.0, score + 0.3)` los 7 quedan en **1.000**. Cuando 7 chunks empatan para 5 lugares, el desempate es el orden de llegada del bi-encoder, que varía con las reformulaciones de Haiku. A veces la receta entra y a veces no.

**Causa.** En [src/reranker.py](../src/reranker.py), `score = min(1.0, score + TITLE_BOOST * factor)`. El recorte se puso para que el score "se viera" como probabilidad, pero borra la información de orden justo en los chunks más relevantes. No se había notado porque, con el cross-encoder ciego (#003), todos los scores eran ~0 y nunca llegaban al tope.

**Opciones.**
- **A. Quitar el recorte**: el score queda en [0, 1.3]. Es una línea. El boost sigue subiendo el artículo correcto y el cross-encoder ordena dentro de él. El score floor (0.15) no cambia.
- **B. Quitar el title boost** (`TITLE_BOOST=0`, sin tocar código). Ahora que el cross-encoder funciona, quizá el boost ya no hace falta, y eso también resuelve #004.
- **C. Medir A y B** y decidir con números (~8 min, < $1 USD).

**Decisión parcial** (Rogelio): C. Se midieron las dos opciones (`results_A-noclip_*`, `results_B-noboost_*`):

| Métrica | Rerank EN (con recorte) | A: sin recorte | B: sin boost |
|---|---|---|---|
| Fuente top-1 | 93% | **96%** (26/27) | 89% (24/27) |
| Fuente top-5 | 100% | 100% | 100% |
| Términos esperados | 0.87 | 0.89 | **0.96** |
| Falsas abstenciones | 2 | 1 | 1 |
| Negativas | 3/3 | 3/3 | 3/3 |

Lectura: la diferencia entre A y B está dentro del ruido, porque las reformulaciones de Haiku cambian en cada corrida y mueven ±1-2 preguntas. B pierde el top-1 en "mesa de crafteo" y "splash" frente a artículos genéricos (*Crafting*, *Brewing*): el boost sirve para que la fuente citada sea el artículo específico. B acertó el comparador por suerte del candidato. Las fallas de receta que quedan no son del boost, son #008.

**Decisión final** (Rogelio): A. El boost se queda, sin recorte. #004 se cierra: con el cross-encoder funcionando, el boost ya no decide solo y el top-1 subió.

---

## 008 — La receta queda separada de su encabezado en otro chunk

**Síntoma.** "¿Cómo hago un comparador?" y "¿Cómo hago un horno?" → "existe una receta de crafteo pero no se detallan los materiales", aun con fuente top-1 correcta.

**Evidencia.** El texto que recibe Sonnet no trae la receta en ninguno de los 5 chunks. Así quedan los cortes:
```
Redstone_Comparator chunk 0: ... 'edstone lab in ancient cities.

Crafting'   ← termina en el encabezado
Redstone_Comparator chunk 1: receta en la posición 150, rodeada de "Natural generation" y placement
Furnace chunk 0:             ... 'Generated loot

Crafting'                    ← igual
Furnace chunk 1:             receta en la posición 149, rodeada de "village houses" y la interfaz
```
El chunk 0 dice "hay una sección Crafting" (de ahí la respuesta del modelo). El chunk 1 tiene la receta, pero su embedding habla de generación natural, así que ninguna query de crafteo lo trae.

**Causa.** El chunker corta por tamaño y no sabe de secciones. Al limpiar el wikitext se pierden los `== Encabezados ==`, así que la línea "Crafting" es texto común y puede quedar al final de un chunk, separada de su contenido. En todo el corpus hay **906 líneas de receta** expuestas a esto.

**Opciones.**
- **A. Chunks de receta dedicados.** En el ingest, cada línea `Crafting/Smelting/Brewing recipe:` se agrega además como un chunk propio con el título del artículo (`"Redstone Comparator — Crafting recipe: ..."`). Son +906 chunks (~12%), 3 min de re-ingest y no hace falta re-scrapear. Ataca directo el foco del proyecto: crafteos y pociones.
- **B. Encabezados contextuales en todos los chunks** (título + sección). Es la técnica estándar y ayuda a todas las preguntas, pero hay que conservar los encabezados en `clean_wikitext` y re-scrapear los 1,046 artículos (~25 min). Es más grande para mañana.
- **C. Solo el título como prefijo de cada chunk.** No requiere re-scrape y ayuda a ligar chunks con su artículo, pero no resuelve que la receta quede enterrada.

**Decisión** (Rogelio): A. `recipe_chunks()` en [src/ingest.py](../src/ingest.py) agrega 789 chunks de receta (ya deduplicados), con ids `<titulo>_r<i>` y `kind: "recipe"` en la metadata. Índice: 8,408 chunks. Test en `tests/test_ingest.py`.

**Resultado** (`results_recipe-chunks_*.json`): fuente top-1 96% (26/27), top-5 100%, términos 0.96, **0 falsas abstenciones**, negativas 3/3, p50 6.5 s. El comparador ("3 Redstone Torch + 1 Nether Quartz + 3 Stone") y el horno ("8 bloques de piedra con el centro vacío") ya responden bien.

**Ruido de etiquetado que queda** (no se corrige para no mover la vara):
- Brewing Stand: esperaba "Cobblestone", pero la wiki dice "Any stone-tier block" y la respuesta es correcta. El top-1 es *Brewing*.
- Repeater: la respuesta dice "delay" y no "tick".

---

## 009 — El cross-encoder no prefiere la receta cuando la query dice "make"

**Síntoma.** En la corrida de confirmación (`results_final-run2_*`), el comparador vuelve a responder "el contexto no incluye la receta". En la corrida anterior sí acertaba.

**Evidencia.**
- El bi-encoder **sí** trae el chunk de receta (posición #0 con la query en inglés).
- El cross-encoder lo baja según cómo Haiku redactó la traducción: con "How do I **make** a Redstone Comparator?" la receta queda en el **#10**; con "How do I **craft**..." queda en el **#2**.
- Logits del cross-encoder según el formato del chunk de receta:

| Query | Párrafo descriptivo | Formato actual | `How to make X (crafting): ...` |
|---|---|---|---|
| How do I make a Redstone Comparator? | 6.10 | 4.63 | **7.67** |
| How do I craft a Redstone Comparator? | 4.74 | 6.39 | **7.66** |
| What ingredients do I need for...? | 1.98 | 4.74 | **5.12** |

**Causa.** `ms-marco` se entrenó con pasajes web que responden preguntas. Una lista seca ("Redstone Torch, Redstone Torch, Nether Quartz...") le parece peor respuesta a "how do I make" que un párrafo que describe el bloque. Además, varios chunks del artículo saturan en ~0.999, así que diferencias chicas de redacción deciden el top-5. Haiku alterna entre "make" y "craft" de una corrida a otra, de ahí la variación.

**Opciones.**
- **A. Redactar el chunk de receta como respuesta**: `"How to make a Redstone Comparator (crafting): Crafting recipe: ..."`. Es una línea en `recipe_chunks()` + re-ingest de 3 min. En la prueba gana con las 3 redacciones.
- **B. Lugar garantizado para la receta**: si el artículo top tiene un chunk de receta entre los candidatos y no quedó en el top-k, se agrega al contexto (k+1). Es más robusto ante cualquier redacción, pero son ~10 líneas en el pipeline y un chunk extra en algunas preguntas.
- **A + B**: lo más robusto, con más código.

**Decisión** (Rogelio): A. `recipe_chunks()` ahora redacta `"How to make <producto> (<método>): <receta>"`. El producto sale de lo que va después de `→`, para que en la página de Sugar la receta diga "How to make Potion of Swiftness". Test en `tests/test_ingest.py`.

---

## 010 — Hueco en el glosario: "soporte para pociones"

**Evidencia.** El glosario tiene `"soporte de pociones"` pero no `"soporte para pociones"`, que es el nombre oficial en español. Sin el glosario, Haiku lo tradujo como *"Potion Cauldron"*, y el contexto completo fue del Cauldron → "no tengo esa información".

**Opción.** Agregar `"soporte para pociones": "Brewing Stand"` a [src/mc_glossary.py](../src/mc_glossary.py). No cuesta nada y es determinístico.

**Decisión** (Rogelio): agregado. Ojo: este fix salió de una pregunta del propio eval set (ver la nota de sobreajuste abajo).

---

## Resultado final

Dos corridas seguidas con todo aplicado (`results_final-1_*`, `results_final-2_*`):

| Métrica | Baseline | Final |
|---|---|---|
| Fuente top-1 correcta | 52% | **100%** (27/27 en ambas) |
| Fuente en top-5 | 78% | **100%** |
| Términos esperados en la respuesta | 0.59 | **0.89 – 0.94** |
| Falsas abstenciones | 7/27 | **0/27** |
| Negativas bien rechazadas | 3/3 | 3/3 |
| Chunks en el índice | 113,584 | 8,408 |
| Latencia p50 | 6.4 s | 6.4 – 6.8 s |

Términos que aún faltan:
- Casi todos son de etiquetado, con respuestas correctas: "bloques de piedra de cualquier tipo" vs "Cobblestone", "delay" vs "tick", "se desactiva" vs "apag".
- La única respuesta parcial real es la de la poción de debilidad, que no menciona la Golden Apple.

**Sobreajuste.** Este eval set se usó para *encontrar* los bugs, así que no es un test independiente. Los fixes #001, #002, #003, #007, #008 y #009 son generales: arreglan mecanismos, no preguntas. El #010 (glosario) sí salió de una pregunta concreta. Con preguntas nuevas hay que esperar números más bajos. Siguiente paso recomendado: un segundo set de ~20 preguntas que no se use para tunear.

---

## 011 — El scraper no entra a subcategorías: casi no hay mobs, biomas ni estructuras

**Síntoma.** Rogelio preguntó si se puede preguntar por el Ender Dragon. No está en el corpus, y tampoco el Creeper, el Wither, el Zombie, el Enderman, el Nether, el End ni ninguna estructura.

**Evidencia.**

| Categoría | Artículos en el corpus |
|---|---|
| Blocks | 462 |
| Items | 296 |
| Gameplay | 127 |
| Priority | 84 |
| Enchantments | 36 |
| Potions | 24 |
| **Mobs** | **12** |
| **Biomes** | **3** |
| Redstone circuits | 2 |

Los 12 "mobs" son páginas generales (*Mob*, *Boss*, *Undead*…). En la wiki, `Category:Mobs` tiene 13 páginas y **27 subcategorías** (*Hostile mobs*, *Boss mobs*…), y ahí viven los mobs reales.

**Causa.** `fetch_category()` ([src/scraper.py](../src/scraper.py)) solo procesa las páginas directas (namespace 0) y descarta las subcategorías sin avisar. Además, varias categorías de `CATEGORIES` en `scrape_wiki.py` no existen en la wiki (`Mechanics`, `Redstone components`, `Utility blocks`, `Farming`) y regresaron 0 artículos sin error. También faltan 5 páginas prioritarias que en realidad son redirects (ej. `Enchanting`, `Hunger`), y `_process_page()` también las descarta en silencio.

**Lo que falta, contado en la API de la wiki:**

| Subcategoría | Páginas |
|---|---|
| Hostile mobs | 46 |
| Passive mobs | 41 (3 ya están) |
| Neutral mobs | 20 |
| Boss mobs | 2 (Ender Dragon, Wither) |
| Generated structures | 41 |
| Dimensions | 9 |
| Overworld biomes | 59 |
| Nether biomes | 5 |
| End biomes | 5 |

En total son **~220 páginas**: ~4-5 min de scrape a 1 req/s y ~4 min de re-ingest.

**Decisión.** _(pendiente — Rogelio)_

---

## 012 — Desbloquear artículos legítimos de la blocklist

**Contexto.** La blocklist de v5 bloqueaba Cake, Cactus, Banner, Fluid, Cooking y Player como "ruido". En realidad dominaban por el bug del chunker (#001), así que "¿cómo hago un pastel?" nunca podía encontrar *Cake*.

**Decisión** (Rogelio): desbloquear esos 6 artículos. Language, Death messages, Biome/Before*, April Fools, easter eggs y meta-páginas siguen bloqueados. Se agregaron 2 preguntas al eval (pastel y estandarte); ahora son 32.

**Resultado** (`results_blocklist-clean_*.json`):
- Fuente top-1: **29/29**. "¿Cómo hago un pastel?" → *Cake*, con la receta completa (3 Milk Bucket, 2 Sugar, Egg, 3 Wheat). "¿Cómo hago un estandarte?" → *Banner*, con 6 de lana y 1 Stick.
- Fuente en top-5: 100%. Términos esperados: 0.91. Falsas abstenciones: 0. Negativas: 3/3. Latencia p50: 6.5 s.
- No hubo regresiones en las 27 preguntas anteriores.

---

## Pendientes (actualizado 2026-10-11)

Estado: `main` está pusheado a GitHub (`argomezflores/minecraft-rag`) con todo lo de v6. Docs actualizados a v6: `README.md`, este log, `docs/pipeline.html` y `docs/timeline.html`.

1. **Visibilidad.** Confirmar que el repo está en **Public** (Settings → Danger Zone). Al hacerlo público, el email `argomezflores@gmail.com` queda visible en el User-Agent (`.env.example`, `src/config.py`, notebook). Opción: cambiarlo por la URL del repo, que la wiki también acepta como contacto.
2. **`ipykernel` fuera de `requirements.txt`.** La app no lo usa (solo el notebook), y su dependencia `debugpy` tiene rutas tan largas que `pip install` falló en Windows al clonar en una carpeta anidada. Moverlo a `requirements-notebook.txt`.
3. **Ejemplo `curl` del README.** Tiene acentos ("¿Cómo…poción") y da 400 desde Git Bash en Windows por la codificación. Cambiarlo por una pregunta sin acentos o agregar un ejemplo de PowerShell.
4. ~~**Blocklist**~~ ✅ hecho, ver #012.
5. **Docs desactualizados.** `docs/GUIDE.md` sigue en v5: dice ~800 artículos, re-rank con la pregunta original, CC BY-SA y no menciona el eval. Actualizarlo con lo de v6. `docs/guide.html` es una copia vieja (v2-v3) de `GUIDE.md` que nada enlaza: borrarla.
6. **Capturas** del widget y del bot in-game → `docs/img/`, enlazadas desde el README (las toma Rogelio).
7. **CV.** Falta corregir la fecha: el proyecto es de ago 2026, no de ene 2026. Bullets propuestos con los números finales:
   > **Minecraft Knowledge Assistant (RAG)** · Python, FastAPI, ChromaDB, Claude API · github.com/argomezflores/minecraft-rag
   > - Built a from-scratch RAG pipeline (no LangChain) over 1,000+ Minecraft Wiki articles that answers Spanish gameplay questions with cited sources, through a REST API, a web widget and an in-game bot.
   > - Designed an evaluation harness that exposed five root-cause bugs, among them a chunker that duplicated text 19× and an English-only re-ranker that was blind to Spanish queries. Fixing them raised top-1 retrieval accuracy from 52% to 100% on a 27-question dev set and cut false "not found" answers from 7 to 0.
   > - Reduced the vector index from 113K to 8.4K chunks and indexing time from ~15 to ~3 minutes.

   En entrevista, decir que el 100% es sobre el dev set y no sobre un test independiente.
8. **Cobertura (#011):** decidir si se agregan mobs, jefes, estructuras, dimensiones y biomas (~220 páginas), si el scraper debe recorrer subcategorías, y arreglar los redirects de las páginas prioritarias.
9. **Opcional, después del CV:**
   - Un eval set **independiente** de ~20 preguntas que no se use para tunear.
   - Docker de un comando (el compose está corregido pero sin probar).
   - pytest en GitHub Actions.
   - Upgrade de modelos.
