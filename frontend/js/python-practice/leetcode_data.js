// 資料來源自動偵測 / 分組清單渲染
import { PATHS, SELECTORS } from './constants.js';
import { dedupeById, extractUnitFromPath, normDifficultyLabel, groupByUnitAndDifficulty } from './helpers.js';

export async function discoverLeetEntries() {
  // 1) leetcode_index.json
  try {
    const idxResp = await fetch(PATHS.leetIndex, { cache: 'no-store' });
    if (idxResp.ok) {
      const idx = await idxResp.json(); // simple 或 advanced
      const list = [];
      if (Array.isArray(idx)) {
        idx.forEach((it) => {
          if (typeof it === 'string') {
            const file = it.startsWith('/') || it.startsWith('http') ? it : `${PATHS.dataRoot}/${it}`;
            const id = (it.split('/').pop() || '').replace(/\.json$/i, '');
            if (/^leetcode\d+$/i.test(id)) list.push({ file, id, title: id });
          } else if (it && typeof it === 'object' && typeof it.file === 'string') {
            const file = it.file.match(/^https?:/) ? it.file : `${PATHS.dataRoot}/${it.file}`;
            const id = (it.id || it.file.split('/').pop() || '').replace(/\.json$/i, '');
            list.push({
              file,
              id,
              title: it.title || id,
              unit: it.unit,
              difficulty: it.difficulty,
            });
          }
        });
      }
      if (list.length) return dedupeById(list);
    }
  } catch {}

  // 2) 目錄索引（伺服器需允許 directory listing）
  const htmlLists = [];
  try {
    const dirResp = await fetch(`${PATHS.dataRoot}/`, { cache: 'no-store' });
    if (dirResp.ok) {
      const html = await dirResp.text();
      const doc = new DOMParser().parseFromString(html, 'text/html');
      const links = Array.from(doc.querySelectorAll('a[href$=".json"]'));
      links.forEach((a) => {
        const href = a.getAttribute('href');
        if (!href) return;
        const name = href.split('/').pop() || '';
        if (/^leetcode.*\.json$/i.test(name)) {
          const file = href.startsWith('http') ? href : `${PATHS.dataRoot}/${name}`;
          const id = name.replace(/\.json$/i, '');
          htmlLists.push({ file, id, title: id });
        }
      });
    }
  } catch {}
  if (htmlLists.length) return dedupeById(htmlLists);

  return [];
}

export async function populateLeetListAuto() {
  const menuEl = document.querySelector(SELECTORS.mainMenu);
  if (!menuEl) return;

  const leetList = document.getElementById('leetcode-list');
  if (!leetList) {
    console.warn('⚠️ 找不到 #leetcode-list，請確認 HTML 有這個元素');
    return;
  }

  leetList.querySelectorAll('li').forEach((li) => li.remove());

  try {
    const entries = await discoverLeetEntries();
    if (!entries.length) {
      console.warn('⚠️ 找不到任何 leetcode*.json；請確認已產生 /data/leetcode_index.json');
      return;
    }

    const normalized = entries.map((e) => ({
      id: e.id,
      title: e.title || e.id,
      file: e.file,
      unit: e.unit ?? extractUnitFromPath(e.file),
      difficulty: normDifficultyLabel(e.difficulty),
    }));

    const grouped = groupByUnitAndDifficulty(normalized);
    const unitKeys = Array.from(grouped.keys()).sort((a, b) => {
      if (!a) return 1;
      if (!b) return -1;
      return a - b;
    });

    const diffOrder = ['easy', 'medium', 'hard', 'unknown'];

    for (const unit of unitKeys) {
      const diffMap = grouped.get(unit);
      const totalCount = Array.from(diffMap.values()).reduce((n, arr) => n + arr.length, 0);

      const unitLi = document.createElement('li');
      unitLi.className = 'UnitBlock';

      const header = document.createElement('div');
      header.className = 'UnitHeader';
      header.textContent = unit ? `第${unit}單元（${totalCount}）` : `未分類（${totalCount}）`;
      header.tabIndex = 0;
      unitLi.appendChild(header);

      const inner = document.createElement('ul');
      inner.className = 'UnitInner';
      unitLi.appendChild(inner);

      header.addEventListener('click', () => inner.classList.toggle('is-collapsed'));
      header.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          inner.classList.toggle('is-collapsed');
        }
      });

      for (const d of diffOrder) {
        const items = (diffMap.get(d) || []).sort((a, b) =>
          a.id.localeCompare(b.id, undefined, { numeric: true })
        );
        if (!items.length) continue;

        if (d !== 'unknown') {
          const sub = document.createElement('li');
          sub.className = `UnitSubheader diff-${d}`;
          sub.textContent = d;
          inner.appendChild(sub);
        }

        for (const it of items) {
          const li = document.createElement('li');
          li.className = 'M-Unit';
          li.dataset.id = it.id;
          li.dataset.path = it.file;

          const match = it.id.match(/leetcode(\d+)/i);
          const num = match ? parseInt(match[1], 10) : null;

          li.textContent = num ? `${num}. ${it.title}` : it.title;
          inner.appendChild(li);
        }
      }

      leetList.appendChild(unitLi);
    }
  } catch (err) {
    console.warn('❌ 自動偵測 leetcode 檔案失敗：', err);
  }
}