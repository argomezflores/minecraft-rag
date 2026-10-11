"""
retriever.py — Búsqueda semántica: query → top-K chunks más relevantes.

Concepto RAG: cuando llega una pregunta del usuario, la convertimos a un
embedding y le pedimos a ChromaDB los K vectores más cercanos (medida:
cosine similarity). Esos chunks son los que le pasaremos al LLM como
contexto para que genere la respuesta.

Devolvemos también el score y metadata para poder mostrarle al usuario
de dónde salió la información (link a la wiki).

🆕 v5: filtrado post-retrieval con blocklist de artículos "ruido"
(Language, Death messages, Biome/Before*, April Fools, etc.) detectados en logs reales.
Ver src/corpus_filters.py para la lista completa.
"""

from typing import NamedTuple
import chromadb

from src.config import CHROMA_PATH, COLLECTION_NAME, TOP_K
from src.embedder import embed_query
from src.corpus_filters import is_blocked


class Hit(NamedTuple):
    text: str
    title: str        # 📚 Nombre del artículo (ej. "Diamond Pickaxe")
    url: str          # 📚 URL a la wiki para linkear la fuente
    category: str     # 📚 Categoría (Items, Blocks, Mobs, etc.) — útil para filtrar
    score: float      # 📚 0.0-1.0, más alto = más similar


def _get_collection():
    client = chromadb.PersistentClient(path=str(CHROMA_PATH))
    return client.get_collection(name=COLLECTION_NAME)


# 📚 Factor multiplicador para pedir más resultados a Chroma y compensar
# los que serán filtrados por la blocklist. 3x es conservador — casi nunca
# más del 30% de los top-N caen en la blocklist.
_OVERFETCH_FACTOR = 3


def search(query: str, k: int = TOP_K) -> list[Hit]:
    """Devuelve los K chunks más relevantes para la query, filtrando ruido."""
    # 📚 1) Convertimos la query en el mismo espacio vectorial que los chunks.
    q_vec = embed_query(query)

    # 📚 2) Pedimos MÁS de lo necesario para tener margen tras el filtrado
    # por blocklist. Si los top-K resultantes son basura, tenemos backup.
    overfetch_k = max(k * _OVERFETCH_FACTOR, k + 15)

    collection = _get_collection()
    results = collection.query(
        query_embeddings=[q_vec],
        n_results=overfetch_k,
        include=["documents", "metadatas", "distances"],
    )

    # 📚 3) Convertimos distancia coseno → score de similitud [0, 1].
    docs = results["documents"][0]
    metas = results["metadatas"][0]
    dists = results["distances"][0]

    all_hits: list[Hit] = []
    for doc, meta, dist in zip(docs, metas, dists):
        title = meta.get("title", "?")
        # 📚 4) FILTRO v5: si el artículo está en la blocklist, lo descartamos.
        # is_blocked() chequea títulos exactos + patrones regex.
        if is_blocked(title):
            continue
        all_hits.append(Hit(
            text=doc,
            title=title,
            url=meta.get("url", ""),
            category=meta.get("category", ""),
            score=round(1.0 - (dist / 2.0), 3),
        ))
        if len(all_hits) >= k:
            break

    return all_hits[:k]
