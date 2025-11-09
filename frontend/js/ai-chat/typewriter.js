// 打字機與插入程式碼區塊
import { renderBoldText, applyHLJS } from "./dom-utils.js";

export function typeParagraph(container, seg, onDone, scrollCb) {
  const p = document.createElement("p");
  container.appendChild(p);
  let j = 0;
  const tick = () => {
    if (j >= seg.length) {
      const rich = renderBoldText(p.textContent);
      p.innerHTML = rich.innerHTML;
      onDone && onDone();
      return;
    }
    const next = seg.slice(j, j + 2);
    p.textContent += next;
    j += 2;
    scrollCb && scrollCb();
    const delay = /[,.!?，。！？；;:\n]/.test(next[next.length - 1]) ? 80 : 25;
    setTimeout(tick, delay);
  };
  tick();
}

export function insertCodeBlock(container, raw, onDone, scrollCb) {
  // 解析 ```lang\ncode```；lang 可省略
  const m = String(raw).match(/^([a-zA-Z0-9+#\-.]+)?\n([\s\S]*)$/);
  const lang = (m ? m[1] : "plaintext") || "plaintext";
  const codeText = (m ? m[2] : String(raw)) || "";

  // 建立外層區塊 + 標題列 + 複製鍵
  const id = `code-${Date.now()}-${Math.random().toString(36).slice(2)}`;

  const block = document.createElement("div");
  block.className = "code-block";

  const header = document.createElement("div");
  header.className = "code-header";

  const label = document.createElement("span");
  label.className = "lang-label";
  label.textContent = lang;

  const btn = document.createElement("button");
  btn.className = "copy-btn";
  btn.setAttribute("data-target", id);
  btn.title = "複製程式碼";
  btn.textContent = "複製程式碼";

  header.appendChild(label);
  header.appendChild(btn);

  const pre = document.createElement("pre");
  const code = document.createElement("code");
  code.id = id;
  code.className = `language-${lang}`;
  code.textContent = codeText; // 用 textContent 安全插入

  pre.appendChild(code);
  block.appendChild(header);
  block.appendChild(pre);
  container.appendChild(block);

  // 單塊上色（效率比 highlightAll 好）
  if (window.hljs && code) window.hljs.highlightElement(code);
  else applyHLJS(pre); // 你的輔助函式也可

  // 捲到底 & 回呼
  if (typeof scrollCb === "function") scrollCb();
  if (typeof onDone === "function") onDone();
}