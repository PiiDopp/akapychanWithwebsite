// 純函式工具
export function escapeHtml(s = "") {
  return String(s)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

// 判斷字串是否像程式碼
export function looksLikeCode(s = "") {
  if (!s) return false;
  const t = String(s);
  const lines = t.split(/\r?\n/).filter(Boolean);
  if (lines.length >= 2) return true;
  return /[(){}[\];=:]|=>|==|!=|<=|>=|\b(def|class|if|elif|else|for|while|return|print|import|from|const|let|var|function)\b/.test(t);
}

// 文字 -> <pre>
export function makePreFromText(text = "") {
  const pre = document.createElement("pre");
  pre.textContent = String(text).replace(/\r\n/g, "\n");
  return pre;
}