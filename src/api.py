"""
api.py — API REST FastAPI que expone el sistema RAG.

Concepto: envolvemos el retriever + generator en endpoints HTTP para que
cualquier cliente (widget web, bot de Minecraft, curl) pueda consumirlos.

Endpoints:
  GET  /health        → verificar que la API está viva
  POST /query         → hacer una pregunta al RAG
  POST /ingest        → re-indexar la wiki (uso administrativo)
"""

import time
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from src.config import TOP_K, BASE_DIR
from src.pipeline import answer_question
from src.ingest import ingest_all
from src.query_log import log_query, read_recent, count_entries


app = FastAPI(
    title="RAG Minecraft Wiki",
    description="Asistente RAG sobre la Minecraft Wiki oficial (items, mobs, mecánicas)",
    version="0.2.0",
)

# 📚 CORS abierto para que widget y bot puedan llamar desde cualquier origen.
# En producción real esto se restringe al dominio del portafolio.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


# --- Modelos de request/response ---

class QueryRequest(BaseModel):
    question: str = Field(..., min_length=3, max_length=500)
    k: int | None = Field(default=None, ge=1, le=20)
    # 📚 "full" = widget web (markdown, citas, hasta 512 tokens).
    # "chat" = bot in-game (texto plano corto, sin citas [N], max 256 tokens).
    format: Literal["full", "chat"] = "full"
    # 📚 v4: identifica el origen de la query para métricas/benchmark.
    # Cada cliente (widget, bot, cli) lo envía. Default "unknown" para retrocompat.
    source: str = Field(default="unknown", max_length=32)


class Source(BaseModel):
    title: str        # 📚 "Diamond Pickaxe"
    url: str          # 📚 https://minecraft.wiki/w/Diamond_Pickaxe
    category: str     # 📚 Items / Mobs / Blocks / ...
    score: float
    excerpt: str


class QueryResponse(BaseModel):
    question: str
    answer: str
    sources: list[Source]
    rewrites: list[str] = []  # 📚 Variaciones que generó el query rewriter (útil para debug/UI)
    debug: dict = {}          # 📚 Latencia y counts internos


# --- Endpoints ---

@app.get("/health")
def health():
    return {"status": "ok", "service": "rag-minecraft"}


@app.post("/query", response_model=QueryResponse)
def query(req: QueryRequest):
    """Ejecuta el pipeline RAG completo: rewrite → retrieve → rerank → generate."""
    t0 = time.perf_counter()
    try:
        # 📚 Toda la lógica vive en src/pipeline.py — este endpoint solo traduce
        # a modelos Pydantic para respuesta HTTP tipada.
        result = answer_question(req.question, k=req.k or TOP_K, format=req.format)

        sources = [
            Source(
                title=h.title,
                url=h.url,
                category=h.category,
                score=h.score,
                excerpt=(h.text[:200] + "...") if len(h.text) > 200 else h.text,
            )
            for h in result["sources"]
        ]

        latency_ms = int((time.perf_counter() - t0) * 1000)

        # 📚 Log persistente para benchmark/observabilidad.
        # Best-effort: si falla no rompe la respuesta.
        log_query({
            "source": req.source,
            "question": req.question,
            "format": req.format,
            "rewrites": result["rewrites"],
            "sources": [
                {"title": s.title, "url": s.url, "category": s.category, "score": s.score}
                for s in sources
            ],
            "answer": result["answer"],
            "latency_ms": latency_ms,
            "n_candidates": result["debug"].get("candidates_after_dedup", 0),
            "n_final_hits": result["debug"].get("final_hits", 0),
            "rewrites_used": result["debug"].get("rewrites_used", 0),
        })

        return QueryResponse(
            question=result["question"],
            answer=result["answer"],
            sources=sources,
            rewrites=result["rewrites"],
            debug={**result["debug"], "latency_ms": latency_ms},
        )
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error interno: {e}")


@app.get("/logs/recent")
def logs_recent(n: int = 20):
    """Últimas N queries logueadas. Útil para debug y dashboards."""
    return {
        "total_logged": count_entries(),
        "returned": n,
        "entries": read_recent(n),
    }


@app.post("/ingest")
def ingest(reset: bool = False):
    """Re-indexa la wiki cacheada. Uso administrativo."""
    try:
        ingest_all(reset=reset)
        return {"status": "ok", "reset": reset}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# --- Servir el widget como archivos estáticos ---
# 📚 Con esto la misma API sirve la demo en http://localhost:8000/widget/
widget_dir = BASE_DIR / "widget"
if widget_dir.exists():
    app.mount("/widget", StaticFiles(directory=str(widget_dir), html=True), name="widget")
