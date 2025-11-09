import { SELECTORS, PATHS } from "./constants.js";
import { renderOneQuestion } from "./render.js";
import { setBackBtnVisible, setPreviewVisible, setOutput } from "./dom.js";
import { saveCur } from "./state.js";

export function installRandomPicker() {
  // 僅在頁面包含 .random 區塊時啟用
  const randomBox = document.querySelector(".random");
  if (!randomBox) return;

  const selectCategory   = randomBox.querySelector('select[name="data-id"]');
  const selectDifficulty = randomBox.querySelector('select[name="difficult"]');
  const submitBtn        = randomBox.querySelector('input[type="submit"]');

  // ---- 快取（避免重複抓同一題組）----
  // key: setId (e.g., 'leetcode1') → Promise<{ setId, url, data }>
  const setCache = new Map();

  // ---- 工具：DOM option ----
  function makeOption(value, label) {
    const opt = document.createElement("option");
    opt.value = value;
    opt.textContent = label;
    return opt;
  }

  // ---- 收集頁面上所有可載入的 Leetcode 題組（支援 data-path 覆寫）----
  function collectAllLeetSets() {
    const nodes = document.querySelectorAll('[data-id^="leetcode"]');
    const list = [];
    nodes.forEach((el) => {
      const setId = el.dataset?.id;
      if (!/^leetcode\d+$/i.test(setId)) return;
      const preferPath = el.dataset?.path;
      const url = preferPath || `${PATHS.leetRoot}/${encodeURIComponent(setId)}.json`;
      list.push({ setId, url });
    });
    return list;
  }

  // ---- 載入單一題組 JSON ----
  function loadSetJSON(setId, url) {
    if (!setCache.has(setId)) {
      const p = (async () => {
        const resp = await fetch(url, { cache: "no-store" });
        if (!resp.ok) throw new Error(`題組 ${setId} 載入失敗（HTTP ${resp.status}）`);
        const data = await resp.json();
        if (!Array.isArray(data?.coding_practice) || data.coding_practice.length === 0) {
          throw new Error(`題組 ${setId} 內容為空或格式不正確`);
        }
        return { setId, url, data };
      })();
      setCache.set(setId, p);
    }
    return setCache.get(setId);
  }

  // ---- 載入所有題組 ----
  async function loadAllSets() {
    const sets = collectAllLeetSets();
    if (!sets.length) {
      throw new Error('找不到任何可載入的 Leetcode 題組（請確認主選單的 data-id="leetcodeX" 項目）');
    }
    return Promise.all(sets.map((s) => loadSetJSON(s.setId, s.url)));
  }

  // ---- 依單元(百位數)取得該單元實際擁有的難度（lowercase: easy/medium/hard）----
  async function getAvailableDiffsForUnit(categoryId) {
    const loaded = await loadAllSets();
    const diffs = new Set();
    const wantHundreds = Number(categoryId);

    for (const { data } of loaded) {
      (data.coding_practice || []).forEach((q) => {
        const tagNum = Math.floor(Number(q.tag) / 100) * 100;
        if (tagNum === wantHundreds && q.difficult) {
          diffs.add(String(q.difficult).toLowerCase());
        }
      });
    }
    return Array.from(diffs); // 例：['medium'] 或 ['medium','hard']
  }

  // ---- 重建難度下拉（規則：僅 1 種難度 → 只顯示該難度；≥2 種 → 顯示「隨機難度」+ 這些難度）----
  async function rebuildDifficultySelect(categoryId, selectEl) {
  const labelMap = {
    easy:   "簡單(Easy)",
    medium: "中等(Medium)",
    hard:   "困難(Hard)",
  };
  const order = ["easy", "medium", "hard"]; // 固定順序

  // 先記住目前使用者選的值（可能是 Easy/Medium/Hard/none）
  const prevValueRaw = selectEl.value || "none";
  const prevValueLc  = prevValueRaw.toLowerCase(); // 'easy' | 'medium' | 'hard' | 'none'

  // 取得該單元實際存在的難度（小寫陣列）
  const diffs = await getAvailableDiffsForUnit(categoryId);

  // 重建選單
  selectEl.innerHTML = "";

  if (diffs.length === 0) {
    // 這個單元沒有任何題 → 顯示預設四項，維持使用者原本值（若不存在就設 'none'）
    selectEl.append(
      makeOption("none", "隨機難度"),
      makeOption("Easy",   labelMap.easy),
      makeOption("Medium", labelMap.medium),
      makeOption("Hard",   labelMap.hard),
    );
    selectEl.value = ["none","easy","medium","hard"].includes(prevValueLc)
      ? prevValueRaw
      : "none";
    return;
  }

  // 依固定順序放入當前單元真的有的難度
  const present = order.filter(d => diffs.includes(d)); // e.g. ['medium'] 或 ['medium','hard']
  present.forEach(d => {
    selectEl.append(makeOption(d[0].toUpperCase()+d.slice(1), labelMap[d]));
  });

  if (present.length >= 2) {
    // 有 2+ 種難度 → 顯示「隨機難度」，但 **不主動選取 'none'**
    selectEl.prepend(makeOption("none", "隨機難度"));

    // 選擇策略：
    // 1) 若先前選的是某個難度且仍存在 → 保留
    // 2) 若先前選的是 'none' → 保留 'none'
    // 3) 其餘（先前選的難度不在 present）→ 選 present[0]（Easy→Medium→Hard）
    if (present.includes(prevValueLc)) {
      selectEl.value = prevValueLc[0].toUpperCase()+prevValueLc.slice(1);
    } else if (prevValueLc === "none") {
      selectEl.value = "none";
    } else {
      const pick = present[0];
      selectEl.value = pick[0].toUpperCase()+pick.slice(1);
    }
  } else {
    // 只有 1 種難度 → 不顯示「隨機」
    const only = present[0]; // 'easy' | 'medium' | 'hard'
    selectEl.value = only[0].toUpperCase()+only.slice(1);
  }
}

  // ---- 過濾器（依單元百位數 + 難度；difficulty === 'none' 代表不限難度）----
  function makeFilter(categoryId, difficulty) {
    const wantHundreds = Number(categoryId);
    const wantAnyDiff = difficulty === "none";
    const wantDiff = wantAnyDiff ? null : String(difficulty).toLowerCase();

    return (q) => {
      const tagNum = Math.floor(Number(q.tag) / 100) * 100;
      const okCat  = tagNum === wantHundreds;
      const okDiff = wantAnyDiff ? true : String(q.difficult).toLowerCase() === wantDiff;
      return okCat && okDiff;
    };
  }

  // ---- 抽題主流程 ----
  async function pickAndRender() {
    const categoryId = selectCategory?.value;   // "500" | "600" | ...
    const difficulty = selectDifficulty?.value; // "none" | "Easy" | "Medium" | "Hard"

    setOutput("隨機出題中…");

    // 先保險：依單元重建難度下拉，確保使用者看到與資料一致
    await rebuildDifficultySelect(categoryId, selectDifficulty);

    // 重新取 difficulty（避免剛剛重建時預設值有變）
    const finalDifficulty = selectDifficulty.value;

    // 載入所有題組後合併候選池
    const loaded = await loadAllSets();
    const filterFn = makeFilter(categoryId, finalDifficulty);

    const pool = [];
    for (const { setId, data } of loaded) {
      (data.coding_practice || []).forEach((q, idx) => {
        if (filterFn(q)) pool.push({ setId, data, idx, q });
      });
    }

    // 若「隨機難度」仍沒命中，保險再放寬到該單元所有難度
    let candidate = pool;
    if (!candidate.length && finalDifficulty === "none") {
      for (const { setId, data } of loaded) {
        (data.coding_practice || []).forEach((q, idx) => {
          const tagNum = Math.floor(Number(q.tag) / 100) * 100;
          if (tagNum === Number(categoryId)) candidate.push({ setId, data, idx, q });
        });
      }
    }

    // 若依舊沒有，丟出提示
    if (!candidate.length) {
      throw new Error("找不到符合「單元／難度」的題目。請換個條件再試試！");
    }

    // 隨機挑一題並渲染
    const picked = candidate[Math.floor(Math.random() * candidate.length)];
    await renderOneQuestion(document, picked.data, picked.idx, picked.setId);
    saveCur(picked.setId, picked.idx);

    const area = document.querySelector(SELECTORS.practiceArea);
    if (area) area.style.display = "block";
    setBackBtnVisible(false);
    setPreviewVisible(true);
    setOutput("");
  }

  // ---- 事件：出題 ----
  submitBtn?.addEventListener("click", async (e) => {
    e.preventDefault?.();
    try {
      await pickAndRender();
    } catch (err) {
      setOutput(`出題失敗：${err.message}`);
    }
  });

  // ---- 事件：切換單元 → 依單元重建難度下拉 ----
  selectCategory?.addEventListener("change", () => {
    rebuildDifficultySelect(selectCategory.value, selectDifficulty)
      .catch((err) => setOutput(`更新難度選單失敗：${err.message}`));
  });

  // ---- 初始：進頁時就依當前單元重建一次難度下拉 ----
  // 若你的專案已經在 main.js 裡有 DOMContentLoaded 時機，也可改成在那邊呼叫。
  if (selectCategory && selectDifficulty) {
    rebuildDifficultySelect(selectCategory.value, selectDifficulty)
      .catch(() => {/* 初載失敗不擋流程 */});
  }
}