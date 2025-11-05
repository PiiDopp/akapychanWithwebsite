// 點擊事件委派：主選單 → 進入子選單、單題 Leetcode 直開、同題組內題目切換、返回主選單。
import { SELECTORS, PATHS } from './constants.js';
import { loadSet, backToMainMenu } from './router.js';
import { loadCur, getLastLoaded, saveCur } from './state.js';
import { renderOneQuestion } from './render.js';
import { setBackBtnVisible, setPreviewVisible, setOutput } from './dom.js';

export function installClickDelegation() {
  document.addEventListener('click', (evt) => {
    const menuEl = document.querySelector(SELECTORS.mainMenu);
    if (!menuEl) return;

    // 返回主選單
    const backBtn = evt.target.closest(SELECTORS.backBtn);
    if (backBtn) {
      backToMainMenu(evt);
      return;
    }

    // 直接載入單題 JSON（有 data-path 就用）
    const directLeet = evt.target.closest('.M-Unit');
    if (
      directLeet &&
      directLeet.dataset?.id &&
      /^leetcode\d+$/i.test(directLeet.dataset.id) &&
      !directLeet.dataset.exIdx
    ) {
      evt.preventDefault?.();

      const setId = directLeet.dataset.id;
      const area = document.querySelector(SELECTORS.practiceArea);
      const preferPath = directLeet.dataset.path;

      (async () => {
        try {
          setOutput('載入題組中…');

          const urlToFetch = preferPath || `${PATHS.leetRoot}/${encodeURIComponent(setId)}.json`;
          const resp = await fetch(urlToFetch, { cache: 'no-store' });
          if (!resp.ok) throw new Error(`題組載入失敗（HTTP ${resp.status}）`);
          const data = await resp.json();

          if (!Array.isArray(data?.coding_practice) || data.coding_practice.length === 0) {
            throw new Error('題組內容為空或格式不正確');
          }

          // 記錄最近
          const cur = loadCur(setId);
          await renderOneQuestion(document, data, cur, setId);

          if (area) area.style.display = 'block';
          setBackBtnVisible(false);
          setPreviewVisible(true);
          setOutput('');
        } catch (err) {
          setOutput(`載入失敗：${err.message}`);
        }
      })();

      return;
    }

    // 進入子選單（點大項）
    const targetSet = evt.target.closest('[data-id]');
    if (targetSet && targetSet.dataset.id && !targetSet.dataset.exIdx) {
      if (typeof menuEl.__origHTML !== 'string') {
        menuEl.__origHTML = menuEl.innerHTML;
      }
      loadSet(targetSet.dataset.id, true);
      return;
    }

    // 切換同題組內的練習（點小題）
    const targetLi = evt.target.closest('.M-Unit');
    if (targetLi && targetLi.dataset.exIdx != null) {
      const i = Number(targetLi.dataset.exIdx);
      const curSet = targetLi.dataset.id || getLastLoaded().setId;
      const curData = getLastLoaded().data;
      if (!curSet || !curData) return;

      renderOneQuestion(document, curData, i, curSet);
      saveCur(curSet, i);
      return;
    }
  });
}