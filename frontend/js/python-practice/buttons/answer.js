import { PATHS } from "../constants.js";

document.querySelectorAll(".answerbtn").forEach((btn) => {
  btn.addEventListener("click", handleAnswer);
});

function escapeHTML(str = "") {
  return String(str).replace(/[&<>]/g, (ch) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[ch]));
}

function renderAnswer({ answer = "", explanation = "", lang = "python" } = {}) {
  const outputEl = document.querySelector("#output");
  if (!outputEl) return console.warn("⚠️ 找不到 #output");

  const codeId = `code-${Date.now()}`;

  const html = `
    <p>以下是其中一種範例解答：</p
    ><div class="code-block"
      ><div class="code-header"
        ><span class="lang-label">${lang}</span
        ><button class="copy-btn" data-target="${codeId}">複製程式碼</button 
      ></div
      ><pre><code id="${codeId}" class="language-${lang}">${escapeHTML(answer)}</code></pre
    ></div
    ><p>說明：</p
    ><p>${escapeHTML(explanation).replace(/\n/g, "<br>")}</p
    ><br><div class="openChat"><b>需要求助家教嗎? 請點我</b></div>
  `;

  outputEl.innerHTML = html;

  // 啟動 highlight.js
  if (window.hljs) hljs.highlightAll();

  // 綁定複製按鈕事件
  document.querySelectorAll(".copy-btn").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const targetId = btn.getAttribute("data-target");
      const codeEl = document.getElementById(targetId);
      if (!codeEl) return;

      try {
        await navigator.clipboard.writeText(codeEl.textContent);
        btn.textContent = "✅ 已複製";
        setTimeout(() => (btn.textContent = "複製程式碼"), 1500);
      } catch (err) {
        console.error("複製失敗：", err);
        btn.textContent = "❌ 複製失敗";
        setTimeout(() => (btn.textContent = "複製程式碼"), 1500);
      }
    });
  });
}

export async function handleAnswer(e) {
  e.preventDefault();
  try {
    const root = e?.target?.closest?.("[data-problem-id],[data-id]") || document;

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

    if (!resp.ok) {
      show(`取得解答失敗（HTTP ${resp.status}）`);
      return;
    }

    const data = await resp.json().catch(() => ({}));

    if (data?.ok && (data.answer || data.explanation)) {
      // 若你的後端會傳語言，可用 data.lang；預設 python
      renderAnswer({
        answer: data.answer || "",
        explanation: data.explanation || "",
        lang: data.lang || "python",
      });
    } else {
      show("取得解答失敗");
    }
  } catch (err) {
    show(`[錯誤] ${err?.message || err}`);
  }
}

function show(text, lang = "python") {
  const outputEl = document.querySelector("#output");
  if (!outputEl) return console.warn("⚠️ 找不到 #output");

  // 判斷是否像程式碼（多行或含符號）
  const isCodeLike = /[\n{};=<>\[\]()]/.test(text);

  let html;
  if (isCodeLike) {
    html = `
      <pre><code class="language-${lang}">${escapeHTML(text)}</code></pre>
    `;
  } else {
    html = `<p>${escapeHTML(text)}</p>`;
  }

  outputEl.innerHTML = html;
  if (window.hljs) hljs.highlightAll();
}
