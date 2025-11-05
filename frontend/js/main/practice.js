// 渲染練習題與互動邏輯
import { looksLikeCode, makePreFromText } from "./helpers.js";
import { ensurePreHasCode } from "./dom.js";

export function renderPractice(lesson) {
  const data = lesson.practice || lesson.quiz || [];

  let practiceSec = document.querySelector(".practice");
  if (!practiceSec) {
    const host = document.querySelector(".expContenter") || document.body;
    practiceSec = document.createElement("section");
    practiceSec.className = "practice";
    practiceSec.innerHTML = `<p><b># 練習題:</b></p><ol class="practice-list"></ol>`;
    host.appendChild(practiceSec);
  }
  const list = practiceSec.querySelector(".practice-list");
  list.innerHTML = "";

  if (data.length === 0) {
    practiceSec.style.display = "none";
    return;
  } else {
    practiceSec.style.display = "";
  }

  data.forEach((q, idx) => {
    const li = document.createElement("li");
    li.className = "practice-item";

    // ---- 題目 ----
    const question = document.createElement("div");
    question.className = "practice-q";
    const qText = q.question || `第 ${idx + 1} 題`;
    if (looksLikeCode(qText)) {
      question.appendChild(makePreFromText(qText));
    } else {
      question.textContent = qText;
    }

    // ---- 選項 ----
    const optionsWrap = document.createElement("div");
    optionsWrap.className = "practice-options";

    const options = (q.options || []).map((opt, optIdx) => {
      const optDiv = document.createElement("div");
      optDiv.className = "practice-opt";
      optDiv.dataset.key = String.fromCharCode(65 + optIdx);
      optDiv.dataset.full = String(opt).trim();

      if (looksLikeCode(opt)) {
        optDiv.appendChild(makePreFromText(opt));
      } else {
        optDiv.textContent = opt;
      }

      optionsWrap.appendChild(optDiv);
      return optDiv;
    });

    // ---- 詳解 ----
    const explain = document.createElement("div");
    explain.className = "practice-explain";
    const expText = q.explanation || "";
    if (looksLikeCode(expText)) {
      explain.appendChild(makePreFromText(expText));
    } else {
      explain.textContent = expText;
    }
    explain.style.display = "none";

    // ---- 判題 ----
    options.forEach((optDiv) => {
      optDiv.addEventListener("click", () => {
        const correct = String(q.answer || "").trim(); // "A" / "A. ..." / 完整選項
        const userKey = optDiv.dataset.key;
        const userFull = optDiv.dataset.full;

        // 鎖定（點一次後其他都禁用）
        options.forEach((o) => o.classList.add("disabled"));

        // 比對
        const isCorrect = userKey === correct || userFull === correct;

        if (isCorrect) {
          optDiv.classList.add("is-correct");
        } else {
          optDiv.classList.add("is-wrong");
          // 標出正解
          const hit = options.find(
            (o) => o.dataset.key === correct || o.dataset.full === correct
          );
          if (hit) hit.classList.add("is-correct");
        }

        // 顯示詳解
        explain.style.display = "block";

        // 詳解與本題再補一次 code 上色
        ensurePreHasCode(li, "python");
        if (window.hljs && hljs.highlightElement) {
          li.querySelectorAll("pre code, code").forEach((b) => {
            if (!b.classList.contains("hljs")) hljs.highlightElement(b);
          });
        }
      });
    });

    li.appendChild(question);
    li.appendChild(optionsWrap);
    li.appendChild(explain);
    list.appendChild(li);
  });

  // 整個練習區再補 code + 上色
  ensurePreHasCode(practiceSec, "python");
  if (window.hljs && hljs.highlightElement) {
    practiceSec.querySelectorAll("pre code, code").forEach((b) => {
      if (!b.classList.contains("hljs")) hljs.highlightElement(b);
    });
  }
}
