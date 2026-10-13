"""
pipeline.py — Orquestador único del pipeline RAG completo.

Este módulo une todas las capas en una sola función: `answer_question()`.
Es el ÚNICO lugar donde se decide "cuándo aplicar qué mejora" (query rewriting,
re-ranking) — así el API y los CLIs no duplican esa lógica.

Flujo:
  1. Query rewriting (opcional, controlado por env QUERY_REWRITE)
     → 1 o 3 variaciones de la pregunta
  2. Retrieval con cada variación (top-N cada una, dedup)
     → pool de ~20-60 candidatos únicos
  3. Re-ranking (opcional, controlado por env RERANK)
     → top-K final ordenado por relevancia fina
  4. Generation con Claude Sonnet
     → respuesta en español con citas

Ambos pasos opcionales tienen fallback silencioso: si algo falla, degradan
al comportamiento base (query original + top-K por bi-encoder). El pipeline
sigue respondiendo, solo con menos calidad.
"""

from typing import Literal, TypedDict

from src.config import QUERY_REWRITE, RERANK, RETRIEVAL_TOP_N, TOP_K, MIN_ACCEPTABLE_SCORE
from src.query_rewriter import rewrite_query
from src.retriever import search, Hit
from src.reranker import rerank
from src.generator import generate_answer
from src.smalltalk import smalltalk_reply


# 📚 Respuesta canónica cuando ningún chunk supera el score floor.
# Le decimos al user cómo mejorar su query (usar nombre en inglés).
LOW_CONFIDENCE_ANSWER = (
    "No encontré información específica sobre eso en la wiki. Puede que el artículo "
    "no esté indexado en este corpus, o que la pregunta sea muy ambigua. "
    "Intenta con el nombre exacto en inglés (ej. 'Hopper', 'Beacon', 'Fortune', "
    "'Netherite')."
)


class PipelineResult(TypedDict):
    question: str
    answer: str
    sources: list[Hit]
    rewrites: list[str]     # Variaciones usadas para el retrieval
    debug: dict              # Info de latencia/counts para telemetría


def _merge_dedupe(hit_lists: list[list[Hit]]) -> list[Hit]:
    """
    Combina resultados de múltiples queries y elimina duplicados.

    📚 Dedup por (title + primeros 60 chars del texto) — es suficiente para
    detectar el mismo chunk que apareció en varias variaciones. Preservamos
    orden: los primeros hits (mejor score) quedan al frente.
    """
    seen: set[tuple[str, str]] = set()
    merged: list[Hit] = []
    for hits in hit_lists:
        for h in hits:
            key = (h.title, h.text[:60])
            if key in seen:
                continue
            seen.add(key)
            merged.append(h)
    return merged


def answer_question(
    question: str,
    k: int = TOP_K,
    format: Literal["full", "chat"] = "full",
) -> PipelineResult:
    """
    Pipeline RAG completo. Punto de entrada único para la API y CLIs.

    - `question`: pregunta original del usuario (en cualquier idioma).
    - `k`: cuántos chunks finales devolver al LLM (default TOP_K=5).
    - `format`: "full" (widget web, markdown) o "chat" (bot in-game, texto plano corto).
    """
    debug: dict = {}

    # --- Paso 0: saludos / ayuda / gracias → respuesta fija, sin RAG ($0) ---
    reply = smalltalk_reply(question, format=format)
    if reply:
        return PipelineResult(
            question=question,
            answer=reply,
            sources=[],
            rewrites=[question],
            debug={"short_circuit": "smalltalk"},
        )

    # --- Paso 1: Query rewriting (opcional) ---
    if QUERY_REWRITE:
        queries, rerank_query = rewrite_query(question)
    else:
        queries, rerank_query = [question], question
    debug["rewrites_used"] = len(queries)
    debug["rerank_query"] = rerank_query

    # --- Paso 2: Retrieval ---
    # 📚 Si vamos a re-rankear, casteamos red amplia (top-N por query).
    # Si no, solo pedimos K directo (no tiene sentido pedir más para tirar).
    per_query_k = RETRIEVAL_TOP_N if RERANK else k
    raw_lists = [search(q, k=per_query_k) for q in queries]
    candidates = _merge_dedupe(raw_lists)
    debug["candidates_after_dedup"] = len(candidates)

    # --- Paso 3: Re-ranking (opcional) ---
    if RERANK and candidates:
        # 📚 Re-rankeamos con la TRADUCCIÓN FIEL al inglés, no con la original:
        # el cross-encoder (ms-marco) solo entiende inglés y con español
        # puntuaba todo ~0 (docs/eval-log.md #003). La traducción fiel conserva
        # la intención real sin los ingredientes que Haiku inventa en las otras variantes.
        # 📚 v5: pasamos también las reformulaciones al boost por título — así
        # queries en español activan el boost del artículo en inglés (via glosario).
        hits = rerank(rerank_query, candidates, top_k=k, boost_queries=queries)
    else:
        hits = candidates[:k]
    debug["final_hits"] = len(hits)

    # --- Paso 3.5 (v5): Score floor + respuesta honesta ---
    # 📚 Si el mejor score es tan bajo que el LLM va a generar "no tengo info"
    # de todos modos, cortocircuiteamos: ahorramos $$$ (llamada Sonnet) y ~2-3s.
    top_score = hits[0].score if hits else 0.0
    debug["top_score"] = top_score
    if top_score < MIN_ACCEPTABLE_SCORE:
        debug["short_circuit"] = "low_confidence"
        return PipelineResult(
            question=question,
            answer=LOW_CONFIDENCE_ANSWER,
            sources=hits,
            rewrites=queries,
            debug=debug,
        )

    # --- Paso 4: Generation ---
    answer = generate_answer(question, hits, format=format)

    return PipelineResult(
        question=question,
        answer=answer,
        sources=hits,
        rewrites=queries,
        debug=debug,
    )
