// 常數（API、HLJS、選擇器等）
export const HLJS_CSS =
  "https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/styles/github.min.css";
export const HLJS_JS =
  "https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/highlight.min.js";

export const SELECTORS = {
  chatRoot: ".chatinput",
  chatInput: ".chatinput textarea",
  sendBtn:  ".chatinput i",
  chatbox:  ".chatbox",
};

export const API_BASE = (typeof window.API_BASE === "string" ? window.API_BASE : "")
  .replace(/\/+$/, "");