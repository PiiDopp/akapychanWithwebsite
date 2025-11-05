// 判題按鈕
import { SELECTORS, PATHS, UI } from '../constants.js';
import { getSetId, loadCur } from '../state.js';

// 在 editor 準備好後綁定執行按鈕
export function setupRunButton() {
  const bind = () => {
    const btn = document.querySelector(SELECTORS.runBtn);
    if (!btn) return;
    // 先移除舊的，避免重複綁定
    btn.removeEventListener('click', handleRun);
    btn.addEventListener('click', handleRun);
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', bind, { once: true });
  } else {
    bind();
  }

  // 由 editor 模組在建立完成後 dispatch：document.dispatchEvent(new CustomEvent('editor:ready'))
  document.addEventListener('editor:ready', bind);
}

export async function handleRun(e) {
  e.preventDefault();
  e.stopPropagation();

  const runBtn = e.currentTarget;
  const outputEl = document.querySelector(SELECTORS.output);
  const code = window.editor?.getValue?.() ?? '';

  const dataId =
    window.currentDataId ||
    (typeof getSetId === 'function' ? getSetId() : null);
  const practiceIdx =
    window.currentPracticeIdx ??
    (typeof loadCur === 'function' && dataId ? loadCur(dataId) : 0);

  if (!dataId) {
    if (outputEl) outputEl.textContent = '請先選擇題目';
    return;
  }

  const isLeet = /^leetcode\d+$/i.test(String(dataId));

  let inferredPath = null;
  try {
    const activeLi = document.querySelector(`.M-Unit[data-id="${CSS.escape(String(dataId))}"]`);
    const dsPath = activeLi?.dataset?.path;
    if (dsPath) inferredPath = dsPath;
  } catch {}
  if (!inferredPath) {
    inferredPath = isLeet
      ? `${PATHS.leetRoot}/${String(dataId)}.json`
      : `${PATHS.dataRoot}/${encodeURIComponent(String(dataId))}.json`;
  }

  let tick;
  let t0 = Date.now();
  const setStatus = (s) => outputEl && (outputEl.textContent = s);
  const setRunningUI = (flag) => { if (runBtn) runBtn.disabled = !!flag; };

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), UI.judgeTimeoutMs);

  try {
    setRunningUI(true);
    setStatus('判題中…（0s）');
    tick = setInterval(() => {
      const sec = Math.floor((Date.now() - t0) / 1000);
      setStatus(`判題中…（${sec}s）`);
    }, 500);

    const body = {
      data_id: String(dataId),
      practice_idx: Number(practiceIdx),
      code,
      data_path: inferredPath,
      force_mode: 'stdin',
      data_source: isLeet ? 'leetcode' : 'builtin',
    };

    const res = await fetch(PATHS.judge, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      signal: controller.signal,
    });

    const raw = await res.text();
    let data = null;
    try { data = raw ? JSON.parse(raw) : null; } catch {}

    if (!res.ok) {
      const msg = (data && (data.error || data.detail)) || raw || `HTTP ${res.status}`;
      setStatus(`[錯誤] ${String(msg).slice(0, 500)}`);
      return;
    }
    if (!data || typeof data !== 'object') {
      setStatus('[錯誤] 後端回傳非 JSON 或為空');
      console.error('Non-JSON response:', raw);
      return;
    }

    setStatus(
      data.ok && data.verdict === 'correct'
        ? '[成功] 所有測資通過 ✅'
        : data.suggestions || '錯誤，請再試一次'
    );

    if (outputEl) outputEl.scrollTop = outputEl.scrollHeight;
  } catch (err) {
    const msg = err?.name === 'AbortError'
      ? '請求逾時（>10s），請稍後再試。'
      : err?.message || String(err);
    setStatus(`[例外錯誤] ${msg}`);
  } finally {
    clearTimeout(timeout);
    if (tick) clearInterval(tick);
    setRunningUI(false);
  }
}