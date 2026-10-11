from src.chunker import split_text


def _list_like_text() -> str:
    # 📚 Reproduce el caso de "Death messages": un párrafo corto seguido de
    # un bloque largo de líneas simples sin línea en blanco.
    lines = [f"death.attack.entry{i}\nAppears when the player is hurt by mob {i}." for i in range(200)]
    return "Intro paragraph.\n\n" + "\n".join(lines)


def test_chunk_count_is_proportional_to_text_length():
    text = _list_like_text()
    chunks = split_text(text, chunk_size=800, overlap=150)
    # Avance mínimo por chunk = chunk_size // 2 - overlap = 250 caracteres.
    assert len(chunks) <= len(text) // 250 + 1


def test_chunks_respect_min_and_max_size():
    chunks = split_text(_list_like_text(), chunk_size=800, overlap=150)
    for c in chunks[:-1]:
        assert 400 - 1 <= len(c) <= 800


def test_no_near_duplicate_chunks():
    chunks = split_text(_list_like_text(), chunk_size=800, overlap=150)
    prefixes = [c[:60] for c in chunks]
    assert len(set(prefixes)) == len(prefixes)


def test_short_text_is_single_chunk():
    assert split_text("Hopper.", chunk_size=800, overlap=150) == ["Hopper."]
