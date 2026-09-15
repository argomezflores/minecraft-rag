"""
test_rag.py — Prueba end-to-end del pipeline completo (rewrite + retrieve + rerank + LLM).

Uso:
  python scripts/test_rag.py "how to craft a beacon"
  python scripts/test_rag.py --chat "cómo crafteo una tolva"    # format=chat (bot in-game)

Muestra: variaciones generadas, chunks recuperados con scores, respuesta final.
También guarda al log persistente (source="cli") para que aparezca en el benchmark.
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.pipeline import answer_question
from src.query_log import log_query


def main() -> int:
    args = list(sys.argv[1:])
    fmt = "full"
    if "--chat" in args:
        fmt = "chat"
        args.remove("--chat")

    query = " ".join(args) or "¿Cómo se craftea un Beacon?"
    print(f"\n[Q] ({fmt}) {query}\n")

    t0 = time.perf_counter()
    result = answer_question(query, format=fmt)
    latency_ms = int((time.perf_counter() - t0) * 1000)

    if result["rewrites"] and len(result["rewrites"]) > 1:
        print("[QUERY REWRITES]")
        for i, r in enumerate(result["rewrites"], start=1):
            marker = "→" if i == 1 else " "
            print(f"  {marker} [{i}] {r}")
        print()

    print(f"[DEBUG] {result['debug']} · latency={latency_ms}ms\n")

    print(f"[RESPUESTA]\n{result['answer']}\n")

    print("[FUENTES]")
    for i, h in enumerate(result["sources"], start=1):
        print(f"  [{i}] {h.title} ({h.category}) score={h.score}")
        print(f"      {h.url}")

    # 📚 Guardamos en el log persistente igual que la API para que aparezca en el benchmark.
    log_query({
        "source": "cli",
        "question": query,
        "format": fmt,
        "rewrites": result["rewrites"],
        "sources": [
            {"title": h.title, "url": h.url, "category": h.category, "score": h.score}
            for h in result["sources"]
        ],
        "answer": result["answer"],
        "latency_ms": latency_ms,
        "n_candidates": result["debug"].get("candidates_after_dedup", 0),
        "n_final_hits": result["debug"].get("final_hits", 0),
        "rewrites_used": result["debug"].get("rewrites_used", 0),
    })

    return 0


if __name__ == "__main__":
    sys.exit(main())
