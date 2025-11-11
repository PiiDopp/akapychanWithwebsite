import { SELECTORS, PATHS } from "./constants.js";
import { renderOneQuestion } from "./render.js";
import { setBackBtnVisible, setPreviewVisible, setOutput } from "./dom.js";
import { saveCur } from "./state.js";

export function installRandomPicker() {
  // ---------- 快取 ----------
  const setCache = new Map(); // setId -> Promise<{ setId, url, data }>
  let leetSetsMemo = null; // 記住最近掃到的 [{ setId, url }]

  // ---------- 現抓 UI ----------
  function getUI() {
    const box = document.querySelector(".randomPicker");
    const selectCategory = box?.querySelector('select[name="data-id"]') || null;
    const selectDifficulty =
      box?.querySelector('select[name="difficult"]') || null;
    const submitBtn =
      box?.querySelector(
        'input[type="submit"], button[type="submit"], button.random-submit'
      ) || null;
    // 保險：避免 form submit 導致跳頁
    if (submitBtn) submitBtn.setAttribute("type", "button");
    return { box, selectCategory, selectDifficulty, submitBtn };
  }

  // ---------- 小工具 ----------
  function makeOption(value, label) {
    const opt = document.createElement("option");
    opt.value = value; // 保留你的大小寫（Easy/Medium/Hard/none）
    opt.textContent = label;
    return opt;
  }

  // 掃 DOM 抓題組；若這次有掃到就更新 memo
  function collectAllLeetSets() {
    const nodes = document.querySelectorAll('[data-id^="leetcode"]');
    const list = [];
    nodes.forEach((el) => {
      const setId = el.dataset?.id;
      if (!/^leetcode\d+$/i.test(setId)) return;
      const preferPath = el.dataset?.path;
      const url =
        preferPath || `${PATHS.leetRoot}/${encodeURIComponent(setId)}.json`;
      list.push({ setId, url });
    });
    if (list.length) leetSetsMemo = list;
    return list;
  }

  function loadSetJSON(setId, url) {
    if (!setCache.has(setId)) {
      const p = (async () => {
        const resp = await fetch(url, { cache: "no-store" });
        if (!resp.ok)
          throw new Error(`題組 ${setId} 載入失敗（HTTP ${resp.status}）`);
        const data = await resp.json();
        if (
          !Array.isArray(data?.coding_practice) ||
          data.coding_practice.length === 0
        ) {
          throw new Error(`題組 ${setId} 內容為空或格式不正確`);
        }
        return { setId, url, data };
      })();
      setCache.set(setId, p);
    }
    return setCache.get(setId);
  }

  async function loadAllSets() {
    // 先試著從 DOM 掃；掃不到就用上次 memo
    let sets = collectAllLeetSets();
    if (!sets.length && Array.isArray(leetSetsMemo) && leetSetsMemo.length) {
      sets = leetSetsMemo;
    }
    if (!sets.length) {
      // 不要 throw，避免把流程卡死；給清楚訊息
      throw new Error(
        '目前沒有題組清單（請回含 data-id="leetcodeX" 的主頁初始化一次）。'
      );
    }
    return Promise.all(sets.map((s) => loadSetJSON(s.setId, s.url)));
  }

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
    return Array.from(diffs);
  }

  async function rebuildDifficultySelect(categoryId, selectEl) {
    if (!selectEl) return;
    const labelMap = {
      easy: "簡單(Easy)",
      medium: "中等(Medium)",
      hard: "困難(Hard)",
    };
    const order = ["easy", "medium", "hard"];
    const prevValueRaw = selectEl.value || "none";
    const prevValueLc = prevValueRaw.toLowerCase();

    const diffs = await getAvailableDiffsForUnit(categoryId).catch(() => []);
    selectEl.innerHTML = "";

    if (!diffs.length) {
      selectEl.append(
        makeOption("none", "隨機難度"),
        makeOption("Easy", labelMap.easy),
        makeOption("Medium", labelMap.medium),
        makeOption("Hard", labelMap.hard)
      );
      selectEl.value = ["none", "easy", "medium", "hard"].includes(prevValueLc)
        ? prevValueRaw
        : "none";
      return;
    }

    const present = order.filter((d) => diffs.includes(d));
    present.forEach((d) =>
      selectEl.append(makeOption(d[0].toUpperCase() + d.slice(1), labelMap[d]))
    );

    if (present.length >= 2) {
      selectEl.prepend(makeOption("none", "隨機難度"));
      if (present.includes(prevValueLc)) {
        selectEl.value = prevValueLc[0].toUpperCase() + prevValueLc.slice(1);
      } else if (prevValueLc === "none") {
        selectEl.value = "none";
      } else {
        const pick = present[0];
        selectEl.value = pick[0].toUpperCase() + pick.slice(1);
      }
    } else {
      const only = present[0];
      selectEl.value = only[0].toUpperCase() + only.slice(1);
    }
  }

  function makeFilter(categoryId, difficulty) {
    const wantHundreds = Number(categoryId);
    const diffLc = String(difficulty).toLowerCase();
    const any = diffLc === "none";
    return (q) => {
      const tagNum = Math.floor(Number(q.tag) / 100) * 100;
      if (tagNum !== wantHundreds) return false;
      if (any) return true;
      return String(q.difficult).toLowerCase() === diffLc;
    };
  }

  // ---------- 核心流程：每次點擊都現抓元素 ----------
  async function pickAndRender() {
    const { box, selectCategory, selectDifficulty } = getUI();
    if (!box || !selectCategory || !selectDifficulty) {
      setOutput("找不到隨機出題區塊或選單元素");
      return;
    }

    const categoryId = selectCategory.value;
    const difficulty = selectDifficulty.value;

    setOutput("隨機出題中…");

    // 重建難度下拉（UI同步）；失敗不阻擋
    await rebuildDifficultySelect(categoryId, selectDifficulty).catch(() => {});
    const finalDifficulty = selectDifficulty.value;

    let loaded;
    try {
      loaded = await loadAllSets();
    } catch (err) {
      setOutput(err?.message || "目前沒有題組清單。");
      return;
    }

    const filterFn = makeFilter(categoryId, finalDifficulty);
    const pool = [];
    for (const { setId, data } of loaded) {
      (data.coding_practice || []).forEach((q, idx) => {
        if (filterFn(q)) pool.push({ setId, data, idx, q });
      });
    }

    // 放寬：finalDifficulty = none 時，改抓該單元任意難度
    if (!pool.length && String(finalDifficulty).toLowerCase() === "none") {
      for (const { setId, data } of loaded) {
        (data.coding_practice || []).forEach((q, idx) => {
          const tagNum = Math.floor(Number(q.tag) / 100) * 100;
          if (tagNum === Number(categoryId)) pool.push({ setId, data, idx, q });
        });
      }
    }

    if (!pool.length) {
      setOutput("找不到符合「單元／難度」的題目。請換個條件再試試！");
      return;
    }

    const picked = pool[Math.floor(Math.random() * pool.length)];
    await renderOneQuestion(document, picked.data, picked.idx, picked.setId);
    saveCur(picked.setId, picked.idx);

    const area = document.querySelector(SELECTORS.practiceArea);
    if (area) area.style.display = "block";
    setBackBtnVisible(false);
    setPreviewVisible(true);
    setOutput("");
  }

  // ---------- 單次初始化（若目前就有 .random，先重建難度） ----------
  {
    const { selectCategory, selectDifficulty } = getUI();
    if (selectCategory && selectDifficulty) {
      rebuildDifficultySelect(selectCategory.value, selectDifficulty).catch(
        () => {}
      );
    }
  }

  // ---------- 事件委派 ----------
  if (!window.__randomDelegatedOnce__) {
    document.addEventListener("click", async (e) => {
      const btn =
        e.target &&
        e.target.closest?.(
          ".random .random-submit, .randomPicker .random-submit"
        );
      if (!btn) return;
      e.preventDefault?.();
      await pickAndRender();
    });

    document.addEventListener("change", (e) => {
      const isUnitSelect =
        e.target && e.target.matches?.('select[name="data-id"]');
      if (!isUnitSelect) return;
      if (!e.target.closest(".random, .randomPicker")) return;

      const { selectDifficulty } = getUI();
      if (!selectDifficulty) return;
      rebuildDifficultySelect(e.target.value, selectDifficulty).catch((err) =>
        setOutput(`更新難度選單失敗：${err.message}`)
      );
    });

    window.__randomDelegatedOnce__ = true;
  }
}
