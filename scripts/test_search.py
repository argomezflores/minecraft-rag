"""
test_search.py — Prueba rápida del retriever (sin llamar al LLM).

Uso: python scripts/test_search.py "how do I make a beacon"
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.retriever import search


def main() -> int:
    query = " ".join(sys.argv[1:]) or "how do I make a diamond pickaxe?"
    print(f"\n[Q] {query}\n")
    hits = search(query, k=3)
    for i, h in enumerate(hits, start=1):
        preview = h.text[:250].replace("\n", " ")
        print(f"[{i}] {h.title} · {h.category} · score={h.score}")
        print(f"    URL: {h.url}")
        print(f"    {preview}...\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
