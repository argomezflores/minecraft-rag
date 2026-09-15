/**
 * bot.js — MineRag: bot Mineflayer que consulta al RAG y responde en el chat.
 *
 * Flujo:
 *   1. Se conecta a un mundo abierto a LAN (o servidor multiplayer).
 *   2. Escucha mensajes en el chat.
 *   3. Cuando alguien escribe "!rag <pregunta>", llama al FastAPI local
 *      con format="chat" (respuesta corta, sin markdown).
 *   4. Post-procesa el texto (quita [N], **bold**, emojis), aplica códigos
 *      MC §-color y publica en el chat en chunks respetando el límite.
 *
 * Uso:
 *   1. En Minecraft: abre un mundo, ESC → "Open to LAN" → toma nota del puerto.
 *   2. set MC_PORT=<tu_puerto>  (Windows CMD)   |   $env:MC_PORT="<puerto>"  (PowerShell)
 *   3. Asegúrate de que la API RAG esté corriendo (localhost:8000).
 *   4. Ejecuta: node bot.js
 *   5. En el chat de Minecraft: !rag how do I make a beacon?
 */

const mineflayer = require("mineflayer");
const axios = require("axios");

// --- Configuración ---
const config = {
  host: process.env.MC_HOST || "localhost",
  port: parseInt(process.env.MC_PORT || "25565", 10),
  username: process.env.BOT_USERNAME || "MineRag",
  version: process.env.MC_VERSION || false,
  auth: process.env.MC_AUTH || "offline",
  ragApiUrl: process.env.RAG_API_URL || "http://localhost:8000",
  commandPrefix: process.env.COMMAND_PREFIX || "!rag ",
  maxChatChunk: 240,
};

// 📚 Nota sobre colores: Minecraft NO permite que un cliente envíe códigos
// de color (§) en el chat — solo el servidor puede. Un cliente que envía §
// es kickeado con "multiplayer.disconnect.illegal_characters".
// Por eso trabajamos con texto plano. Si quieres colores, se puede migrar
// a /tellraw @a JSON (requiere mundo con cheats ON + bot con OP).

const IGNORE_OWN_MESSAGES = true;
const MIN_TIME_BETWEEN_QUERIES_MS = 2000;
let lastQueryAt = 0;

console.log("[bot] Iniciando MineRag...");
console.log(`[bot] Conectando a ${config.host}:${config.port}`);
console.log(`[bot] API RAG: ${config.ragApiUrl}`);

const bot = mineflayer.createBot({
  host: config.host,
  port: config.port,
  username: config.username,
  version: config.version,
  auth: config.auth,
});

bot.on("login", () => {
  console.log(`[bot] ✅ Conectado como ${bot.username}`);
});

bot.on("spawn", () => {
  bot.chat("MineRag aqui. Usa: !rag <tu pregunta>");
});

bot.on("kicked", (reason) => {
  console.error("[bot] Kicked:", reason);
});

bot.on("error", (err) => {
  console.error("[bot] Error:", err.message);
});

bot.on("end", (reason) => {
  console.log("[bot] Desconectado:", reason);
});

// 📚 Limpia el texto que viene del LLM para que se vea bien en el chat MC.
// - Quita markdown **bold** y *italic* → solo texto (MC no renderiza markdown).
// - Quita citas [1], [2], [3] que el LLM a veces mete.
// - Quita emojis que no renderizan bien en el chat vanilla.
// - Quita § para evitar el kick por "illegal_characters".
function cleanMarkdown(text) {
  return text
    // **bold** → quitar asteriscos
    .replace(/\*\*([^*]+)\*\*/g, "$1")
    // *italic* → quitar asteriscos
    .replace(/(?<!\*)\*(?!\*)([^*]+)\*(?!\*)/g, "$1")
    // Citas tipo [1], [23] al final o intercaladas
    .replace(/\s*\[\d+\](?:\s*\[\d+\])*\s*/g, " ")
    // Emojis comunes del bot original (variant selectors incluidos)
    .replace(/[⛏️🤖📚❌✅⚠️🎮📌✨🔍💬]/g, "")
    // 📚 Elimina cualquier § por si el LLM lo colada (evita illegal_characters kick).
    .replace(/§/g, "")
    // Espacios múltiples
    .replace(/[ \t]{2,}/g, " ")
    .trim();
}

// 📚 Divide texto largo en trozos <240 chars respetando espacios naturales.
// Los códigos §X ocupan 2 chars visibles pero no cuentan en el ancho del chat.
function splitForChat(text, maxLen) {
  const result = [];
  let remaining = text.trim();
  while (remaining.length > maxLen) {
    let cutAt = remaining.lastIndexOf(" ", maxLen);
    if (cutAt < maxLen / 2) cutAt = maxLen;
    result.push(remaining.slice(0, cutAt).trim());
    remaining = remaining.slice(cutAt).trim();
  }
  if (remaining) result.push(remaining);
  return result;
}

// 📚 Envía respuesta en piezas, con pausa entre mensajes para no ser rate-limited.
async function sendChunkedReply(pieces) {
  for (const piece of pieces) {
    bot.chat(piece);
    await new Promise((r) => setTimeout(r, 700));
  }
}

// 📚 Handler principal: escucha chat, filtra por prefijo, llama al RAG.
bot.on("chat", async (username, message) => {
  if (IGNORE_OWN_MESSAGES && username === bot.username) return;
  if (!message.startsWith(config.commandPrefix)) return;

  const now = Date.now();
  if (now - lastQueryAt < MIN_TIME_BETWEEN_QUERIES_MS) {
    bot.chat("Esperame un momento entre preguntas...");
    return;
  }
  lastQueryAt = now;

  const question = message.slice(config.commandPrefix.length).trim();
  if (!question) {
    bot.chat("Uso: !rag <tu pregunta>");
    return;
  }

  console.log(`[bot] ${username} preguntó: "${question}"`);
  // 📚 "Minando la respuesta" — se mantiene el mensaje. Sin § para evitar kick.
  bot.chat(`> Minando la respuesta para ${username}...`);

  try {
    const res = await axios.post(
      `${config.ragApiUrl}/query`,
      { question, format: "chat", source: "bot" },  // 📚 format:"chat" + source:"bot" para logs
      { timeout: 30000 }
    );

    const { answer, sources } = res.data;
    const cleaned = cleanMarkdown(answer);

    // 📚 Prefijo simple "→" antes del texto. Sin colores por limitación del chat MC.
    const prefixed = `> ${cleaned}`;
    const pieces = splitForChat(prefixed, config.maxChatChunk);
    await sendChunkedReply(pieces);

    // 📚 Fuente al final, prefijo con "-" para que se vea como separador.
    if (sources && sources.length) {
      bot.chat(`- Fuente: ${sources[0].title}`);
    }
  } catch (err) {
    const msg = err.response
      ? `HTTP ${err.response.status}`
      : err.message;
    console.error("[bot] Query error:", msg);
    bot.chat(`Error consultando el RAG: ${msg.slice(0, 100)}`);
  }
});
