"""
smalltalk.py — Respuestas directas para saludos, "ayuda" y "gracias".

📚 Jugadores reales le escribieron "hola?" al bot y recibieron "No encontré
información..." (docs/eval-log.md #018). Si el mensaje COMPLETO es small talk,
respondemos cómo usar el asistente, sin retrieval ni LLM (costo $0). Un mensaje
como "hola, ¿cómo hago una antorcha?" sí pasa al RAG.
"""

import re
import unicodedata
from typing import Literal

_GREETINGS = {
    "hola", "holi", "hey", "buenas", "buenos dias", "buenas tardes", "buenas noches",
    "que tal", "saludos", "hi", "hello", "hola minerag", "hey minerag",
}
_HELP = {
    "ayuda", "help", "que puedes hacer", "que haces", "como funcionas", "quien eres",
    "como te uso", "instrucciones",
}
_THANKS = {"gracias", "muchas gracias", "grax", "thanks", "thank you", "ty"}

_EXAMPLES = "¿cómo hago una poción de velocidad?, ¿cómo invoco al Wither? o ¿qué hace un observer?"


def _normalize(text: str) -> str:
    """Minúsculas, sin acentos ni puntuación: "¡Hola!" y "hola?" → "hola"."""
    text = unicodedata.normalize("NFKD", text.lower())
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r"[^a-z0-9 ]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def smalltalk_reply(question: str, format: Literal["full", "chat"] = "full") -> str | None:
    """Respuesta fija si el mensaje es solo un saludo, ayuda o gracias; si no, None."""
    q = _normalize(question)
    if q in _THANKS:
        return "¡De nada! Si surge otra duda, aquí estoy."
    if q in _GREETINGS or q in _HELP:
        # 📚 En el juego la pregunta va con el prefijo del bot; en la web no.
        usage = "Escribe !rag y tu pregunta, por ejemplo:" if format == "chat" else "Pregúntame, por ejemplo:"
        return (
            "¡Hola! Soy MineRag: respondo dudas de Minecraft con la wiki oficial "
            f"y te digo de dónde saqué cada dato. {usage} {_EXAMPLES}"
        )
    return None
