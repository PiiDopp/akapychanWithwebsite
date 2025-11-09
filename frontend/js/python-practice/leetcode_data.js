import { PATHS, SELECTORS } from "./constants.js";
import {
  dedupeById,
  extractUnitFromPath,
  normDifficultyLabel,
  groupByUnitAndDifficulty,
} from "./helpers.js";

//
// ====== 這段是 discoverLeetEntries()，原本應該在 leetcode_discover.js ======
//
export async function discoverLeetEntries() {
  // 1) 嘗試讀取 /data/leetcode_index.json
  try {
    const idxResp = await fetch(PATHS.leetIndex, { cache: "no-store" });
    if (idxResp.ok) {
      const idx = await idxResp.json();
      const list = [];

      if (Array.isArray(idx)) {
        for (const it of idx) {
          if (typeof it === "string") {
            const file =
              it.startsWith("/") || it.startsWith("http")
                ? it
                : `${PATHS.dataRoot}/${it}`;
            const id = (it.split("/").pop() || "").replace(/\.json$/i, "");
            if (/^leetcode\d+$/i.test(id)) list.push({ file, id, title: id });
          } else if (
            it &&
            typeof it === "object" &&
            typeof it.file === "string"
          ) {
            const file = it.file.match(/^https?:/)
              ? it.file
              : `${PATHS.dataRoot}/${it.file}`;
            const id = (it.id || it.file.split("/").pop() || "").replace(
              /\.json$/i,
              ""
            );
            list.push({
              file,
              id,
              title: it.title || id,
              unit: it.unit,
              difficulty: it.difficulty,
            });
          }
        }
      }
      if (list.length) return dedupeById(list);
    }
  } catch (err) {
    console.warn("❌ 讀取 leetcode_index.json 失敗：", err);
  }

  // 2) 如果 index.json 沒有，就試著抓資料夾列表（伺服器必須允許 directory listing）
  const htmlLists = [];
  try {
    const dirResp = await fetch(`${PATHS.dataRoot}/`, { cache: "no-store" });
    if (dirResp.ok) {
      const html = await dirResp.text();
      const doc = new DOMParser().parseFromString(html, "text/html");
      const links = Array.from(doc.querySelectorAll('a[href$=".json"]'));
      for (const a of links) {
        const href = a.getAttribute("href");
        if (!href) continue;
        const name = href.split("/").pop() || "";
        if (/^leetcode.*\.json$/i.test(name)) {
          const file = href.startsWith("http")
            ? href
            : `${PATHS.dataRoot}/${name}`;
          const id = name.replace(/\.json$/i, "");
          htmlLists.push({ file, id, title: id });
        }
      }
    }
  } catch (err) {
    console.warn("❌ directory listing 失敗：", err);
  }

  if (htmlLists.length) return dedupeById(htmlLists);
  return [];
}

//
// ====== 這段是 populateLeetListAuto()，會呼叫上面的 discoverLeetEntries() ======
//
export async function populateLeetListAuto() {
  const menuEl = document.querySelector(SELECTORS.mainMenu);
  if (!menuEl) return;

  const leetList = document.getElementById("leetcode-list");
  if (!leetList) {
    console.warn("⚠️ 找不到 #leetcode-list，請確認 HTML 有這個元素");
    return;
  }

  leetList.querySelectorAll("li").forEach((li) => li.remove());

  try {
    const entries = await discoverLeetEntries();
    if (!entries.length) {
      console.warn(
        "⚠️ 找不到任何 leetcode*.json；請確認已產生 /data/leetcode_index.json"
      );
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
    const UNIT_NAMES = {
      5: "五、重複結構（迴圈）",
      6: "六、複合式資料型態",
      7: "七、函數",
      8: "八、模組與套件",
      9: "九、例外處理與檔案操作",
      10: "十、進階資料處理",
      11: "十一、物件導向程式設計（OOP）",
      12: "十二、應用實作與延伸：JSON / API / GUI",
    };
    const diffOrder = ["easy", "medium", "hard", "unknown"];
    const DIFF_LABELS = {
      easy: "簡單（Easy）",
      medium: "中等（Medium）",
      hard: "困難（Hard）",
      unknown: "未標示難度",
    };

    for (const unit of unitKeys) {
      const diffMap = grouped.get(unit);
      if (!diffMap) continue;

      const totalCount = Array.from(diffMap.values()).reduce(
        (n, arr) => n + arr.length,
        0
      );

      const unitLi = document.createElement("li");
      unitLi.className = "UnitBlock";

      const header = document.createElement("div");
      header.className = "UnitHeader";
      const name = UNIT_NAMES[unit] || `第${unit}單元`;
      header.textContent = `${name}`;
      header.tabIndex = 0;
      header.setAttribute("role", "button");
      header.setAttribute("aria-expanded", "true");
      unitLi.appendChild(header);

      const inner = document.createElement("ul");
      inner.className = "UnitInner";
      unitLi.appendChild(inner);

      const toggleUnit = () => {
        inner.classList.toggle("is-collapsed");
        const expanded = header.getAttribute("aria-expanded") === "true";
        header.setAttribute("aria-expanded", (!expanded).toString());
      };
      header.addEventListener("click", toggleUnit);
      header.addEventListener("keydown", (e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          toggleUnit();
        }
      });

      for (const d of diffOrder) {
        const items = (diffMap.get(d) || [])
          .slice()
          .sort((a, b) =>
            a.id.localeCompare(b.id, undefined, { numeric: true })
          );
        if (!items.length) continue;

        const groupLi = document.createElement("li");
        groupLi.className = "DiffGroup";

        const subHeader = document.createElement("div");
        subHeader.className = `UnitSubheader diff-${d}`;
        subHeader.textContent = DIFF_LABELS[d] || d;
        subHeader.tabIndex = 0;
        subHeader.setAttribute("role", "button");
        subHeader.setAttribute("aria-expanded", "false");

        const subUl = document.createElement("ul");
        subUl.className = "DiffInner is-collapsed";

        const toggleDiff = () => {
          subUl.classList.toggle("is-collapsed");
          const expanded = subHeader.getAttribute("aria-expanded") === "true";
          subHeader.setAttribute("aria-expanded", (!expanded).toString());
        };
        subHeader.addEventListener("click", toggleDiff);
        subHeader.addEventListener("keydown", (e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            toggleDiff();
          }
        });

        for (const it of items) {
          const li = document.createElement("li");
          li.className = "M-Unit";
          li.dataset.id = it.id;
          li.dataset.path = it.file;

          const match = it.id.match(/leetcode(\d+)/i);
          const num = match ? parseInt(match[1], 10) : null;
          li.textContent = num ? `${num}. ${it.title}` : it.title;
          subUl.appendChild(li);
        }

        groupLi.appendChild(subHeader);
        groupLi.appendChild(subUl);
        inner.appendChild(groupLi);
      }

      leetList.appendChild(unitLi);
    }
  } catch (err) {
    console.warn("❌ 自動偵測 leetcode 檔案失敗：", err);
  }
}
