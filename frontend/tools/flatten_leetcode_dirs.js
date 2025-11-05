import { promises as fs } from "node:fs";
import path from "node:path";

const ROOT = path.resolve(".", "frontend", "data", "Leetcode");

async function flatten() {
  const moved = [];
  const errors = [];

  async function moveJsonFiles(dir) {
    const entries = await fs.readdir(dir, { withFileTypes: true });
    for (const entry of entries) {
      const fullPath = path.join(dir, entry.name);
      if (entry.isDirectory()) {
        await moveJsonFiles(fullPath);
      } else if (entry.isFile() && entry.name.endsWith(".json")) {
        const dest = path.join(ROOT, entry.name);
        try {
          await fs.rename(fullPath, dest);
          moved.push(dest);
        } catch (err) {
          errors.push({ src: fullPath, error: err.message });
        }
      }
    }
  }

  await moveJsonFiles(ROOT);

  console.log(`✅ 已移動 ${moved.length} 個 JSON 檔到 ${ROOT}`);
  if (errors.length) {
    console.warn("⚠️ 發生錯誤：");
    errors.forEach(e => console.warn(`- ${e.src}: ${e.error}`));
  }

  // 清空空資料夾
  async function removeEmptyDirs(dir) {
    const entries = await fs.readdir(dir, { withFileTypes: true });
    if (entries.length === 0) {
      await fs.rmdir(dir);
      return;
    }
    for (const e of entries) {
      if (e.isDirectory()) {
        await removeEmptyDirs(path.join(dir, e.name));
      }
    }
    const remaining = await fs.readdir(dir);
    if (remaining.length === 0 && dir !== ROOT) {
      await fs.rmdir(dir);
    }
  }

  await removeEmptyDirs(ROOT);
  console.log("🧹 清除空資料夾完成。");
}

flatten().catch(err => console.error("❌ 發生錯誤：", err));
