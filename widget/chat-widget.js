/**
 * chat-widget.js — Widget de chat embebible para el RAG de Minecraft.
 *
 * Uso en cualquier página:
 *   <link rel="stylesheet" href="/widget/chat-widget.css">
 *   <script src="/widget/chat-widget.js" data-api="https://tu-api.com"></script>
 *
 * El widget se inyecta automáticamente al cargar. Toma la URL de la API
 * del atributo data-api del script. Default: http://localhost:8000
 */

(function () {
  const scriptTag = document.currentScript;
  const API_URL = (scriptTag && scriptTag.dataset.api) || "http://localhost:8000";

  const HTML = `
    <button class="rag-widget-bubble" id="rag-bubble" aria-label="Abrir chat">⛏️</button>
    <div class="rag-widget-panel" id="rag-panel" role="dialog" aria-label="Chat asistente Minecraft">
      <div class="rag-widget-header">
        <span>🌱 Minecraft Wiki Assistant</span>
        <button class="rag-widget-close" id="rag-close" aria-label="Cerrar">×</button>
      </div>
      <div class="rag-widget-body" id="rag-body">
        <div class="rag-msg rag-msg-bot">
          ¡Hola aventurero! 👋<br>
          Puedo responder cualquier pregunta sobre Minecraft usando la wiki oficial. Ejemplos:<br>
          • ¿Cómo se craftea un Beacon?<br>
          • ¿Qué dropea el Ender Dragon?<br>
          • ¿Cómo funciona la encantación Fortune?<br>
          • ¿Qué cambios trajo la 1.20?
        </div>
      </div>
      <div class="rag-widget-input-row">
        <input type="text" class="rag-widget-input" id="rag-input"
               placeholder="Pregunta lo que quieras..." autocomplete="off">
        <button class="rag-widget-send" id="rag-send">Enviar</button>
      </div>
    </div>
  `;

  const container = document.createElement("div");
  container.innerHTML = HTML;
  document.body.appendChild(container);

  const bubble = document.getElementById("rag-bubble");
  const panel = document.getElementById("rag-panel");
  const closeBtn = document.getElementById("rag-close");
  const body = document.getElementById("rag-body");
  const input = document.getElementById("rag-input");
  const sendBtn = document.getElementById("rag-send");

  bubble.addEventListener("click", () => panel.classList.add("rag-open"));
  closeBtn.addEventListener("click", () => panel.classList.remove("rag-open"));

  function appendMsg(text, who, sources) {
    const div = document.createElement("div");
    div.className = "rag-msg " + (who === "user" ? "rag-msg-user" : "rag-msg-bot");
    div.textContent = text;

    if (sources && sources.length) {
      const srcDiv = document.createElement("div");
      srcDiv.className = "rag-sources";
      srcDiv.innerHTML = "<strong>📚 Fuentes:</strong>";
      sources.forEach((s, i) => {
        const item = document.createElement("div");
        item.className = "rag-source-item";
        // Link al artículo en la wiki
        if (s.url) {
          item.innerHTML = `[${i + 1}] <a href="${s.url}" target="_blank" rel="noopener">${s.title}</a> <span style="color:#888">(${s.category}, score ${s.score})</span>`;
        } else {
          item.textContent = `[${i + 1}] ${s.title} (score ${s.score})`;
        }
        srcDiv.appendChild(item);
      });
      div.appendChild(srcDiv);
    }

    body.appendChild(div);
    body.scrollTop = body.scrollHeight;
    return div;
  }

  async function sendQuery() {
    const q = input.value.trim();
    if (!q) return;

    appendMsg(q, "user");
    input.value = "";
    sendBtn.disabled = true;

    const loading = appendMsg("⛏️ Minando la respuesta...", "bot");
    loading.classList.add("rag-loading");

    try {
      const res = await fetch(`${API_URL}/query`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        // 📚 source:"widget" para poder filtrar en el benchmark por origen.
        body: JSON.stringify({ question: q, source: "widget" }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();

      loading.remove();
      appendMsg(data.answer, "bot", data.sources);
    } catch (e) {
      loading.remove();
      appendMsg(`Error: ${e.message}. ¿La API está corriendo en ${API_URL}?`, "bot");
    } finally {
      sendBtn.disabled = false;
      input.focus();
    }
  }

  sendBtn.addEventListener("click", sendQuery);
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter") sendQuery();
  });
})();
