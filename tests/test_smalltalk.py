from src.smalltalk import smalltalk_reply


def test_greetings_get_usage_help():
    for msg in ["hola?", "¡Hola!", "Buenas tardes", "hey minerag", "ayuda", "¿Qué puedes hacer?"]:
        reply = smalltalk_reply(msg)
        assert reply and "Pregúntame" in reply, msg


def test_chat_format_mentions_bot_prefix():
    assert "!rag" in smalltalk_reply("hola", format="chat")


def test_thanks():
    assert smalltalk_reply("¡Muchas gracias!").startswith("¡De nada!")


def test_real_questions_go_to_rag():
    for msg in [
        "hola, ¿cómo hago una antorcha?",
        "¿Qué hace un repeater?",
        "Porque mis aldeanos no se reproducen en mi granja de aldeanos??",
        "como encuentro una oveja rosa?",
    ]:
        assert smalltalk_reply(msg) is None, msg
