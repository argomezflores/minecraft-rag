"""
embedder.py — Convierte texto en vectores numéricos (embeddings).

Concepto RAG: un embedding es una representación numérica del *significado*
de un texto. Textos con significado similar tienen vectores cercanos en el
espacio (medido con cosine similarity o distancia euclidiana).

Usamos `sentence-transformers` que corre localmente (sin API externa) con
un modelo multilingüe. Para "el patrón debe pagar cuotas al IMSS" y
"aportaciones patronales de seguridad social" el modelo genera vectores
cercanos porque significan cosas parecidas.
"""

import ssl
import truststore
from functools import lru_cache

# 📚 truststore inyecta los certificados nativos de Windows/macOS al SSL de Python.
# Sin esto, huggingface_hub falla con SSLCertVerificationError al descargar modelos.
truststore.inject_into_ssl()

from sentence_transformers import SentenceTransformer

from src.config import EMBEDDING_MODEL


# 📚 lru_cache asegura que el modelo se cargue UNA sola vez por proceso.
# Cargar el modelo tarda ~3 segundos y usa ~500MB de RAM.
@lru_cache(maxsize=1)
def get_model() -> SentenceTransformer:
    print(f"[embedder] Cargando modelo {EMBEDDING_MODEL}...")
    model = SentenceTransformer(EMBEDDING_MODEL)
    print(f"[embedder] Modelo listo. Dim: {model.get_sentence_embedding_dimension()}")
    return model


def embed_texts(texts: list[str], batch_size: int = 32) -> list[list[float]]:
    """
    Convierte una lista de textos en una lista de vectores (list[float]).

    Batch size 32 es un balance: más grande = más rápido pero más RAM.
    En CPU con 500 chunks tarda ~10 seg.
    """
    model = get_model()
    # 📚 normalize_embeddings=True hace que los vectores tengan norma 1.
    # Esto permite usar producto punto como equivalente a cosine similarity,
    # que es más rápido de computar en ChromaDB.
    vectors = model.encode(
        texts,
        batch_size=batch_size,
        show_progress_bar=len(texts) > 50,
        normalize_embeddings=True,
    )
    return vectors.tolist()


def embed_query(text: str) -> list[float]:
    """Embedding de una sola query. Interfaz simple para el retriever."""
    return embed_texts([text])[0]
