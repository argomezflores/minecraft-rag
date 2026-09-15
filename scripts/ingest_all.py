"""
ingest_all.py — CLI para correr la ingesta completa desde terminal.

Uso:
  python scripts/ingest_all.py           # ingesta incremental (upsert)
  python scripts/ingest_all.py --reset   # borra la colección y re-indexa todo
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.ingest import ingest_all


def main() -> int:
    reset = "--reset" in sys.argv
    ingest_all(reset=reset)
    return 0


if __name__ == "__main__":
    sys.exit(main())
