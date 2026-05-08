// Agent Shell UI: vanilla JS, sessionStorage for API key, SSE streaming.

const keyInput = document.getElementById("api-key");
const keyStatus = document.getElementById("key-status");
const form = document.getElementById("chat-form");
const userInput = document.getElementById("user-input");
const convo = document.getElementById("conversation");
const skillList = document.getElementById("skill-list");

// ── API key (sessionStorage; clears on tab close) ─────────────────────────
const stored = sessionStorage.getItem("anthropic_key");
if (stored) { keyInput.value = stored; keyStatus.textContent = "key set"; }
keyInput.addEventListener("change", () => {
  sessionStorage.setItem("anthropic_key", keyInput.value);
  keyStatus.textContent = keyInput.value ? "key set" : "key required";
});

// ── Render skill sidebar from /skills ──────────────────────────────────────
async function renderSkills() {
  try {
    const r = await fetch("/skills");
    const skills = await r.json();
    skillList.innerHTML = skills.map(s => `
      <li>
        <b>${s.name}</b>
        <span>${truncate(s.description, 140)}</span>
      </li>
    `).join("");
  } catch (e) {
    skillList.innerHTML = `<li class="error">Failed to load /skills</li>`;
  }
}
function truncate(s, n) { return s.length > n ? s.slice(0, n - 1) + "…" : s; }
renderSkills();

// ── DOM helpers ────────────────────────────────────────────────────────────
function addBlock(role, text) {
  const div = document.createElement("div");
  div.className = `msg ${role}`;
  div.textContent = text;
  convo.appendChild(div);
  convo.scrollTop = convo.scrollHeight;
  return div;
}

function addToolUse(name, input) {
  const div = document.createElement("div");
  div.className = "tool-use";
  div.innerHTML = `<b>→ ${name}</b><pre>${escapeHtml(JSON.stringify(input, null, 2))}</pre>`;
  convo.appendChild(div);
  convo.scrollTop = convo.scrollHeight;
}

function addToolResult(name, result) {
  const div = document.createElement("div");
  div.className = "tool-result " + (result.ok ? "ok" : "fail");
  const mark = result.ok ? "✓" : "✗";
  div.innerHTML = `<b>${mark} ${name}</b><pre>${escapeHtml(JSON.stringify(result, null, 2))}</pre>`;
  convo.appendChild(div);
  convo.scrollTop = convo.scrollHeight;
}

function escapeHtml(s) {
  return s.replace(/[&<>"']/g, c => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
  }[c]));
}

// ── Conversation state ─────────────────────────────────────────────────────
const messages = [];

// Enter to send, Shift+Enter for newline. Matches the ChatGPT / Claude.ai /
// Slack convention. The textarea is intentionally still resizable so the user
// can compose multi-line prompts; Shift+Enter inserts a newline.
userInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey && !e.isComposing) {
    e.preventDefault();
    form.requestSubmit();
  }
});

// Example prompt buttons. Each carries the exact text in data-prompt; click
// fills the textarea and submits, mimicking the user typing it themselves.
// The whole #examples block is removed on first form submit (whether
// triggered by a button, Enter, or the Send button) so the chat area
// becomes a clean transcript once the conversation starts.
const examplesEl = document.getElementById("examples");
if (examplesEl) {
  examplesEl.querySelectorAll("button.example").forEach((btn) => {
    btn.addEventListener("click", () => {
      userInput.value = btn.dataset.prompt;
      form.requestSubmit();
    });
  });
  form.addEventListener("submit", () => {
    examplesEl.remove();
  }, { once: true });
}

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  const text = userInput.value.trim();
  if (!text) return;
  if (!keyInput.value) {
    alert("Enter your Anthropic API key in the top bar first.");
    keyInput.focus();
    return;
  }

  addBlock("user", text);
  messages.push({ role: "user", content: text });
  userInput.value = "";
  userInput.disabled = true;
  // Show a "thinking" indicator immediately so the user knows the request
  // is in flight. It's removed when the first SSE event arrives (text or
  // tool_use), or on error / completion.
  let thinkingBlock = addBlock("thinking", "Claude is analysing");
  function clearThinking() {
    if (thinkingBlock) { thinkingBlock.remove(); thinkingBlock = null; }
  }

  let resp;
  try {
    resp = await fetch("/chat", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Anthropic-Key": keyInput.value,
      },
      body: JSON.stringify({ messages }),
    });
  } catch (err) {
    clearThinking();
    addBlock("error", `network error: ${err.message}`);
    userInput.disabled = false;
    return;
  }

  if (!resp.ok) {
    clearThinking();
    const body = await resp.text().catch(() => "");
    addBlock("error", `HTTP ${resp.status}: ${body || resp.statusText}`);
    userInput.disabled = false;
    return;
  }

  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let textBlock = null;

  // Track assistant content for next-turn replay (text + tool_use blocks).
  // The server is the source of truth; we just append the user-visible
  // events as we get them. Conversation continuity is handled server-side
  // since each /chat call replays the full messages list.
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const events = buffer.split("\n\n");
    buffer = events.pop();
    for (const evt of events) {
      const lines = evt.split("\n");
      const type = lines.find(l => l.startsWith("event:"))?.slice(7).trim();
      const dataLine = lines.find(l => l.startsWith("data:"));
      if (!type || !dataLine) continue;
      let payload;
      try { payload = JSON.parse(dataLine.slice(5).trim()); } catch { continue; }

      if (type === "text") {
        clearThinking();
        if (!textBlock) textBlock = addBlock("assistant", "");
        textBlock.textContent += payload.text;
      } else if (type === "tool_use") {
        clearThinking();
        textBlock = null;
        addToolUse(payload.name, payload.input);
      } else if (type === "tool_result") {
        clearThinking();
        addToolResult(payload.name, payload.result);
      } else if (type === "done") {
        clearThinking();
        textBlock = null;
        if (payload.warning) addBlock("error", payload.warning);
      } else if (type === "error") {
        clearThinking();
        addBlock("error", payload.error || "unknown error");
      }
    }
  }

  // After server sends done, we don't track assistant turns client-side
  // since the server replays full messages each call. For multi-turn we
  // rebuild messages from the last assistant text only:
  const lastTexts = [...convo.querySelectorAll(".msg.assistant")].map(d => d.textContent);
  if (lastTexts.length) {
    messages.push({ role: "assistant", content: lastTexts[lastTexts.length - 1] });
  }
  userInput.disabled = false;
  userInput.focus();
});
