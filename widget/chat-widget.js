/**
 * chat-widget.js — Chat del RAG de Minecraft, en dos modos:
 *
 *   1. Página completa: si la página tiene <main id="rag-app">, el chat ocupa ese espacio
 *      (así funciona /widget/).
 *   2. Widget flotante: en cualquier otra página se inyecta un bloque de pasto en la esquina
 *      que abre el chat.
 *        <link rel="stylesheet" href="https://tu-api.com/widget/chat-widget.css">
 *        <script src="https://tu-api.com/widget/chat-widget.js" data-api="https://tu-api.com"></script>
 *
 * La URL de la API sale de data-api; si no viene y la página la sirve la propia API, usa ese origen.
 */

(function () {
  const scriptTag = document.currentScript;
  const API_URL =
    (scriptTag && scriptTag.dataset.api) ||
    (location.protocol.startsWith("http") ? location.origin : "http://localhost:8000");
  const ASSET = (name) => new URL(name, scriptTag ? scriptTag.src : location.href).href;

  const EXAMPLES = [
    "¿Cómo hago una poción de velocidad?",
    "¿Cómo invoco al Wither?",
    "¿Qué hace un observer?",
    "Tomé una poción de Bad Omen y no pasó nada, ¿qué hace?",
  ];

  const CHAT_HTML = `
    <section class="rag-chat">
      <div class="rag-body" id="rag-body" aria-live="polite"></div>
      <form class="rag-input-row" id="rag-form">
        <input type="text" class="rag-input" id="rag-input" aria-label="Pregunta"
               placeholder="Escribe tu pregunta..." autocomplete="off">
        <button class="mc-btn" id="rag-send" type="submit">Enviar</button>
      </form>
    </section>`;

  // --- Montaje según el modo ---
  const mount = document.getElementById("rag-app");
  if (mount) {
    mount.innerHTML = CHAT_HTML;
  } else {
    const container = document.createElement("div");
    container.innerHTML = `
      <button class="rag-widget-bubble" id="rag-bubble" aria-label="Abrir chat de Minecraft">
        <img src="${ASSET("grass-block.svg")}" alt="">
      </button>
      <div class="rag-widget-panel" id="rag-panel" role="dialog" aria-label="Chat asistente Minecraft">
        <div class="rag-widget-header">
          <img src="${ASSET("grass-block.svg")}" alt="">
          <span>Minecraft Wiki Assistant</span>
          <button class="mc-btn rag-widget-close" id="rag-close" aria-label="Cerrar">×</button>
        </div>
        ${CHAT_HTML}
      </div>`;
    document.body.appendChild(container);
    const panel = document.getElementById("rag-panel");
    document.getElementById("rag-bubble").addEventListener("click", () => panel.classList.toggle("rag-open"));
    document.getElementById("rag-close").addEventListener("click", () => panel.classList.remove("rag-open"));
  }

  const body = document.getElementById("rag-body");
  const form = document.getElementById("rag-form");
  const input = document.getElementById("rag-input");
  const sendBtn = document.getElementById("rag-send");

  function escapeHtml(s) {
    return s.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }

  // 📚 Markdown mínimo para las respuestas del LLM: títulos, viñetas, negritas
  // y saltos de línea. Se escapa el HTML ANTES de transformar, así una respuesta
  // nunca puede inyectar etiquetas en la página que embebe el widget.
  function renderMarkdown(text) {
    return escapeHtml(text)
      .split("\n")
      .map((line) =>
        line
          .replace(/^#{1,6}\s+(.*)$/, "<strong>$1</strong>")
          .replace(/^\s*[-*]\s+/, "• ")
          .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
      )
      .join("<br>");
  }

  // 📚 Varias fuentes suelen ser chunks del mismo artículo: se agrupan por título
  // conservando los números que cita la respuesta ([1-3] Potion of Swiftness).
  function groupSources(sources) {
    const groups = [];
    sources.forEach((s, i) => {
      let g = groups.find((x) => x.title === s.title);
      if (!g) {
        g = { title: s.title, url: s.url, category: s.category, refs: [] };
        groups.push(g);
      }
      g.refs.push(i + 1);
    });
    return groups;
  }

  // [1, 2, 3, 5] → "1-3, 5"
  function formatRefs(refs) {
    const parts = [];
    let start = refs[0];
    let prev = refs[0];
    for (const n of refs.slice(1).concat([null])) {
      if (n === prev + 1) {
        prev = n;
        continue;
      }
      parts.push(start === prev ? `${start}` : `${start}-${prev}`);
      start = prev = n;
    }
    return parts.join(", ");
  }

  function addToBody(el) {
    body.appendChild(el);
    body.scrollTop = body.scrollHeight;
    return el;
  }

  function appendUser(text) {
    const div = document.createElement("div");
    div.className = "rag-msg rag-msg-user";
    div.innerHTML = `<span class="rag-chat-name">&lt;Tú&gt;</span> ${escapeHtml(text)}`;
    return addToBody(div);
  }

  function appendBot(answer, sources) {
    const div = document.createElement("div");
    div.className = "rag-msg rag-msg-bot";
    div.innerHTML = renderMarkdown(answer);

    if (sources && sources.length) {
      const srcDiv = document.createElement("div");
      srcDiv.className = "rag-sources";
      srcDiv.innerHTML = '<span class="rag-sources-label">Fuentes</span>';
      groupSources(sources).forEach((g) => {
        const item = document.createElement("div");
        item.className = "rag-source-item";
        const refs = `[${formatRefs(g.refs)}]`;
        if (g.url) {
          item.innerHTML = `${refs} <a href="${escapeHtml(g.url)}" target="_blank" rel="noopener">${escapeHtml(g.title)}</a> (${escapeHtml(g.category)})`;
        } else {
          item.textContent = `${refs} ${g.title}`;
        }
        srcDiv.appendChild(item);
      });
      div.appendChild(srcDiv);
    }
    return addToBody(div);
  }

  function appendError(text) {
    const div = document.createElement("div");
    div.className = "rag-msg rag-msg-bot rag-msg-error";
    div.textContent = text;
    return addToBody(div);
  }

  function appendLoading() {
    const div = document.createElement("div");
    div.className = "rag-msg rag-msg-bot rag-loading";
    div.innerHTML = 'Minando la respuesta...<div class="rag-progress"><div></div></div>';
    return addToBody(div);
  }

  function appendWelcome() {
    const div = document.createElement("div");
    div.className = "rag-welcome mc-panel";
    div.innerHTML = `
      <img src="${ASSET("grass-block.svg")}" alt="">
      <h2>¡Hola, aventurero!</h2>
      <p>Pregúntame lo que quieras de Minecraft en español. Respondo con la wiki oficial y te digo de dónde saqué cada dato.</p>
      <div class="rag-examples"></div>`;
    const examples = div.querySelector(".rag-examples");
    EXAMPLES.forEach((q) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "mc-btn";
      btn.textContent = q;
      btn.addEventListener("click", () => sendQuery(q));
      examples.appendChild(btn);
    });
    return addToBody(div);
  }

  async function sendQuery(question) {
    const q = (question || input.value).trim();
    if (!q || sendBtn.disabled) return;

    appendUser(q);
    input.value = "";
    sendBtn.disabled = true;
    const loading = appendLoading();

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
      appendBot(data.answer, data.sources);
    } catch (e) {
      loading.remove();
      appendError(`Error: ${e.message}. ¿La API está corriendo en ${API_URL}?`);
    } finally {
      sendBtn.disabled = false;
      input.focus();
    }
  }

  form.addEventListener("submit", (e) => {
    e.preventDefault();
    sendQuery();
  });
  appendWelcome();
})();
