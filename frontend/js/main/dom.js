// DOM 輔助工具
export function ensurePreHasCode(root, defaultLang = "python") {
  root.querySelectorAll("pre").forEach(pre => {
    if (!pre.querySelector("code")) {
      const code = document.createElement("code");
      code.className = `language-${defaultLang}`;
      code.textContent = pre.textContent;
      pre.textContent = "";
      pre.appendChild(code);
    }
  });
}

// 載入單元後滑到頁面最上面（平滑捲動；含常見自訂滾動容器）
export function scrollToTop() {
  const se = document.scrollingElement || document.documentElement || document.body;
  if (se && typeof se.scrollTo === "function") {
    se.scrollTo({ top: 0, behavior: "smooth" });
  } else if (se) {
    se.scrollTop = 0;
  }
  document.querySelectorAll('.main, .content, .container, .textContent, [data-scroll-root]').forEach(el => {
    try { el.scrollTop = 0; } catch {}
  });
}