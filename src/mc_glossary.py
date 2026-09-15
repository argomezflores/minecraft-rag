"""
mc_glossary.py — Diccionario manual ES→EN de términos de Minecraft.

Concepto: la Minecraft Wiki está en inglés y los embeddings tienen mejor
matching cuando la query menciona los nombres oficiales. El query rewriter
con Haiku a veces traduce "tolva" a "Hopper" y a veces no — es no determinístico.

Solución: un diccionario MANUAL con los términos más comunes que un jugador
mexicano diría, mapeados a su nombre oficial en la wiki. Se usa como
variación GARANTIZADA en el pipeline (además de las variaciones que da Haiku).

Ventajas vs traducción dinámica con LLM:
- Determinístico (siempre traduce igual)
- Cero costo ($0)
- Cero latencia (<1ms)
- Fácil de extender (agregar una línea)
- Testeable

Convención: entradas en MINÚSCULAS para matching case-insensitive.
El VALOR es el nombre oficial de Minecraft (mayúsculas conservadas).
"""

# 📚 Ordenado por categoría para facilitar mantenimiento.
# Cuando detectes un término faltante mientras juegas, agrégalo aquí.
MC_TERMS_ES_EN: dict[str, str] = {
    # --- Bloques utilitarios ---
    "tolva": "Hopper",
    "yunque": "Anvil",
    "horno": "Furnace",
    "ahumador": "Smoker",
    "alto horno": "Blast Furnace",
    "mesa de crafteo": "Crafting Table",
    "mesa de trabajo": "Crafting Table",
    "mesa de encantamientos": "Enchanting Table",
    "mesa de encantamiento": "Enchanting Table",
    "soporte de pociones": "Brewing Stand",
    "caldero": "Cauldron",
    "faro": "Beacon",
    "conducto": "Conduit",
    "barril": "Barrel",
    "cofre": "Chest",
    "cofre trampa": "Trapped Chest",
    "cofre de ender": "Ender Chest",
    "muela": "Grindstone",
    "telar": "Loom",
    "mesa de cartografía": "Cartography Table",
    "mesa de forja": "Smithing Table",
    "cortador de piedra": "Stonecutter",
    "compostera": "Composter",

    # --- Redstone ---
    "pistón": "Piston",
    "piston": "Piston",
    "pistón pegajoso": "Sticky Piston",
    "dispensador": "Dispenser",
    "expulsor": "Dropper",
    "observador": "Observer",
    "repetidor": "Redstone Repeater",
    "repetidor de redstone": "Redstone Repeater",
    "comparador": "Redstone Comparator",
    "comparador de redstone": "Redstone Comparator",
    "antorcha de redstone": "Redstone Torch",
    "polvo de redstone": "Redstone Dust",
    "placa de presión": "Pressure Plate",
    "palanca": "Lever",
    "botón": "Button",
    "detector de luz diurna": "Daylight Detector",

    # --- Herramientas ---
    "pico": "Pickaxe",
    "pico de diamante": "Diamond Pickaxe",
    "pico de netherita": "Netherite Pickaxe",
    "pico de hierro": "Iron Pickaxe",
    "hacha": "Axe",
    "pala": "Shovel",
    "azada": "Hoe",
    "espada": "Sword",
    "espada de diamante": "Diamond Sword",
    "espada de netherita": "Netherite Sword",
    "arco": "Bow",
    "ballesta": "Crossbow",
    "tridente": "Trident",
    "escudo": "Shield",
    "élytra": "Elytra",
    "elytra": "Elytra",

    # --- Items comunes ---
    "vara": "Stick",
    "palo": "Stick",
    "diamante": "Diamond",
    "lingote de hierro": "Iron Ingot",
    "lingote de oro": "Gold Ingot",
    "lingote de netherita": "Netherite Ingot",
    "netherita": "Netherite",
    "pólvora": "Gunpowder",
    "polvora": "Gunpowder",
    "perla de ender": "Ender Pearl",
    "ojo de ender": "Eye of Ender",
    "tótem de la inmortalidad": "Totem of Undying",
    "totem de la inmortalidad": "Totem of Undying",
    "estrella del nether": "Nether Star",
    "ala de dragón": "Dragon's Breath",

    # --- Pociones / brewing ---
    "poción": "Potion",
    "pocion": "Potion",
    "poción de fuerza": "Potion of Strength",
    "poción de debilidad": "Potion of Weakness",
    "poción de veneno": "Potion of Poison",
    "poción de curación": "Potion of Healing",
    "poción de velocidad": "Potion of Swiftness",
    "poción de salto": "Potion of Leaping",
    "poción de invisibilidad": "Potion of Invisibility",
    "poción de respiración": "Potion of Water Breathing",
    "verruga del nether": "Nether Wart",
    "polvo de blaze": "Blaze Powder",
    "vara de blaze": "Blaze Rod",

    # --- Encantamientos ---
    "fortuna": "Fortune",
    "toque de seda": "Silk Touch",
    "eficiencia": "Efficiency",
    "irrompibilidad": "Unbreaking",
    "reparación": "Mending",
    "reparacion": "Mending",
    "filo": "Sharpness",
    "botín": "Looting",
    "poder": "Power",
    "infinidad": "Infinity",
    "caída de pluma": "Feather Falling",
    "protección": "Protection",

    # --- Mobs ---
    "aldeano": "Villager",
    "aldeanos": "Villager",
    "esqueleto": "Skeleton",
    "creeper": "Creeper",
    "enderman": "Enderman",
    "endermen": "Enderman",
    "dragón del end": "Ender Dragon",
    "wither": "Wither",
    "zombi": "Zombie",
    "zombie": "Zombie",
    "araña": "Spider",
    "hombre cerdo del nether": "Zombified Piglin",
    "piglin": "Piglin",
    "ghast": "Ghast",
    "guardián": "Guardian",

    # --- Portales / dimensiones ---
    "portal del nether": "Nether portal",
    "portal al nether": "Nether portal",
    "portal del end": "End portal",
    "portal al end": "End portal",
    "nether": "Nether",
    "el end": "The End",

    # --- Comida / farming ---
    "trigo": "Wheat",
    "zanahoria": "Carrot",
    "zanahoria dorada": "Golden Carrot",
    "papa": "Potato",
    "manzana": "Apple",
    "manzana dorada": "Golden Apple",
    "pan": "Bread",
    "hueso": "Bone",
    "harina de hueso": "Bone Meal",
}


def _tokenize(text: str) -> list[str]:
    """Convierte texto en tokens minúsculos, preservando espacios para bigramas."""
    import re
    # 📚 Preservamos espacios, quitamos puntuación. Los bigramas los detectamos aparte.
    cleaned = re.sub(r"[^\w\sáéíóúñü]+", " ", text.lower(), flags=re.UNICODE)
    return cleaned.split()


def translate_es_terms(query: str) -> tuple[str, list[str]]:
    """
    Detecta términos en español y devuelve (query_traducida, términos_detectados).

    Estrategia: busca coincidencias (case-insensitive) de las claves del glosario
    dentro de la query. Soporta multi-word terms (ej. "pico de diamante").

    Devuelve:
    - query_traducida: la query original con términos ES reemplazados por su EN.
    - términos_detectados: lista de tuplas (es, en) para mostrar en logs/debug.

    Si no detecta ningún término, devuelve la query original sin cambios.
    """
    import re

    query_lower = query.lower()
    detected: list[str] = []
    translated = query

    # 📚 Ordenamos por longitud descendente para hacer match primero de
    # frases largas ("pico de diamante") antes que cortas ("pico").
    sorted_terms = sorted(MC_TERMS_ES_EN.keys(), key=len, reverse=True)

    for es_term in sorted_terms:
        # 📚 word boundary matching case-insensitive.
        # No usamos \b porque no funciona bien con ñ, tildes. Usamos lookaround manual.
        pattern = re.compile(
            r"(?<![a-záéíóúñü])" + re.escape(es_term) + r"(?![a-záéíóúñü])",
            re.IGNORECASE | re.UNICODE,
        )
        if pattern.search(query_lower):
            en_term = MC_TERMS_ES_EN[es_term]
            # 📚 Reemplazamos en la query original (no en el _lower) para preservar mayúsculas.
            translated = pattern.sub(en_term, translated)
            detected.append(f"{es_term} → {en_term}")

    return translated, detected


def has_es_terms(query: str) -> bool:
    """True si la query contiene al menos 1 término del glosario ES."""
    _, detected = translate_es_terms(query)
    return len(detected) > 0
