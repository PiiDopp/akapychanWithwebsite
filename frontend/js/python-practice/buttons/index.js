import { SELECTORS } from "../constants.js";
import { handleRun } from "./run.js";
import { handleHint } from "./hint.js";
import { handleAnswer } from "./answer.js";
import { installTranslateModule } from "./translate.js";

export function setupButtons() {
  // 單一事件委派：所有按鈕點擊都在這裡統一轉派
  document.addEventListener("click", (e) => {
    const t = e.target;
    if (t.matches(SELECTORS.runBtn)) return handleRun(e);
    if (t.matches(SELECTORS.hintBtn)) return handleHint(e);
    if (t.matches(SELECTORS.answerBtn)) return handleAnswer(e);
    if (t.matches(".translateToggleBtn")) return installTranslateModule(e);
  });

  // 初始化翻譯按鈕（translate.js 會動態在每個 .textContent 插入按鈕）
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", installTranslateModule, {
      once: true,
    });
  } else {
    installTranslateModule();
  }
}
