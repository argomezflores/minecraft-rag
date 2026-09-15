"""
query_log.py — Logger persistente de queries al RAG (JSONL append-only).

Concepto: cada request a /query genera una entrada estructurada guardada en
data/logs/queries.jsonl. Esto nos da un dataset REAL (no fabricado) para:
- Debug: ver qué preguntas fallan
- Benchmark: correr comparativas entre versiones (v2 → v3 → v4)
- Portafolio: métricas objetivas de mejora ("hit rate subió de 40% a 85%")

Por qué JSONL y no una base de datos:
- Portable (un archivo de texto)
- Versionable en git si quieres (compresión buena, diffs legibles)
- Exportable a pandas/CSV con 1 línea (pd.read_json(path, lines=True))
- Sin infra extra (SQLite, Postgres) — solo archivo local
- Append-only: nunca modificas líneas viejas → integridad

Diseño:
- Función `log_query(entry: dict)` — best-effort, si falla NO rompe la respuesta al user.
- `read_recent(n)` — utilidad para el endpoint /logs/recent y debug.
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.config import LOG_PATH


def _now_iso() -> str:
    """Timestamp ISO 8601 en UTC (ej. 2026-08-25T21:30:00Z)."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def log_query(entry: dict[str, Any]) -> None:
    """
    Guarda una entrada de query en el JSONL.

    - Añade automáticamente `ts` (timestamp) si no viene.
    - Escribe en modo append (nunca sobreescribe).
    - Best-effort: si falla el disco, imprime a stderr pero NO lanza excepción.
      (No queremos que un disco lleno rompa el /query endpoint.)
    """
    entry.setdefault("ts", _now_iso())
    try:
        # 📚 Aseguramos que la carpeta exista (idempotente).
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with LOG_PATH.open("a", encoding="utf-8") as f:
            # 📚 ensure_ascii=False conserva acentos y ñ; separators evita espacios.
            f.write(json.dumps(entry, ensure_ascii=False, separators=(",", ":")) + "\n")
    except Exception as e:
        # 📚 Best-effort: reportar al stderr pero seguir sirviendo la request.
        print(f"[query_log] WARN: no pude escribir el log: {e}", file=sys.stderr)


def read_recent(n: int = 20) -> list[dict]:
    """Lee las últimas N entradas del log. Útil para debug y endpoint /logs/recent."""
    if not LOG_PATH.exists():
        return []
    try:
        with LOG_PATH.open("r", encoding="utf-8") as f:
            # 📚 Leemos todas las líneas y cortamos las últimas N.
            # Para archivos gigantes (>100MB) sería mejor tail invertido,
            # pero para nuestro caso (miles de queries) esto es perfecto.
            lines = f.readlines()[-n:]
        return [json.loads(ln) for ln in lines if ln.strip()]
    except Exception as e:
        print(f"[query_log] WARN: no pude leer el log: {e}", file=sys.stderr)
        return []


def count_entries() -> int:
    """Cuenta rápida de queries logueadas (para métricas / dashboards)."""
    if not LOG_PATH.exists():
        return 0
    try:
        with LOG_PATH.open("r", encoding="utf-8") as f:
            return sum(1 for ln in f if ln.strip())
    except Exception:
        return 0
