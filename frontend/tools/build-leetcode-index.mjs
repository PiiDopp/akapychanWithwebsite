import { promises as fs } from "node:fs";
import path from "node:path";
import url from "node:url";

const __dirname = path.dirname(url.fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, "..");
const DATA_DIR = path.join(ROOT, "data");
const LC_DIR = path.join(DATA_DIR, "Leetcode");
const OUT_FILE = path.join(DATA_DIR, "leetcode_index.json");

// 輸出格式（"simple" | "advanced"）
const OUTPUT_MODE = process.env.MODE || "advanced";

// ---------- utils ----------
const parseIntSafe = (v) => {
  if (v === null || v === undefined) return null;
  const n = parseInt(String(v).trim(), 10);
  return Number.isFinite(n) ? n : null;
};

const normDifficulty = (v) => {
  if (!v) return "unknown";
  const s = String(v).trim().toLowerCase();
  return ["easy", "medium", "hard"].includes(s) ? s : "unknown";
};

const extractTitle = (json, absFilePath) => {
  if (typeof json?.title === "string" && json.title.trim())
    return json.title.trim();
  const t = json?.coding_practice?.[0]?.title;
  if (typeof t === "string" && t.trim()) return t.trim();
  return path.basename(absFilePath, ".json");
};

const extractTag = (json) => {
  const t1 = parseIntSafe(json?.tag);
  if (t1 !== null) return t1;
  const t2 = parseIntSafe(json?.coding_practice?.[0]?.tag);
  if (t2 !== null) return t2;
  return null;
};

const extractDifficulty = (json) => {
  const d1 = json?.difficult;
  if (d1) return normDifficulty(d1);
  const d2 = json?.coding_practice?.[0]?.difficult;
  if (d2) return normDifficulty(d2);
  return "unknown";
};

const unitFromTagDiv10 = (tag) => Math.floor(tag / 100);

// ---------- main ----------
async function main() {
  await fs.mkdir(LC_DIR, { recursive: true });

  // ✅ 不遞迴：只讀最外層 JSON
  const entries = await fs.readdir(LC_DIR, { withFileTypes: true });
  const filesAbs = entries
    .filter((e) => e.isFile() && /\.json$/i.test(e.name))
    .map((e) => path.join(LC_DIR, e.name));

  console.log(
    `📄 在 ${LC_DIR} 找到 ${filesAbs.length} 個 .json（不遞迴子資料夾）`
  );

  const items = [];

  for (const abs of filesAbs) {
    const name = path.basename(abs);
    const id = name.replace(/\.json$/i, "");

    // 讀檔取 title/tag/difficulty
    let json = null,
      title = id,
      tag = null,
      difficulty = "unknown";
    try {
      const raw = await fs.readFile(abs, "utf-8");
      json = JSON.parse(raw);
      title = extractTitle(json, abs);
      tag = extractTag(json);
      difficulty = extractDifficulty(json);
    } catch (e) {
      console.warn(`[略過] 解析失敗：${name} (${e.message})`);
      continue;
    }

    // ✅ 單元只由 tag 推（不看資料夾）
    const unit = tag != null ? unitFromTagDiv10(tag) : null;

    // ✅ 索引路徑固定為 /Leetcode/<檔名>（不含子資料夾）
    const fileField = path.join("Leetcode", name).replace(/\\/g, "/");
    items.push({ file: fileField, id, title, tag, unit, difficulty });
  }

  if (OUTPUT_MODE === "simple") {
    const arr = items
      .sort(
        (a, b) =>
          (a.unit ?? 0) - (b.unit ?? 0) ||
          (a.tag ?? 0) - (b.tag ?? 0) ||
          a.file.localeCompare(b.file, undefined, { numeric: true })
      )
      .map((x) => x.file);
    await fs.writeFile(OUT_FILE, JSON.stringify(arr, null, 2) + "\n", "utf-8");
  } else {
    const list = items.sort(
      (a, b) =>
        (a.unit ?? 0) - (b.unit ?? 0) ||
        a.file.localeCompare(b.file, undefined, { numeric: true })
    );
    await fs.writeFile(OUT_FILE, JSON.stringify(list, null, 2) + "\n", "utf-8");
  }

  console.log(
    `✅ 完成：索引輸出 ${path.relative(ROOT, OUT_FILE)} (${OUTPUT_MODE})`
  );
}

main().catch((err) => {
  console.error("❌ 生成失敗：", err);
  process.exit(1);
});
