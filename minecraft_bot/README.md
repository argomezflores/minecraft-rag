# MineRag — Bot Mineflayer para el RAG de Minecraft

Bot en Node.js que se conecta a tu mundo de Minecraft y responde preguntas usando el RAG que corre en local.

## Requisitos

- **Node.js 18+** — verifica con `node --version`
- **Minecraft Java Edition** (cualquier versión moderna)
- **API RAG corriendo** en `localhost:8000` (ver el README raíz)

## Instalación

```bash
cd minecraft_bot
npm install
```

## Flujo completo (paso a paso)

### 1. Arranca la API RAG (en otra terminal, desde la raíz del proyecto)

```powershell
cd <ruta-del-repo>   # raíz del proyecto
.\.venv\Scripts\Activate.ps1
uvicorn src.api:app --reload
```

Debería mostrar `Uvicorn running on http://127.0.0.1:8000`.

### 2. Abre Minecraft y prepara tu mundo

1. Entra a un mundo singleplayer (o crea uno nuevo — te recomiendo Creativo para explorar sin riesgo mientras pruebas).
2. Presiona **ESC** → **"Open to LAN"**.
3. Configura:
   - Game Mode: el que quieras
   - Cheats: puede ser off
   - **Presiona "Start LAN World"**
4. Verás un mensaje en el chat como:
   > `Local game hosted on port 51234`
5. **Copia ese puerto.** Es distinto cada vez que abres a LAN.

### 3. Configura el bot con el puerto

Opción A — variable de entorno:

```powershell
$env:MC_PORT = "51234"  # ← reemplaza con tu puerto
node bot.js
```

Opción B — edita `bot.js` línea 27:

```javascript
port: parseInt(process.env.MC_PORT || "51234", 10),  // ← ajusta acá
```

### 4. Arranca el bot

```bash
node bot.js
```

Deberías ver:

```
[bot] Iniciando MineRag...
[bot] Conectando a localhost:51234
[bot] API RAG: http://localhost:8000
[bot] ✅ Conectado como MineRag
```

Y en Minecraft aparecerá `MineRag joined the game` + un mensaje de bienvenida en el chat.

### 5. Haz preguntas en el chat

Abre el chat en Minecraft (tecla **T** o **/**) y escribe:

```
!rag how do I make a beacon?
```

MineRag responderá en el chat:

```
<MineRag> ⛏️ Minando la respuesta para @Rogelio...
<MineRag> [@Rogelio] Para craftear un Beacon necesitas: 3 Obsidian abajo,
<MineRag> 5 Glass en el medio, y 1 Nether Star arriba, formando patrón...
<MineRag> 📚 Fuente: Beacon (score 0.891)
```

## Configuración por variables de entorno

```powershell
$env:MC_HOST = "localhost"          # host del server MC
$env:MC_PORT = "51234"              # puerto (ver mensaje de "Open to LAN")
$env:BOT_USERNAME = "MineRag"        # nombre del bot en el juego
$env:COMMAND_PREFIX = "!rag "        # prefijo del comando (default "!rag ")
$env:RAG_API_URL = "http://localhost:8000"  # URL del FastAPI RAG
$env:MC_VERSION = "1.20.4"          # version MC (o vacío para autodetectar)
$env:MC_AUTH = "offline"            # "offline" para LAN, "microsoft" para servidores premium
```

## Troubleshooting

**"ECONNREFUSED" al conectar a MC**
- El puerto está mal. Vuelve a abrir a LAN, verifica el puerto en el chat, actualízalo.

**"Client is not authenticated"**
- Para LAN singleplayer usa `MC_AUTH=offline`. Para servidores premium multiplayer, `microsoft`.

**El bot no responde**
- Verifica que la API RAG esté corriendo: `curl http://localhost:8000/health` debe devolver `{"status":"ok"}`.
- Ve los logs del bot en la terminal — te dirá el error exacto.

**El chat se corta o el bot es kickeado por spam**
- Ya está mitigado con `MIN_TIME_BETWEEN_QUERIES_MS` y delay entre chunks. Si aún pasa, aumenta esos valores en `bot.js`.

**Respuestas muy largas**
- El chat de MC limita ~256 chars por línea. Respuestas largas se dividen en múltiples mensajes. Ajusta `max_tokens` en `src/generator.py` si quieres respuestas aún más cortas.

## Servidores multiplayer (bonus)

El bot funciona igual en:
- **Servidores locales de Paper/Spigot** — solo cambia `MC_HOST` y `MC_PORT`.
- **Servidores gratuitos como Aternos** — pon `MC_HOST=tuservidor.aternos.me`.
- **Realms** — no funciona (Realms no acepta clientes custom).

Para servers premium: `MC_AUTH=microsoft` y sigue el flujo interactivo de login que te aparece en la terminal.
