import { LESSON_BASE, DEFAULT_LESSON_ID } from "./constants.js";
import { fetchLessonById } from "./lessonsJson.js";
import { renderLesson } from "./lessonView.js";
import { scrollToTop } from "./dom.js";

console.log("[main] 模組載入成功");

// ---- 側欄點擊（事件委派）----
const menu = document.getElementById("unitContenter");

if (menu) {
  menu.addEventListener("click", async (e) => {
    const li = e.target.closest(".M-Unit, .S-Unit");
    if (!li || !menu.contains(li)) return;
    if (!li.dataset.id || li.classList.contains("is-disabled")) return;

    menu.querySelectorAll(".active").forEach((n) => n.classList.remove("active"));
    li.classList.add("active");

    const id = li.dataset.id;
    try {
      const data = await fetchLessonById(id);
      renderLesson(data, id);
      scrollToTop();
      location.hash = "unit=" + encodeURIComponent(id);
    } catch (err) {
      console.error(err);
      const base = String(LESSON_BASE || "/data/lessons").replace(/\/+$/, "");
      document.querySelector(".textContent").innerHTML = `
        <h1 class="title">讀取失敗</h1>
        <p class="intro">
          無法載入 <code>${base + "/" + encodeURIComponent(id) + ".json"}</code><br>
          <small>${String(err.message || err)}</small>
        </p>
      `;
    }
  });
}

// ---- 首次載入：支援 #unit=ID ----
window.addEventListener("DOMContentLoaded", async () => {
  const m = location.hash.match(/unit=([^&]+)/);
  const id = m ? decodeURIComponent(m[1]) : null;

  if (id) {
    if (menu) {
      const node = menu.querySelector(`[data-id="${CSS.escape(id)}"]`);
      if (node) node.classList.add("active");
    }
    try {
      const data = await fetchLessonById(id);
      renderLesson(data, id);
      scrollToTop();
      return;
    } catch {}
  }

  if (menu) {
    const firstValid = Array.from(menu.querySelectorAll(".M-Unit, .S-Unit"))
      .find(el => el.dataset && el.dataset.id);
    if (firstValid) {
      firstValid.click();
      return;
    }
  }

  try {
    const data = await fetchLessonById(DEFAULT_LESSON_ID);
    renderLesson(data, DEFAULT_LESSON_ID);
    scrollToTop();
    location.hash = "unit=" + encodeURIComponent(DEFAULT_LESSON_ID);
  } catch (err) {
    console.error(err);
  }
});

// ---- 左側收合按鈕 ----
const toggleBtn = document.querySelector('.leftsideBtn');
toggleBtn?.addEventListener('click', () => {
  document.body.classList.toggle('sidebar-collapsed');
});
