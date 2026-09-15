"""
benchmark.py — Corre un conjunto de queries reales contra el pipeline actual
y guarda métricas objetivas para comparar entre versiones del sistema.

Uso:
  python scripts/benchmark.py                    # backfill + queries logueadas
  python scripts/benchmark.py --backfill-only    # solo las hardcodeadas del historial
  python scripts/benchmark.py --version v4       # etiqueta la corrida (default: auto)

Salida:
  data/benchmarks/results_<version>_<timestamp>.json  — resultados crudos
  stdout: resumen con hit rate, latencia mediana, respuestas destacadas

Concepto: no fabricamos un "golden set" — usamos queries REALES que hemos hecho
(backfill de screenshots del historial + logs acumulados durante uso normal).
Esto da datos honestos: qué mejoró, qué empeoró, qué sigue roto.
"""

import argparse
import json
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.pipeline import answer_question
from src.query_log import read_recent, count_entries
from src.config import BASE_DIR


# 📚 Backfill: queries reales del historial de esta sesión con Rogelio.
# Cada una viene de un screenshot o test explícito. `expected_source_contains`
# es el título del artículo (o substring) que DEBERÍA ser el top-1 del retrieval.
# Si `expected_answer_contains` está presente, verificamos que la respuesta lo mencione.
BACKFILL_QUERIES: list[dict] = [
    # v1 (baseline) — con el corpus original
    {
        "question": "¿Cómo puedo craftear una mesa de crafteo?",
        "expected_source_contains": "Crafting Table",
        "expected_answer_contains": ["Planks", "4"],
        "tags": ["crafting", "recipe", "spanish"],
    },
    {
        "question": "Como crafteo un pico de diamante?",
        "expected_source_contains": "Diamond Pickaxe",
        "expected_answer_contains": ["Diamond", "Stick"],
        "tags": ["crafting", "recipe", "spanish", "tools"],
    },
    {
        "question": "Cómo crafteo una tolva?",
        "expected_source_contains": "Hopper",
        "expected_answer_contains": ["Iron", "Chest"],
        "tags": ["crafting", "recipe", "spanish", "translation"],
    },
    # v1 — queries en formato chat que fallaron
    {
        "question": "para qué sirve el beacon",
        "expected_source_contains": "Beacon",
        "expected_answer_contains": ["pyramid", "efecto", "block"],
        "tags": ["usage", "spanish"],
    },
    {
        "question": "que hace el repeater en redstone",
        "expected_source_contains": "Repeater",
        "expected_answer_contains": ["signal", "delay", "redstone"],
        "tags": ["redstone", "spanish", "translation"],
    },
    # v2/v3 — nuevos casos post-rewriter/reranker
    {
        "question": "como funciona un hopper para transportar items",
        "expected_source_contains": "Hopper",
        "expected_answer_contains": ["item", "container"],
        "tags": ["usage", "spanish"],
    },
    {
        "question": "para que sirve el smoker y en que se diferencia del furnace",
        "expected_source_contains": "Smoker",
        "expected_answer_contains": ["food", "faster"],
        "tags": ["usage", "spanish", "comparison"],
    },
    # v4 — casos que aún fallaban en pruebas in-game
    {
        "question": "como hago una poción de debilidad",
        "expected_source_contains": "Potion of Weakness",
        "expected_answer_contains": ["fermented", "spider"],
        "tags": ["brewing", "spanish", "translation"],
    },
    # Casos English para comparar
    {
        "question": "how to craft a diamond pickaxe",
        "expected_source_contains": "Diamond Pickaxe",
        "expected_answer_contains": ["Diamond", "Stick"],
        "tags": ["crafting", "recipe", "english"],
    },
    {
        "question": "what does the fortune enchantment do",
        "expected_source_contains": "Fortune",
        "expected_answer_contains": ["drops", "chance"],
        "tags": ["enchantment", "english"],
    },
]


def _check_source_hit(top_source: str, expected: str) -> bool:
    """True si el título del top-1 contiene la substring esperada (case-insensitive)."""
    return expected.lower() in (top_source or "").lower()


def _check_answer_hits(answer: str, expected_terms: list[str]) -> int:
    """Cuenta cuántos términos esperados aparecen en la respuesta."""
    answer_lower = (answer or "").lower()
    return sum(1 for t in expected_terms if t.lower() in answer_lower)


def _run_query(entry: dict, format: str = "full") -> dict:
    """Ejecuta 1 query y devuelve el resultado con métricas."""
    question = entry["question"]
    t0 = time.perf_counter()
    try:
        result = answer_question(question, format=format)
        latency_ms = int((time.perf_counter() - t0) * 1000)

        top_source = result["sources"][0].title if result["sources"] else "(none)"
        source_hit = _check_source_hit(top_source, entry.get("expected_source_contains", ""))

        expected_terms = entry.get("expected_answer_contains", [])
        answer_hits = _check_answer_hits(result["answer"], expected_terms)
        answer_hit_ratio = answer_hits / len(expected_terms) if expected_terms else None

        return {
            "question": question,
            "format": format,
            "tags": entry.get("tags", []),
            "expected_source": entry.get("expected_source_contains", ""),
            "top_source": top_source,
            "top_score": result["sources"][0].score if result["sources"] else 0,
            "source_hit": source_hit,
            "expected_answer_contains": expected_terms,
            "answer_hits": answer_hits,
            "answer_hit_ratio": answer_hit_ratio,
            "answer": result["answer"],
            "rewrites": result["rewrites"],
            "latency_ms": latency_ms,
            "n_candidates": result["debug"].get("candidates_after_dedup", 0),
            "sources_titles": [s.title for s in result["sources"]],
            "error": None,
        }
    except Exception as e:
        return {
            "question": question,
            "format": format,
            "error": str(e),
            "latency_ms": int((time.perf_counter() - t0) * 1000),
            "source_hit": False,
            "answer_hit_ratio": 0,
        }


def _summary(results: list[dict]) -> dict:
    """Resumen agregado del benchmark."""
    total = len(results)
    if total == 0:
        return {"total": 0}

    source_hits = sum(1 for r in results if r.get("source_hit"))
    answer_ratios = [r.get("answer_hit_ratio") for r in results if r.get("answer_hit_ratio") is not None]
    latencies = [r.get("latency_ms", 0) for r in results if not r.get("error")]
    errors = sum(1 for r in results if r.get("error"))

    return {
        "total_queries": total,
        "source_hit_rate": round(source_hits / total, 3),
        "source_hits": source_hits,
        "answer_hit_avg": round(statistics.mean(answer_ratios), 3) if answer_ratios else None,
        "latency_p50_ms": round(statistics.median(latencies)) if latencies else None,
        "latency_p95_ms": round(sorted(latencies)[int(len(latencies) * 0.95) - 1]) if len(latencies) > 1 else None,
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backfill-only", action="store_true", help="Solo backfill, ignorar log")
    parser.add_argument("--from-log", action="store_true",
                        help="Correr TODAS las queries del logger persistente (data/logs/queries.jsonl)")
    parser.add_argument("--version", default=None, help="Etiqueta de versión (default: v5)")
    parser.add_argument("--format", default="full", choices=["full", "chat"])
    args = parser.parse_args()

    version = args.version or "v5"
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_dir = BASE_DIR / "data" / "benchmarks"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"results_{version}_{ts}.json"

    results = []

    # 📚 Modo --from-log: corre TODAS las queries del logger persistente.
    # Útil para re-evaluar el corpus con las queries reales que hiciste.
    if args.from_log:
        logged = read_recent(n=1000)
        print(f"[bench] Corriendo benchmark v={version} format={args.format}")
        print(f"[bench] From-log: {len(logged)} queries del logger persistente\n")

        seen: set[str] = set()
        for i, entry in enumerate(logged, start=1):
            q = entry.get("question", "").strip()
            if not q or q.lower() in seen:
                continue
            seen.add(q.lower())
            print(f"  [{i}/{len(logged)}] {q[:60]}...", end=" ")
            r = _run_query(
                {"question": q, "expected_source_contains": "", "expected_answer_contains": []},
                format=args.format,
            )
            print(f"top={r.get('top_source', 'N/A')[:30]} lat={r.get('latency_ms', 0)}ms")
            r["from_log"] = True
            results.append(r)

    else:
        print(f"[bench] Corriendo benchmark v={version} format={args.format}")
        print(f"[bench] Backfill: {len(BACKFILL_QUERIES)} queries del historial\n")

        for i, entry in enumerate(BACKFILL_QUERIES, start=1):
            print(f"  [{i}/{len(BACKFILL_QUERIES)}] {entry['question'][:60]}...", end=" ")
            r = _run_query(entry, format=args.format)
            status = "✓" if r.get("source_hit") else "✗"
            print(f"{status} top={r.get('top_source', 'N/A')[:30]} lat={r.get('latency_ms', 0)}ms")
            results.append(r)

    # Optional: correr también las queries del log persistente (menos backfill).
    logged_count = 0
    if not args.backfill_only and not args.from_log:
        logged = read_recent(n=50)
        # Filtramos duplicados con backfill.
        backfill_qs = {q["question"].lower().strip() for q in BACKFILL_QUERIES}
        for entry in logged:
            q = entry.get("question", "").strip()
            if not q or q.lower() in backfill_qs:
                continue
            print(f"  [log] {q[:60]}...", end=" ")
            r = _run_query(
                {"question": q, "expected_source_contains": "", "expected_answer_contains": []},
                format=args.format,
            )
            print(f"top={r.get('top_source', 'N/A')[:30]} lat={r.get('latency_ms', 0)}ms")
            r["from_log"] = True
            results.append(r)
            logged_count += 1

    summary = _summary(results)
    total_logged = count_entries()

    output = {
        "version": version,
        "timestamp": ts,
        "format": args.format,
        "summary": summary,
        "total_queries_in_log": total_logged,
        "backfill_count": len(BACKFILL_QUERIES),
        "log_added_count": logged_count,
        "results": results,
    }

    out_path.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"\n{'=' * 60}")
    print(f"RESUMEN v={version}")
    print(f"{'=' * 60}")
    print(f"Total queries:       {summary['total_queries']}")
    print(f"Source hit rate:     {summary['source_hit_rate']} ({summary['source_hits']}/{summary['total_queries']})")
    if summary.get("answer_hit_avg") is not None:
        print(f"Answer hit avg:      {summary['answer_hit_avg']}")
    print(f"Latencia p50:        {summary['latency_p50_ms']}ms")
    print(f"Latencia p95:        {summary['latency_p95_ms']}ms")
    print(f"Errores:             {summary['errors']}")
    print(f"\n✅ Guardado: {out_path.relative_to(BASE_DIR)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
