// 通用 DOM 工具 & 渲染工具（el、bold、code、高亮、捲動）
// --- 新增：安全轉義 ---
function escapeHTML(str = "") {
  return String(str).replace(/[&<>]/g, ch => (
    ch === "&" ? "&amp;" : ch === "<" ? "&lt;" : "&gt;"
  ));
}

// --- 新增：建立「帶複製鍵」的 code 區塊 HTML ---
function buildCodeBlockHtml(code, lang = "python") {
  const id = `code-${Date.now()}-${Math.random().toString(36).slice(2)}`;
  return `
    <div class="code-block">
      <div class="code-header">
        <span class="lang-label">${escapeHTML(lang)}</span>
        <button class="copy-btn" data-target="${id}" title="複製程式碼">複製程式碼</button>
      </div>
      <pre><code id="${id}" class="language-${escapeHTML(lang)}">${escapeHTML(code)}</code></pre>
    </div>
  `;
}

// --- 你原本的 ---
export function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text != null) node.textContent = String(text);
  return node;
}

export function renderBoldText(text) {
  const safe = String(text).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");
  const html = safe.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
  const span = document.createElement("span");
  span.innerHTML = html;
  return span;
}

export function renderMessageWithCode(text) {
  const wrap = document.createElement("div");
  wrap.className = "ai-rich-content";

  const raw = String(text);
  const parts = raw.split(/```/); // 偶數:文字, 奇數:程式碼

  for (let i = 0; i < parts.length; i++) {
    const seg = parts[i];

    if (i % 2 === 0) {
      const p = document.createElement("p");
      p.appendChild(renderBoldText(seg));
      wrap.appendChild(p);
    } else {
      const m = seg.match(/^([a-zA-Z0-9+#\-.]+)?\n([\s\S]*)$/);
      const lang = (m ? m[1] : "plaintext") || "plaintext";
      const codeText = (m ? m[2] : seg) || "";

      const holder = document.createElement("div");
      holder.innerHTML = buildCodeBlockHtml(codeText, lang);
      wrap.appendChild(holder.firstElementChild); 
    }
  }
  return wrap;
}

// --- HLJS 上色：維持你的版本 ---
export function applyHLJS(container) {
  if (!window.hljs) return;
  container.querySelectorAll("pre code").forEach((block) => {
    window.hljs.highlightElement(block);
  });
}

// --- 事件委派：一次綁在根（或 chat 容器）即可 ---
export function installCopyDelegation(root = document) {
  root.addEventListener("click", async (e) => {
    const btn = e.target.closest(".copy-btn");
    if (!btn) return;

    const code = document.getElementById(btn.dataset.target);
    if (!code) return;

    const original = btn.textContent;
    try {
      // 直接複製 <code> 的純文字（已是高亮前的內容）
      await navigator.clipboard.writeText(code.textContent);
      btn.textContent = "✅ 已複製";
    } catch {
      // 部分瀏覽器／HTTP 環境可能限制 clipboard；可加 textarea 備援
      btn.textContent = "❌ 失敗";
    } finally {
      setTimeout(() => (btn.textContent = original), 1500);
    }
  });
}

export function isNearBottom(elem, gap = 48) {
  return elem.scrollHeight - elem.scrollTop - elem.clientHeight < gap;
}

export function scrollToBottom(elem, force = false) {
  if (force || isNearBottom(elem)) {
    elem.scrollTop = elem.scrollHeight;
    window.scrollTo({ top: document.documentElement.scrollHeight, behavior: "smooth" });
  }
}
