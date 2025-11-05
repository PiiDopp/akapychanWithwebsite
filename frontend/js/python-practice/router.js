// 子選單載入與返回主選單 / URL 與瀏覽器行為
import { SELECTORS, PATHS } from './constants.js';
import { setBackBtnVisible, setPreviewVisible, setCurrentQuestion, setOutput } from './dom.js';
import { renderOneQuestion } from './render.js';
import {
  getSetId, loadCur, saveCur, getLoading, setLoading,
  setLastLoaded, getLastLoaded, getMainMenuOrigHTML, setMainMenuOrigHTML,
} from './state.js';
import { populateLeetListAuto } from './leetcode_data.js';

export async function loadSet(setId, pushUrl = false) {
  if (getLoading()) return;
  setLoading(true);

  const menuEl = document.querySelector(SELECTORS.mainMenu);
  const area = document.querySelector(SELECTORS.practiceArea);
  if (!menuEl) { setLoading(false); return; }

  try {
    if (pushUrl) {
      const url = new URL(window.location.href);
      url.searchParams.set('set', setId);
      history.pushState({ set: setId }, '', url);
    }

    setOutput('載入題組中…');

    const resp = await fetch(`../data/${encodeURIComponent(setId)}.json`, { cache: 'no-store' });
    if (!resp.ok) throw new Error(`題組載入失敗（HTTP ${resp.status}）`);
    const data = await resp.json();

    if (!Array.isArray(data?.coding_practice) || data.coding_practice.length === 0) {
      throw new Error('題組內容為空或格式不正確');
    }

    if (typeof menuEl.__origHTML !== 'string') {
      menuEl.__origHTML = menuEl.innerHTML;
      setMainMenuOrigHTML(menuEl.__origHTML);
    }
    menuEl.innerHTML = '';
    data.coding_practice.forEach((q, i) => {
      const li = document.createElement('li');
      li.className = 'M-Unit';
      li.dataset.id = setId;
      li.dataset.exIdx = String(i);
      li.textContent = q?.title || `題目 ${i + 1}`;
      menuEl.appendChild(li);
    });

    const cur = loadCur(setId);
    await renderOneQuestion(document, data, cur, setId);

    const area2 = document.querySelector(SELECTORS.practiceArea);
    if (area2) area2.style.display = 'block';
    setBackBtnVisible(true);
    setPreviewVisible(true);

    setOutput('');

    setLastLoaded(setId, data);
  } catch (err) {
    setOutput(`載入失敗：${err.message}`);
  } finally {
    setLoading(false);
  }
}

export function backToMainMenu(evt) {
  const menuEl = document.querySelector(SELECTORS.mainMenu);
  const area = document.querySelector(SELECTORS.practiceArea);

  if (menuEl) {
    const orig = typeof menuEl.__origHTML === 'string' ? menuEl.__origHTML : getMainMenuOrigHTML();
    if (orig) {
      menuEl.innerHTML = orig;
      populateLeetListAuto();
    }
  }
  if (area) {
    area.style.display = 'block';
    const t = area.querySelector('.textContent .title');
    const d = area.querySelector('.textContent .description');
    const e = area.querySelector('.textContent .expContent');
    if (t) t.textContent = '請先選擇題目';
    if (d) d.textContent = '';
    if (e) e.innerHTML = '';

    area.classList.remove('fade-in');
    requestAnimationFrame(() => area.classList.add('fade-in'));
  }
  setOutput('');
  setBackBtnVisible(false);
  setPreviewVisible(false);

  const url = new URL(window.location.href);
  url.searchParams.delete('set');
  history.pushState({}, '', url);

  if (evt?.preventDefault) evt.preventDefault();
}

export function installPopstateHandler() {
  window.addEventListener('popstate', () => {
    const set = getSetId();
    const area = document.querySelector(SELECTORS.practiceArea);
    if (set) {
      loadSet(set, false);
      if (area) area.style.display = 'block';
      setBackBtnVisible(true);
      setPreviewVisible(true);
    } else {
      backToMainMenu();
    }
  });
}

export function initOnDOMContentLoaded() {
  document.addEventListener('DOMContentLoaded', () => {
    const menuEl = document.querySelector(SELECTORS.mainMenu);
    const area = document.querySelector(SELECTORS.practiceArea);

    if (menuEl) {
      populateLeetListAuto();
      menuEl.__origHTML = menuEl.innerHTML;
      setMainMenuOrigHTML(menuEl.__origHTML);
    } else {
      console.warn('⚠️ 找不到 #mainMenu');
    }

    const initial = getSetId();
    if (initial) {
      loadSet(initial, false);
      if (area) area.style.display = 'block';
      setBackBtnVisible(true);
      setPreviewVisible(true);
    } else {
      if (area) {
        area.style.display = 'block';
        const t = area.querySelector('.textContent .title');
        const d = area.querySelector('.textContent .description');
        const e = area.querySelector('.textContent .expContent');
        if (t) t.textContent = '請先選擇題目';
        if (d) d.textContent = '';
        if (e) e.innerHTML = '';
        area.classList.add('fade-in');
      }
      setBackBtnVisible(false);
      setPreviewVisible(false);
      setOutput('');
    }
  });
}