// 渲染整個課程內容畫面
import { TABLE_LESSON_IDS } from "./constants.js";
import { escapeHtml } from "./helpers.js";
import { ensurePreHasCode } from "./dom.js";
import { makeExpItem } from "./expItem.js";
import { renderPractice } from "./practice.js";

export function renderLesson(lesson, lessonId) {
  const { Title, Intro, exp = {}, practice = [] } = lesson;
  const { cor_exp = [], mis_exp = [] } = exp;
  const el = document.querySelector(".textContent");

  el.innerHTML = `
    <h1 class="title">${escapeHtml(Title || "")}</h1>
    <p class="intro">${escapeHtml(Intro || "")}</p>

    <div class="expContenter">
      <div class="corExp">
        <span><b># 範例:</b></span>
        <ul class="cor-list"></ul>
      </div>

      <div class="misExp">
        <span><b># 錯誤範例:</b></span>
        <ul class="mis-list"></ul>
      </div>

      <section class="practice" aria-label="練習題">
        <p><b># 練習題:</b></p>
        <ol class="practice-list"></ol>
      </section>
    </div>
  `;

  const isTableLesson = TABLE_LESSON_IDS.has(String(lessonId ?? lesson.ID ?? lesson.id));

  const corList = el.querySelector(".cor-list");
  cor_exp.forEach(code => corList.appendChild(makeExpItem(code, "python", isTableLesson)));

  const misList = el.querySelector(".mis-list");
  mis_exp.forEach(code => misList.appendChild(makeExpItem(code, "python", isTableLesson)));

  // 先讓練習題渲染
  renderPractice({ practice });

  // ✅ 最後只針對 <pre><code> 上色（不影響表格）
  const root = document.querySelector(".textContent");
  ensurePreHasCode(root, "python");

  requestAnimationFrame(() => {
    if (window.hljs && hljs.highlightElement) {
      root.querySelectorAll("pre code").forEach(b => {
        if (!b.classList.contains("hljs")) hljs.highlightElement(b);
      });
    } else {
      console.warn("highlight.js 尚未載入");
    }
  });

  // 再補一輪：專門針對練習題區域
  requestAnimationFrame(() => {
    const practiceSec = document.querySelector(".practice");
    if (practiceSec && window.hljs && hljs.highlightElement) {
      ensurePreHasCode(practiceSec, "python");
      practiceSec.querySelectorAll("pre code").forEach(b => {
        if (!b.classList.contains("hljs")) hljs.highlightElement(b);
      });
    }
  });
}