// 建立單一「範例」區塊
import { renderTabbedTable } from "./tableFromTabbed.js";

export function makeExpItem(block, lang = "python", parseTable = false) {
  const li = document.createElement("li");
  li.className = "exp";

  const table = parseTable ? renderTabbedTable(block) : null;
  if (table) {
    li.appendChild(table);
  } else {
    const pre = document.createElement("pre");
    const code = document.createElement("code");
    code.className = `language-${lang}`;
    code.textContent = String(block ?? "").replace(/\r\n/g, "\n");
    pre.appendChild(code);
    li.appendChild(pre);
  }
  return li;
}