"""
ingest.py — Pipeline offline: artículos de wiki → chunks → embeddings → ChromaDB.

Concepto RAG: la fase de "indexado". Corre una sola vez (o cada vez que
cambia el corpus). Todo el trabajo pesado (chunking, embeddings) se hace
aquí para que las queries en runtime sean rápidas.

Flujo:
  1. Recorre todos los .txt en data/wiki/
  2. Carga cada artículo con su metadata (título, categoría, URL)
  3. Divide el texto en chunks
  4. Genera embeddings en batch
  5. Guarda en ChromaDB con metadata (título, url, categoría, chunk index)
"""

from pathlib import Path
import chromadb

from src.config import (
    WIKI_PATH,
    CHROMA_PATH,
    COLLECTION_NAME,
    CHUNK_SIZE,
    CHUNK_OVERLAP,
)
from src.scraper import load_article, safe_filename, WikiArticle
from src.chunker import split_text
from src.embedder import embed_texts


def get_collection(reset: bool = False):
    """Devuelve la colección de ChromaDB. Si reset=True, la borra primero."""
    # 📚 PersistentClient guarda a disco (data/chroma). Sobrevive reinicios.
    client = chromadb.PersistentClient(path=str(CHROMA_PATH))

    if reset:
        try:
            client.delete_collection(COLLECTION_NAME)
            print(f"[ingest] Colección '{COLLECTION_NAME}' eliminada.")
        except Exception:
            pass  # 📚 No existe todavía, todo bien.

    # 📚 metadata={"hnsw:space": "cosine"} le dice a Chroma que use
    # cosine similarity para las búsquedas (mejor para texto que L2).
    return client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )


def ingest_article(article: WikiArticle, collection) -> int:
    """Ingesta un artículo. Devuelve el número de chunks agregados."""
    chunks = split_text(article.text, CHUNK_SIZE, CHUNK_OVERLAP)
    if not chunks:
        return 0

    # 📚 ID único e idempotente: si re-ingestas el mismo artículo,
    # los chunks se sobrescriben en lugar de duplicarse.
    ids = [f"{safe_filename(article.title)}_c{i}" for i in range(len(chunks))]

    # 📚 Metadata útil para citar la fuente y filtrar por categoría.
    metas = [
        {
            "title": article.title,
            "category": article.category,
            "url": article.url,
            "chunk_index": i,
        }
        for i in range(len(chunks))
    ]

    embeddings = embed_texts(chunks)

    # 📚 upsert = insert-or-update. Si el ID ya existe, lo reemplaza.
    collection.upsert(
        ids=ids,
        documents=chunks,
        embeddings=embeddings,
        metadatas=metas,
    )
    return len(chunks)


def ingest_all(reset: bool = False) -> None:
    """Ingesta todos los artículos de wiki en WIKI_PATH."""
    files = sorted(WIKI_PATH.glob("*.txt"))
    if not files:
        print(f"[ingest] ⚠️  No hay artículos en {WIKI_PATH}")
        print("  Corre primero: python scripts/scrape_wiki.py")
        return

    print(f"[ingest] Encontrados {len(files)} artículos en {WIKI_PATH}")
    collection = get_collection(reset=reset)

    total = 0
    for i, txt in enumerate(files, start=1):
        article = load_article(txt)
        n = ingest_article(article, collection)
        total += n
        if i % 25 == 0 or i == len(files):
            print(f"  [progress] {i}/{len(files)} artículos, {total} chunks totales")

    print(f"\n[ingest] ✅ Terminado. {total} chunks en '{COLLECTION_NAME}'.")
    print(f"[ingest] Chunks en colección: {collection.count()}")
