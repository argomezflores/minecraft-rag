"""
reranker.py — Re-ordena los chunks recuperados por relevancia semántica fina.

Concepto RAG: los embeddings (bi-encoder) son rápidos pero imprecisos —
comparan vectores INDEPENDIENTES. El embedding de la query no "sabe" nada
sobre el embedding del chunk, se calculan por separado y comparamos distancias.

El cross-encoder es distinto: toma (query, chunk) COMO PAR y produce un score
de relevancia. Mucho más preciso, pero más lento (por eso solo lo corremos
sobre los top-N candidatos del bi-encoder, no sobre 85k chunks).

Arquitectura estándar (desde 2021):
  1. Bi-encoder (rápido): busca en 85k chunks, devuelve top-20 candidatos.
  2. Cross-encoder (preciso): re-puntúa esos 20 y devuelve top-5 final.

🆕 v5: title boost. Si el título del artículo aparece como substring en la
query (o en cualquiera de sus variaciones), sumamos TITLE_BOOST al score final.
Esto asegura que "cómo hago un hopper" traiga el artículo Hopper al top.
"""

import re
from functools import lru_cache
from math import exp
from sentence_transformers import CrossEncoder

from src.config import RERANK_MODEL, TITLE_BOOST
from src.retriever import Hit


@lru_cache(maxsize=1)
def get_reranker() -> CrossEncoder:
    """
    Carga el cross-encoder una sola vez por proceso (evita reload en cada query).

    📚 Primera llamada: descarga ~90MB de HuggingFace (~15s).
    Siguientes llamadas: instantáneo (retorna del caché).
    """
    print(f"[reranker] Cargando cross-encoder {RERANK_MODEL}...")
    model = CrossEncoder(RERANK_MODEL)
    print("[reranker] Modelo listo.")
    return model


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + exp(-x))


def _title_matches_query(title: str, queries: list[str]) -> tuple[bool, float]:
    """
    Retorna (matched, boost_factor) para el título dado.

    - Requiere ≥5 chars y word boundary (evita que "Smelting" en la frase
      "for smelting ores" boost el artículo Smelting).
    - El boost_factor es proporcional a la longitud del título: títulos más
      específicos ("Potion of Swiftness") ganan sobre genéricos ("Potion")
      cuando ambos aparecen en la query.
    """
    if not title or len(title) < 5:
        return False, 0.0
    title_lower = title.lower()
    pattern = re.compile(r"\b" + re.escape(title_lower) + r"\b", re.IGNORECASE)
    matched = any(pattern.search(q) for q in queries)
    if not matched:
        return False, 0.0
    factor = min(1.0, len(title) / 12.0)
    return True, factor


def rerank(
    query: str,
    hits: list[Hit],
    top_k: int = 5,
    boost_queries: list[str] | None = None,
) -> list[Hit]:
    """
    Re-ordena `hits` por relevancia semántica fina, devuelve los top_k mejores.

    - `query`: pregunta ORIGINAL del usuario (para el cross-encoder).
    - `hits`: candidatos del bi-encoder (típicamente ~20-40 chunks).
    - `top_k`: cuántos devolver al final (típicamente 5).
    - `boost_queries` (v5): lista de queries donde buscar títulos como substring
      para aplicar TITLE_BOOST. Típicamente incluye la original + rewrites.
      Si es None, usamos solo `[query]`.
    """
    if not hits:
        return []

    reranker = get_reranker()

    # 📚 El cross-encoder espera pares [(query, doc), (query, doc), ...].
    # Devuelve un logit por par (más alto = más relevante).
    pairs = [(query, hit.text) for hit in hits]
    scores = reranker.predict(pairs)

    # 📚 Aplicamos sigmoide para llevar los logits a [0, 1] (más intuitivo).
    # Después aplicamos TITLE_BOOST aditivo si el título aparece en las queries.
    queries_for_boost = boost_queries or [query]

    boosted = []
    for hit, logit in zip(hits, scores):
        score = _sigmoid(float(logit))
        matched, factor = _title_matches_query(hit.title, queries_for_boost)
        if matched:
            # 📚 Sin recorte a 1.0: con min(1.0, ...) los mejores chunks de un
            # artículo empataban y se perdía el orden fino (docs/eval-log.md #007).
            score = score + TITLE_BOOST * factor
        boosted.append((hit, score))

    # 📚 Ordenamos por score final (sigmoide + boost) descendente.
    boosted.sort(key=lambda pair: pair[1], reverse=True)

    return [
        Hit(
            text=h.text,
            title=h.title,
            url=h.url,
            category=h.category,
            score=round(s, 3),
        )
        for h, s in boosted[:top_k]
    ]
