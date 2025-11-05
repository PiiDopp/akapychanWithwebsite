// 翻譯按鈕
import { PATHS } from '../constants.js';
import { ensureTitleRow } from '../dom.js';

async function translateWithBackend(text) {
  const resp = await fetch(PATHS.translate, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text }),
  });
  if (!resp.ok) {
    const t = await resp.text().catch(() => '');
    throw new Error(`HTTP ${resp.status}：${t || '翻譯失敗'}`);
  }
  const data = await resp.json();
  if (!data.ok) throw new Error(data.error || '翻譯失敗');
  return (data.translation || '').trim();
}

function startBtnDots(btn, base = '翻譯中') {
  const frames = ['', '.', '..', '...'];
  let i = 0;
  const id = setInterval(() => {
    i = (i + 1) % frames.length;
    btn.textContent = base + frames[i];
  }, 300);
  return () => clearInterval(id);
}

// === 若你想要求有 active question 才顯示，改為 true ===
const REQUIRE_ACTIVE_QUESTION = false;

function hasActiveQuestion() {
  const dataId =
    window.currentDataId ||
    (typeof window.getSetId === 'function' ? window.getSetId() : null);
  return !!dataId;
}

function insertTranslateButton(rootEl) {
  if (!rootEl) return;

  // 清除舊按鈕（避免重複）
  rootEl.querySelectorAll('.translateToggleBtn').forEach((b) => b.remove());

  const desc = rootEl.querySelector('.description');
  const titleRow = ensureTitleRow(rootEl);
  if (!desc || !titleRow) return;

  const btn = document.createElement('button');
  btn.className = 'translateToggleBtn';
  btn.type = 'button';
  btn.textContent = '翻譯描述';

  Object.assign(btn.style, {
    padding: '6px 12px',
    borderRadius: '6px',
    border: '1px solid var(--border, #e5e7eb)',
    background: 'var(--surface, transparent)',
    color: 'inherit',
    cursor: 'pointer',
    display: 'inline-flex',
    alignItems: 'center',
    gap: '6px',
    whiteSpace: 'nowrap',
  });

  titleRow.appendChild(btn);

  const st = (rootEl._translateState = {
    original: (desc.textContent || '').trim(),
    translated: null,
    showingTranslated: false,
  });

  const syncBtnVisibility = () => {
    const hasDesc = !!desc && !!desc.textContent && desc.textContent.trim().length > 0;
    const shouldShow = (!REQUIRE_ACTIVE_QUESTION || hasActiveQuestion()) && hasDesc;
    btn.style.display = shouldShow ? 'inline-flex' : 'none';
  };

  // 監聽描述變化，重置狀態
  if (rootEl._translateObserver) {
    rootEl._translateObserver.disconnect();
  }
  const contentObserver = new MutationObserver(() => {
    const cur = (desc.textContent || '').trim();
    if (cur !== st.original && cur !== (st.translated || '').trim()) {
      st.original = cur;
      st.translated = null;
      st.showingTranslated = false;
      btn.textContent = '翻譯描述';
    }
    syncBtnVisibility();
  });
  contentObserver.observe(desc, { childList: true, characterData: true, subtree: true });
  rootEl._translateObserver = contentObserver;

  // 點擊切換
  btn.addEventListener('click', async () => {
    if (!st.showingTranslated) {
      btn.disabled = true;
      const stop = startBtnDots(btn, '翻譯中');
      try {
        if (!st.translated) st.translated = await translateWithBackend(st.original);
        desc.textContent = st.translated || '（沒有翻譯結果）';
        st.showingTranslated = true;
        stop();
        btn.textContent = '顯示原文';
      } catch (e) {
        stop();
        alert('翻譯失敗：' + (e?.message || e));
        st.showingTranslated = false;
        btn.textContent = '翻譯描述';
      } finally {
        btn.disabled = false;
        syncBtnVisibility();
      }
      return;
    }
    // 切回原文
    desc.textContent = st.original;
    st.showingTranslated = false;
    btn.textContent = '翻譯描述';
    syncBtnVisibility();
  });

  // 初始顯示
  syncBtnVisibility();
}

// —— 一次性插入目前頁面上已存在的 .textContent
function ensureTranslateButtonsOnce(root = document) {
  root.querySelectorAll('.textContent').forEach((rootEl) => {
    if (!rootEl.querySelector('.translateToggleBtn')) {
      insertTranslateButton(rootEl);
    }
  });
}

let _installed = false;
let _pageObserver = null;

export function installTranslateModule() {
  if (_installed) return; // 避免重複初始化
  _installed = true;

  // 1) 初次嘗試插入
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => ensureTranslateButtonsOnce(), { once: true });
  } else {
    ensureTranslateButtonsOnce();
  }

  // 2) 監聽整個頁面，當 .textContent 動態加入時就插入
  _pageObserver = new MutationObserver((mList) => {
    for (const m of mList) {
      m.addedNodes.forEach((n) => {
        if (!(n instanceof Element)) return;
        if (n.matches?.('.textContent')) {
          ensureTranslateButtonsOnce(n.ownerDocument || document);
        } else {
          const hasBlocks = n.querySelector?.('.textContent');
          if (hasBlocks) ensureTranslateButtonsOnce(n);
        }
      });
    }
  });
  _pageObserver.observe(document.body, { childList: true, subtree: true });

  // 3) 題目切換：重建
  document.addEventListener('py:question-changed', () => {
    document.querySelectorAll('.textContent').forEach((rootEl) => {
      if (rootEl._translateObserver) {
        rootEl._translateObserver.disconnect();
        delete rootEl._translateObserver;
      }
      if (rootEl._translateState) delete rootEl._translateState;
      rootEl.querySelectorAll('.translateToggleBtn').forEach((b) => b.remove());
      insertTranslateButton(rootEl);
    });
  });
}
