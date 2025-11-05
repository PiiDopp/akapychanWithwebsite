// 產生聊天列（incoming/outgoing）
import { el } from "./dom-utils.js";

export function createChatLi(message, className) {
  const li = el("li", `chat ${className}`);

  if (className === "chat-incoming") {
    // 左側小機器人
    const icon = document.createElement("i");
    icon.className = "fas fa-robot";
    li.appendChild(icon);

    // 內容包一層 .ai-rich-content（和你的 HTML 一致）
    const wrap = document.createElement("div");
    wrap.className = "ai-rich-content";
    const p = document.createElement("p");
    p.appendChild(document.createTextNode(String(message)));
    wrap.appendChild(p);
    li.appendChild(wrap);
  } else {
    // 使用者訊息（右側）
    const p = document.createElement("p");
    p.appendChild(document.createTextNode(String(message)));
    li.appendChild(p);
  }

  return li;
}