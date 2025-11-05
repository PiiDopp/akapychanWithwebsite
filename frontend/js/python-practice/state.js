// 內部狀態管理：isLoading、目前題組/題號、最近載入的 data、主選單原始 HTML 暫存。
import { STORAGE } from './constants.js';

let isLoading = false;
let currentDataId = null;
let currentPracticeIdx = 0;
let lastSetId = null;
let lastData = null;
// 主選單原始 HTML 暫存（對齊舊實作 menuEl.__origHTML）
let mainMenuOrigHTML = '';

export function getLoading() { return isLoading; }
export function setLoading(v) { isLoading = !!v; }

export function getCurrent() {
  return { dataId: currentDataId, practiceIdx: currentPracticeIdx };
}
export function setCurrent(setId, idx) {
  currentDataId = setId;
  currentPracticeIdx = idx;
}

export function setLastLoaded(setId, data) {
  lastSetId = setId;
  lastData = data;
}
export function getLastLoaded() {
  return { setId: lastSetId, data: lastData };
}

export function setMainMenuOrigHTML(html) { mainMenuOrigHTML = html || ''; }
export function getMainMenuOrigHTML() { return mainMenuOrigHTML; }

export function getSetId() {
  const sp = new URLSearchParams(window.location.search);
  return sp.get('set');
}

export function saveCur(setId, idx) {
  try { sessionStorage.setItem(`${STORAGE.curPrefix}${setId}`, String(idx)); } catch {}
}
export function loadCur(setId) {
  try {
    const v = sessionStorage.getItem(`${STORAGE.curPrefix}${setId}`);
    const n = Number(v);
    return Number.isFinite(n) ? n : 0;
  } catch { return 0; }
}