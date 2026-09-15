"""
chunker.py — Divide texto largo en fragmentos manejables (chunks).

Concepto RAG: los modelos de embeddings tienen un límite de tokens (~512 típico).
Un PDF de 50 páginas no cabe. Dividimos en chunks de ~800 caracteres con overlap
de 150 caracteres para no perder contexto en los bordes.

¿Por qué implementación propia y no un splitter de librería?
Porque un chunker es literalmente ~30 líneas de código. Escribirlo tú te da
control total sobre cómo se rompen las frases y elimina una dependencia extra.
"""


def split_text(text: str, chunk_size: int = 800, overlap: int = 150) -> list[str]:
    """
    Divide `text` en chunks de máximo `chunk_size` caracteres, con `overlap`
    caracteres compartidos entre chunks vecinos.

    Estrategia: intentamos cortar en un separador "natural" (doble salto de
    línea > salto de línea > punto > espacio) para no partir frases a la mitad.
    """
    if len(text) <= chunk_size:
        return [text.strip()] if text.strip() else []

    # 📚 Prioridad de puntos de corte: del más "limpio" (párrafo) al menos limpio (espacio).
    separators = ["\n\n", "\n", ". ", " "]
    chunks: list[str] = []
    start = 0

    while start < len(text):
        end = start + chunk_size

        if end >= len(text):
            # 📚 Último chunk: agarra lo que quede.
            chunks.append(text[start:].strip())
            break

        # 📚 Buscamos el mejor separador dentro de la ventana [start, end].
        # Empezamos por el más limpio; si no encontramos, bajamos de nivel.
        split_at = -1
        for sep in separators:
            idx = text.rfind(sep, start, end)
            if idx > start:
                split_at = idx + len(sep)
                break

        if split_at == -1:
            # 📚 Ningún separador encontrado — cortamos duro en `end`.
            split_at = end

        chunks.append(text[start:split_at].strip())

        # 📚 El próximo chunk empieza `overlap` caracteres antes del corte,
        # para compartir contexto y no cortar ideas a la mitad.
        start = max(split_at - overlap, start + 1)

    # Filtramos chunks vacíos que puedan colarse.
    return [c for c in chunks if c]
