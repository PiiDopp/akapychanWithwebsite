// DOM/畫面層
import { SELECTORS } from './constants.js';
import { setCurrent } from './state.js';

export function q(sel, root = document) {
  return root.querySelector(sel);
}

export function setOutput(text) {
  const el = q(SELECTORS.output);
  if (el) el.textContent = text || '';
}

export function setPreviewVisible(flag) {
  const preview = document.querySelector(SELECTORS.preview);
  if (!preview) return;
  preview.classList.toggle('is-hidden', !flag);
}

export function setBackBtnVisible(flag) {
  const back = q(SELECTORS.backBtn);
  if (!back) return;
  back.style.display = flag ? 'inline-block' : 'none';
}

export function setCurrentQuestion(setId, idx) {
  setCurrent(setId, idx);
  window.currentDataId = setId;
  window.currentPracticeIdx = idx;
  document.dispatchEvent(new CustomEvent('py:question-changed', {
    detail: { dataId: setId, practiceIdx: idx },
  }));
}

export function ensureTitleRow(rootEl) {
  // rootEl: .textContent
  let row = rootEl.querySelector('.titleRow');
  const title = rootEl.querySelector('.title');
  if (!row) {
    row = document.createElement('div');
    row.className = 'titleRow';
    if (title) {
      title.parentNode.insertBefore(row, title);
      row.appendChild(title);
    } else {
      rootEl.insertBefore(row, rootEl.firstChild);
    }
    Object.assign(row.style, {
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between',
      gap: '12px',
      marginBottom: '6px',
    });
    if (title) title.style.margin = '8px 0';
  }
  return row;
}