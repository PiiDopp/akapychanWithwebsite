// 鍵盤/按鈕事件集中
export function bindEnterToSend(textarea, sendBtn, onResize) {
  const autoResize = () => {
    textarea.style.height = "auto";
    textarea.style.height = Math.min(textarea.scrollHeight, 200) + "px";
    onResize && onResize();
  };
  ["input", "keydown"].forEach((evt) => textarea.addEventListener(evt, autoResize));
  autoResize();

  textarea.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendBtn.click();
    }
  });
}