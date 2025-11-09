import { PATHS } from "../constants.js";

document.querySelectorAll(".hintbtn").forEach((btn) => {
  btn.addEventListener("click", handleHint);
});

export async function handleHint(e) {
  e.preventDefault();
  const btn = e.currentTarget;
  const el = document.querySelector("#output");

  let stopAnim = null; // 用來停止動畫

  try {
    const root =
      e?.target?.closest?.("[data-problem-id],[data-id]") || document;

    const problemId =
      root.getAttribute?.("data-problem-id") ||
      root.getAttribute?.("data-id") ||
      document.querySelector("#problem_id")?.value?.trim() ||
      window.currentDataId ||
      "";

    const practiceIdxRaw =
      root.getAttribute?.("data-practice-idx") ||
      document.querySelector("#practice_idx")?.value ||
      window.currentPracticeIdx ||
      0;

    const practiceIdx = Number(practiceIdxRaw);

    const code =
      window.editor?.getValue?.() ??
      document.querySelector("#user_code")?.value ??
      "";

    if (!problemId || !code) {
      show("# 請先輸入您的程式碼，會針對你的程式碼，給予相對應的提示。");
      return;
    }

    // 🌀 顯示動畫「分析中...」
    stopAnim = startLoading(el, btn);

    const resp = await fetch(PATHS.hint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        problem_id: problemId,
        code,
      }),
    });

    const data = await resp.json().catch(() => ({}));
    show(data.ok ? data.hint ?? "（沒有提示）" : data.error ?? "取得提示失敗");
  } catch (err) {
    show(`[錯誤] ${err?.message ?? err}`);
  } finally {
    // ✅ 停止動畫
    if (stopAnim) stopAnim();
  }
}

// === 輔助函式 ===
function show(text) {
  const el = document.querySelector("#output");
  if (el) el.textContent = text;
}

/**
 * 顯示「分析中...」動畫
 * @param {HTMLElement} el - 要顯示文字的元素
 * @param {HTMLElement} btn - 觸發按鈕
 * @returns {Function} 停止動畫的函式
 */
function startLoading(el, btn) {
  if (btn) btn.disabled = true;
  if (el) el.textContent = "分析中";

  let dots = 0;
  const id = setInterval(() => {
    dots = (dots + 1) % 4;
    if (el) el.textContent = "分析中" + ".".repeat(dots);
  }, 400);

  // 停止動畫
  return () => {
    clearInterval(id);
    if (btn) btn.disabled = false;
  };
}