"""
query_rewriter.py — Reformula la pregunta del usuario en múltiples variaciones.

Concepto RAG: los embeddings comparan la query contra los chunks vector-a-vector.
Si la query es corta o está en otro idioma que el corpus, muchas veces "no
encuentra" chunks relevantes aunque el contenido exista.

Solución: pedirle a un LLM rápido (Claude Haiku) que reformule la query en
3 variaciones distintas. Cada una captura un ángulo semántico distinto.
Después el retriever busca con las 3 y hacemos merge.

🆕 v4: además de las variaciones de Haiku, agregamos una variación GARANTIZADA
proveniente del diccionario manual ES→EN (src/mc_glossary.py). Esto asegura
que "tolva" siempre tenga "Hopper" en sus variaciones, sin depender de que
Haiku acierte cada vez.

Ejemplo:
  Input:  "cómo crafteo una tolva"
  Output: [
    "cómo crafteo una tolva",                          # original
    "¿Cómo se craftea un Hopper y para qué sirve?",     # rewrite Haiku 1
    "Hopper crafting recipe iron ingots",               # rewrite Haiku 2
    "cómo crafteo un Hopper",                           # 🆕 glosario ES→EN garantizado
  ]
"""

import json
import re

# 📚 truststore usa los certs nativos del OS. Sin esto, en Windows el SDK
# de anthropic (que usa httpx) puede fallar con SSLCertVerificationError.
import truststore
truststore.inject_into_ssl()

from anthropic import Anthropic

from src.config import ANTHROPIC_API_KEY, HAIKU_MODEL
from src.mc_glossary import translate_es_terms


_REWRITE_PROMPT = """Eres un asistente que reformula preguntas de jugadores de Minecraft para mejorar la búsqueda en la wiki oficial (en inglés).

Tu tarea: dado una pregunta, genera exactamente 3 REFORMULACIONES ÚTILES:
1. Una versión clara y directa (puede estar en español).
2. Una versión TÉCNICA en INGLÉS que USE NOMBRES OFICIALES de Minecraft (ej. "Hopper" no "tolva", "Anvil" no "yunque", "Diamond Pickaxe" no "pico de diamante", "Redstone Repeater" no "repetidor").
3. Una versión que enfatice un ángulo específico (mecánicas relacionadas, stats, crafting recipe), preferentemente en inglés.

Reglas ESTRICTAS:
- Devuelve SOLO un JSON array con 3 strings. Nada más. Sin explicaciones. Sin markdown.
- USA nombres oficiales en INGLÉS de Minecraft (Diamond Pickaxe, Redstone Repeater, Nether Wart, Hopper, Anvil, etc.).
- La variación #2 SIEMPRE en inglés puro con nombres oficiales.
- No repitas frases idénticas.

Ejemplo entrada: "cómo crafteo una tolva"
Ejemplo salida: ["¿Cómo se craftea un Hopper en Minecraft?", "Hopper crafting recipe Iron Ingots Chest", "How to make a Hopper for item transport"]"""


def _extract_json_array(text: str) -> list[str] | None:
    """Extrae el primer JSON array del texto (tolera markdown fences o texto extra)."""
    match = re.search(r"\[[\s\S]*?\]", text)
    if not match:
        return None
    try:
        arr = json.loads(match.group(0))
        if isinstance(arr, list) and all(isinstance(x, str) for x in arr):
            return arr
    except json.JSONDecodeError:
        return None
    return None


def rewrite_query(question: str, n: int = 3) -> list[str]:
    """
    Devuelve una lista de queries: la original + reformulaciones + variación del glosario.

    Flujo:
    1. Query original (siempre incluida).
    2. Variaciones de Claude Haiku (hasta N).
    3. 🆕 Variación GARANTIZADA del glosario ES→EN si detectamos términos españoles.

    Si Haiku falla, seguimos teniendo original + glosario (fallback robusto).
    """
    # 📚 Siempre incluimos la original como primer elemento.
    seen = {question.lower().strip()}
    result = [question]

    # --- Paso 1: variaciones dinámicas de Haiku ---
    if ANTHROPIC_API_KEY:
        try:
            client = Anthropic(api_key=ANTHROPIC_API_KEY)
            response = client.messages.create(
                model=HAIKU_MODEL,
                max_tokens=300,
                system=_REWRITE_PROMPT,
                messages=[{"role": "user", "content": question}],
            )
            text = response.content[0].text.strip()
            rewrites = _extract_json_array(text)
            if rewrites:
                for r in rewrites[:n]:
                    key = r.lower().strip()
                    if key and key not in seen:
                        result.append(r)
                        seen.add(key)
        except Exception as e:
            print(f"[query_rewriter] fallback Haiku (error: {e})")

    # --- Paso 2: variación garantizada del glosario ES→EN ---
    # 📚 Esto asegura que "tolva" siempre tenga "Hopper" en las variaciones,
    # aunque Haiku no lo haya hecho (o haya fallado por completo).
    translated, detected = translate_es_terms(question)
    if detected and translated.lower().strip() not in seen:
        result.append(translated)
        seen.add(translated.lower().strip())
        print(f"[query_rewriter] glosario aplicado: {', '.join(detected)}")

    return result
