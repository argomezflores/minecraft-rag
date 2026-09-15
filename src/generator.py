"""
generator.py — Genera la respuesta final llamando a Claude con los chunks recuperados.

Concepto RAG: la G (Generation) del acrónimo. Tomamos los K chunks del
retriever, los formateamos como contexto en el prompt del LLM, y pedimos
una respuesta que se base ÚNICAMENTE en ese contexto (para evitar
alucinaciones).

Dos modos según cliente:
- format="full"  → widget web, respuesta con markdown y citas, hasta 512 tokens.
- format="chat"  → bot in-game, texto plano, 3-4 líneas cortas, sin citas [N].
"""

from typing import Literal
from anthropic import Anthropic

from src.config import ANTHROPIC_API_KEY, CLAUDE_MODEL
from src.retriever import Hit


# 📚 Prompt "full": para el widget web. Permite markdown, citas [N], respuestas
# de longitud media. Anti-alucinación FUERTE — este fue el bug del v3 (LLM
# contradicía "no tengo info" y luego daba la respuesta desde training).
SYSTEM_PROMPT_FULL = """Eres un experto en Minecraft (Java Edition, versiones modernas 1.20+).
Respondes preguntas de jugadores usando ÚNICAMENTE el contexto oficial de la Minecraft Wiki que se te da.

Reglas ESTRICTAS (obligatorias):
1. Responde en ESPAÑOL, aunque el contexto esté en inglés (tradúcelo tú al responder).
2. NO uses tu conocimiento pre-entrenado sobre Minecraft. SOLO lo que está en el contexto.
3. Si dices "no tengo esa información en la wiki" o similar, PARA AHÍ. NO añadas "sin embargo, sé que...", "necesitas X y Y", ni ninguna información desde tu memoria.
4. La HONESTIDAD > la utilidad. Es peor dar info correcta por casualidad que admitir que no está en el contexto.
5. Si falta una receta específica en el contexto, di: "La wiki no tiene esa receta indexada. Revisa el link de la fuente."
6. Sé conciso: máximo 4-5 líneas por respuesta.
7. Menciona items/mobs por su nombre en inglés (ej. "Diamond Pickaxe", "Enderman").
8. Cita fuentes al final con [1], [2], etc., correspondientes al número del fragmento.
9. Números y stats siempre precisos, y SOLO si están en el contexto."""


# 📚 Prompt "chat": para el bot in-game. Sin markdown, sin citas, ultra-corto.
# Los códigos MC de color/estilo los aplica el bot en JavaScript, no aquí.
#
# 🆕 v4 rebalanceado: la versión anterior era demasiado defensiva (reglas
# "PARA AHÍ", "honestidad > utilidad") y hacía que el modelo se autocensurara
# aunque tuviera contexto válido. Ejemplo del bug: pico de diamante → "no tengo info"
# cuando el chunk con la receta SÍ estaba presente. Este balance es mejor:
# responde cuando hay info, admite honestamente cuando no.
SYSTEM_PROMPT_CHAT = """Eres un experto en Minecraft. Respondes preguntas rápidas de un jugador que está EN EL JUEGO.

Reglas:
1. Si el contexto TIENE la respuesta, RESPÓNDELA completa (aunque sea corta y directa). No la escondas.
2. NO uses tu conocimiento pre-entrenado — SOLO el contexto que se te da.
3. Si el contexto NO tiene la respuesta, di UNA frase clara: "No lo encontré en la wiki." Sin añadir "sin embargo".
4. Responde en ESPAÑOL, en TEXTO PLANO (nada de **negrita** ni *cursiva*).
5. MÁXIMO 3 líneas cortas. Sin citas [1] [2].
6. Menciona items por su nombre en inglés (Diamond Pickaxe, Redstone Repeater, Hopper, etc.).
7. Para crafting, di los materiales exactos y cantidad (ej: "3 Diamonds + 2 Sticks en la crafting grid").
8. Números y stats precisos, siempre que estén en el contexto."""


def _format_context(hits: list[Hit]) -> str:
    """Convierte los chunks recuperados en un bloque de contexto numerado."""
    lines = []
    for i, h in enumerate(hits, start=1):
        # 📚 Numeramos cada fragmento para que Claude pueda citarlos con [N]
        # en modo full. En modo chat, la numeración sigue ayudando a que el
        # LLM organice el contexto, aunque no la cite.
        lines.append(f"[{i}] (Wiki: {h.title})\n{h.text}")
    return "\n\n---\n\n".join(lines)


def generate_answer(
    question: str,
    hits: list[Hit],
    format: Literal["full", "chat"] = "full",
) -> str:
    """
    Llama a Claude con contexto + pregunta, devuelve la respuesta en texto.

    format="full" → para widget web (default, retro-compatible).
    format="chat" → para bot in-game (más corto, texto plano).
    """
    if not ANTHROPIC_API_KEY:
        raise RuntimeError(
            "ANTHROPIC_API_KEY no configurada. Copia .env.example a .env y ponla."
        )

    if not hits:
        return "No tengo información sobre eso en la wiki."

    # 📚 Selección de prompt y presupuesto de tokens según el cliente.
    if format == "chat":
        system_prompt = SYSTEM_PROMPT_CHAT
        max_tokens = 256  # 📚 Chat MC: mitad que full → generation ~1.5s vs ~2.5s
    else:
        system_prompt = SYSTEM_PROMPT_FULL
        max_tokens = 512

    context = _format_context(hits)
    user_message = f"""Contexto (de la Minecraft Wiki oficial):
{context}

---

Pregunta del jugador: {question}

Responde en español, basándote SOLO en el contexto proporcionado arriba."""

    client = Anthropic(api_key=ANTHROPIC_API_KEY)
    response = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=max_tokens,
        system=system_prompt,
        messages=[{"role": "user", "content": user_message}],
    )
    # 📚 La respuesta viene como lista de bloques; para texto simple es 1 bloque.
    return response.content[0].text
