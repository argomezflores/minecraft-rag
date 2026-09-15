"""
config.py — Configuración centralizada del sistema RAG.

Concepto: mantener todos los "números mágicos" (chunk size, top-K, modelo)
y rutas en un solo lugar. Así cambias comportamiento sin buscar por el código.
Los valores vienen de variables de entorno (.env) con defaults sensatos.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# 📚 Base path del proyecto — todo se resuelve relativo a esto.
BASE_DIR = Path(__file__).resolve().parent.parent

# --- LLM (generación) ---
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-5-20250929")

# 📚 Modelo rápido para tareas auxiliares (query rewriting): 10x más barato,
# 3x más rápido que Sonnet. Suficiente para reformular preguntas.
HAIKU_MODEL = os.getenv("HAIKU_MODEL", "claude-haiku-4-5-20251001")

# --- Embeddings ---
# 📚 Modelo en INGLÉS puro: la Minecraft Wiki está en inglés, y modelos
# monolingües rinden mejor que multilingües en su idioma nativo.
# 384 dimensiones, local, rápido, gratis.
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")

# --- Vector store (ChromaDB) ---
CHROMA_PATH = BASE_DIR / os.getenv("CHROMA_PATH", "data/chroma").replace("./", "")
COLLECTION_NAME = os.getenv("COLLECTION_NAME", "minecraft")

# --- Wiki cache (reemplaza PDFs) ---
WIKI_PATH = BASE_DIR / os.getenv("WIKI_PATH", "data/wiki").replace("./", "")

# --- Query log (JSONL append-only) ---
# 📚 Cada request a /query se guarda como una línea JSON aquí.
# Usado por scripts/benchmark.py para métricas objetivas del sistema.
LOG_PATH = BASE_DIR / os.getenv("LOG_PATH", "data/logs/queries.jsonl").replace("./", "")

# 📚 Etiqueta requerida por la Minecraft Wiki (política de MediaWiki).
# Sin un User-Agent identificable te bloquean.
WIKI_USER_AGENT = os.getenv(
    "WIKI_USER_AGENT",
    "RAG-Minecraft/1.0 (contact: argomezflores@gmail.com)",
)
WIKI_API_URL = os.getenv("WIKI_API_URL", "https://minecraft.wiki/api.php")

# --- Parámetros de RAG ---
# 📚 CHUNK_SIZE: caracteres por fragmento. Balance entre "suficiente contexto"
# y "no exceder límite de embeddings". 800 chars ≈ 200 tokens ≈ 1 párrafo largo.
CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "800"))

# 📚 CHUNK_OVERLAP: caracteres compartidos entre chunks vecinos.
# Evita cortar ideas a la mitad. ~20% del chunk_size es un buen default.
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "150"))

# 📚 TOP_K: cuántos chunks recuperar por query. Más = más contexto pero
# más ruido y más tokens al LLM. 5 es el sweet spot para RAG clásico.
TOP_K = int(os.getenv("TOP_K", "5"))

# --- Mejoras de calidad (v3) ---
# 📚 Estas dos técnicas son el estándar de la industria (2022+) para mejorar
# la precisión de un RAG. Ambas son opcionales — se pueden desactivar via env var
# para A/B testear o para reducir latencia.

# 📚 RETRIEVAL_TOP_N: cuántos chunks recuperar del vector store ANTES del re-ranking.
# Casteamos una red más amplia (20) para que el re-ranker tenga candidatos ricos
# de donde elegir el TOP_K final (5). Estándar en la literatura: N ≈ 4-5x K.
RETRIEVAL_TOP_N = int(os.getenv("RETRIEVAL_TOP_N", "20"))

# 📚 QUERY_REWRITE: si es true, Claude Haiku genera 3 variaciones de la query
# antes del retrieval. Da mejor cobertura para preguntas ambiguas o multiidioma.
QUERY_REWRITE = os.getenv("QUERY_REWRITE", "true").lower() == "true"

# 📚 RERANK: si es true, un cross-encoder re-ordena los top-N por relevancia
# fina. Corrige el problema de "chunks superficiales" que dominan el bi-encoder.
RERANK = os.getenv("RERANK", "true").lower() == "true"

# 📚 Modelo de re-ranking (local, gratis, ~90MB). Cross-encoder MS-MARCO es el
# baseline estándar y suficientemente bueno para nuestro caso.
RERANK_MODEL = os.getenv("RERANK_MODEL", "cross-encoder/ms-marco-MiniLM-L-6-v2")

# --- Mejoras de calidad v5 ---
# 📚 TITLE_BOOST: cuánto sumamos al score si el título del artículo aparece
# como substring en la query. Ayuda a que "hopper" siempre traiga "Hopper" arriba.
# Aditivo post-sigmoide del cross-encoder.
TITLE_BOOST = float(os.getenv("TITLE_BOOST", "0.3"))

# 📚 MIN_ACCEPTABLE_SCORE: si el mejor score tras re-rank es menor a esto,
# devolvemos "no encontré info" sin llamar al LLM. Ahorra $$ y da respuesta útil.
MIN_ACCEPTABLE_SCORE = float(os.getenv("MIN_ACCEPTABLE_SCORE", "0.15"))
