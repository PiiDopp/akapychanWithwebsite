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
  const m = raw.match(/^([a-zA-Z0-9+#\-.]+)?\n([\s\S]*)$/);
  const lang = m ? m[1] : "";
  const codeText = m ? m[2] : raw;
  const pre = document.createElement("pre");
  const code = document.createElement("code");
  if (lang) code.className = `language-${lang}`;
  code.textContent = codeText;
  pre.appendChild(code);
  container.appendChild(pre);
  applyHLJS(pre);
  scrollCb && scrollCb();
  onDone && onDone();
}