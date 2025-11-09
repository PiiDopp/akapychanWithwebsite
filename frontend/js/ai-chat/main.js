import { ensureHLJSAssets } from "./assets.js";
import { SELECTORS } from "./constants.js";
import { scrollToBottom } from "./dom-utils.js";
import { installCopyDelegation } from "./dom-utils.js";
import { typeParagraph, insertCodeBlock } from "./typewriter.js";
import { createChatLi } from "./render.js";
import { bindEnterToSend } from "./events.js";
import { mountToolbars } from "./toolbars.js";
import {
  messages,
  pushMsg,
  currentChatId,
  chosenMode,
  setChosenMode,
  consumePendingMode,
} from "./state.js";
import { chatToBackend } from "./transport.js";

console.log("[ai-chat] 模組載入成功");

if (!window.__chat_inited) {
  window.__chat_inited = true;

  window.addEventListener("DOMContentLoaded", () => {
    ensureHLJSAssets();

    installCopyDelegation(document);

    const chatRoot = document.querySelector(SELECTORS.chatRoot);
    const chatInput = chatRoot?.querySelector("textarea");
    const sendBtn = chatRoot?.querySelector("i");
    const chatbox = document.querySelector(SELECTORS.chatbox);
    if (!chatInput || !sendBtn || !chatbox) {
      console.warn("[chat] 缺少必要節點，略過初始化。");
      return;
    }

    // 工具：把文字塞進 textarea 並觸發送出
    function sendViaUI(arg) {
      if (typeof arg === "string") {
        chatInput.value = arg; // payload = 字串
        chatInput.removeAttribute("data-display");
      } else if (arg && typeof arg === "object") {
        chatInput.value = arg.payload ?? ""; // 寫入要送後端的 payload
        if (arg.display) {
          chatInput.setAttribute("data-display", arg.display); // 顯示用文字
        } else {
          chatInput.removeAttribute("data-display");
        }
      }
      chatInput.dispatchEvent(new Event("input", { bubbles: true }));
      sendBtn.click();
    }

    const { analyzeAssistantText } = mountToolbars(
      chatRoot,
      chatbox,
      sendViaUI
    );

    const firstLi = document.querySelector(".chatbox .chat-incoming");
    const aiContent = firstLi?.querySelector(".ai-rich-content");
    const firstP = aiContent?.querySelector("p");

    if (firstP && aiContent) {
      // 先取出完整文字
      const originalText = firstP.textContent.trim();
      // 清空內容
      aiContent.innerHTML = "";
      // 開始逐字輸出
      import("./typewriter.js").then(({ typeParagraph }) => {
        typeParagraph(
          aiContent,
          originalText,
          () => {},
          () => {}
        );
      });
    }

    bindEnterToSend(chatInput, sendBtn);

    let isSending = false;
    let aborter = null;

    const handleChat = async () => {
      const userText = chatInput.value.trim(); // ← 送後端用的 payload
      if (!userText || isSending) return;

      // 顯示用文字（例如：進入 模式 1｜互動開發）
      const overrideDisplay = chatInput.getAttribute("data-display");
      const userDisplay = overrideDisplay || userText;
      chatInput.removeAttribute("data-display");

      isSending = true;
      sendBtn.classList.add("is-disabled");
      sendBtn.style.pointerEvents = "none";

      // 右側泡泡顯示「userDisplay」
      chatbox.appendChild(createChatLi(userDisplay, "chat-outgoing"));
      chatInput.value = "";
      scrollToBottom(chatbox, true);

      // 初始化 system 提示
      if (!messages.some((m) => m.role === "system")) {
        pushMsg("system", "你是助教，回覆請用繁體中文。");
      }

      // 判斷是否已選過模式（payload 以 1/2/3 表示）
      const hasChosenMode = messages.some(
        (m) =>
          m.role === "user" &&
          ["1", "2", "3"].includes(String(m.content).trim())
      );
      const isControlOnly = /^[MmNnYyAa]$/.test(userText);

      // 若還沒選過模式、且這次不是單鍵控制，就先補送模式（consumePendingMode 或預設 1）
      if (!hasChosenMode && !isControlOnly) {
        const pending = consumePendingMode();
        if (pending) {
          pushMsg("user", String(pending)); // ← 後端要的是 payload
          setChosenMode(String(pending));
        } else {
          pushMsg("user", "1");
          setChosenMode("1");
        }
      } else if (!hasChosenMode && isControlOnly && chosenMode) {
        pushMsg("user", chosenMode);
      }

      // 送本次使用者指令（payload）
      pushMsg("user", userText);

      // 建立左側「Thinking」
      const incomingLI = createChatLi("Thinking", "chat-incoming");
      chatbox.appendChild(incomingLI);
      scrollToBottom(chatbox, true);

      const wrapInit = incomingLI.querySelector(".ai-rich-content");
      let pNode = wrapInit?.querySelector("p");
      let dotCount = 0;
      let thinkingActive = true;
      const thinkingTimer = setInterval(() => {
        if (!thinkingActive || !pNode) return;
        dotCount = (dotCount + 1) % 4;
        pNode.textContent = "Thinking" + ".".repeat(dotCount);
      }, 400);

      try {
        aborter?.abort();
        aborter = new AbortController();

        const text = await chatToBackend(
          { chat_id: String(currentChatId), messages },
          aborter.signal
        );

        clearInterval(thinkingTimer);
        thinkingActive = false;

        let wrap = wrapInit;
        if (!wrap) {
          wrap = document.createElement("div");
          wrap.className = "ai-rich-content";
          if (pNode && pNode.isConnected) pNode.replaceWith(wrap);
          else incomingLI.appendChild(wrap);
        } else {
          wrap.innerHTML = "";
        }

        const scrollCb = () => scrollToBottom(chatbox);
        const finish = () => {
          pushMsg("assistant", text);
          analyzeAssistantText(text);
          scrollToBottom(chatbox, true);
        };

        if (/```/.test(text)) {
          const parts = text.split(/```/);
          let idx = 0;

          // 跳過一開始可能的空段
          while (idx < parts.length && /^\s*$/.test(parts[idx])) idx++;

          const step = () => {
            if (idx >= parts.length) return finish();
            const seg = parts[idx++];
            if ((idx - 1) % 2 === 0) {
              typeParagraph(wrap, seg, step, scrollCb);
            } else {
              insertCodeBlock(wrap, seg, step, scrollCb);
            }
          };
          setTimeout(step, 120);
        } else {
          typeParagraph(wrap, text, finish, scrollCb);
        }
      } catch (e) {
        const wrap =
          incomingLI.querySelector(".ai-rich-content") ||
          (() => {
            const w = document.createElement("div");
            w.className = "ai-rich-content";
            incomingLI.appendChild(w);
            return w;
          })();
        wrap.innerHTML = "";
        const p = document.createElement("p");
        p.textContent = `發生錯誤：${e?.message || e}`;
        wrap.appendChild(p);
      } finally {
        isSending = false;
        sendBtn.classList.remove("is-disabled");
        sendBtn.style.pointerEvents = "";
      }
    };

    sendBtn.addEventListener("click", handleChat);
  });
}
