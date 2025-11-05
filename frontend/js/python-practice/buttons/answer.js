import { PATHS } from "../constants.js";

document.querySelectorAll(".answerbtn").forEach((btn) => {
  btn.addEventListener("click", handleAnswer);
});

export async function handleAnswer(e) {
  e.preventDefault();
  try {
    const root =
      e?.target?.closest?.("[data-problem-id],[data-id]") || document;

    const problemId =
      root.getAttribute?.("data-problem-id") ||
      root.getAttribute?.("data-id") ||
      document.querySelector("#problem_id")?.value?.trim() ||
      window.currentDataId || // setCurrentQuestion() 會設定
      "";

    // 🔹 找題目索引（練習編號）
    const practiceIdxRaw =
      root.getAttribute?.("data-practice-idx") ||
      document.querySelector("#practice_idx")?.value ||
      window.currentPracticeIdx ||
      0;

    const practiceIdx = Number(practiceIdxRaw);

    if (!problemId) {
      show("請先輸入題目 ID");
      return;
    }

    const resp = await fetch(PATHS.answer, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        problem_id: problemId,
        practice_idx: isNaN(practiceIdx) ? 0 : practiceIdx,
      }),
    });

    const data = await resp.json().catch(() => ({}));
    if (data.ok) {
      show(
        `${data.answer ?? "（沒有解答）"}\n\n說明：\n${data.explanation ?? ""}`
      );
    } else {
      show("取得解答失敗");
    }
  } catch (err) {
    show(`[錯誤] ${err.message || err}`);
  }
}

function show(text) {
  const el = document.querySelector("#output");
  if (el) el.textContent = text;
}
