// 動態載入 highlight.js 資源
import { HLJS_CSS, HLJS_JS } from "./constants.js";

export function ensureHLJSAssets() {
  if (!document.querySelector(`link[href="${HLJS_CSS}"]`)) {
    const link = document.createElement("link");
    link.rel = "stylesheet";
    link.href = HLJS_CSS;
    document.head.appendChild(link);
  }
  if (!document.querySelector(`script[src="${HLJS_JS}"]`)) {
    const s = document.createElement("script");
    s.src = HLJS_JS;
    s.defer = true;
    document.head.appendChild(s);
  }
}