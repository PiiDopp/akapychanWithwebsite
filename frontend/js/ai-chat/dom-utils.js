// 通用 DOM 工具 & 渲染工具（el、bold、code、高亮、捲動）
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
  const parts = String(text).split(/```/);
  for (let i = 0; i < parts.length; i++) {
    const seg = parts[i];
    if (i % 2 === 0) {
      const p = document.createElement("p");
      p.appendChild(renderBoldText(seg));
      wrap.appendChild(p);
    } else {
      const m = seg.match(/^([a-zA-Z0-9+#\-.]+)?\n([\s\S]*)$/);
      const lang = m ? m[1] : "";
      const codeText = m ? m[2] : seg;
      const pre = document.createElement("pre");
      const code = document.createElement("code");
      if (lang) code.className = `language-${lang}`;
      code.textContent = codeText;
      pre.appendChild(code);
      wrap.appendChild(pre);
    }
  }
  return wrap;
}

export function applyHLJS(container) {
  if (!window.hljs) return;
  container.querySelectorAll("pre code").forEach((block) => {
    window.hljs.highlightElement(block);
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