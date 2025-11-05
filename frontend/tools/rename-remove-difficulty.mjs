import { promises as fs } from "node:fs";
import path from "node:path";
import url from "node:url";

const __dirname = path.dirname(url.fileURLToPath(import.meta.url));
const LC_DIR = path.join(__dirname, "../data/Leetcode");

async function renameFiles() {
  const files = await fs.readdir(LC_DIR);
  for (const name of files) {
    // 比對例如 leetcode1(easy).json
    const match = name.match(/^(leetcode\d+)(\([^)]+\))?\.json$/i);
    if (match) {
      const newName = `${match[1]}.json`; // 移除括號那段
      if (newName !== name) {
        await fs.rename(path.join(LC_DIR, name), path.join(LC_DIR, newName));
        console.log(`✅ ${name} → ${newName}`);
      }
    }
  }
}
renameFiles().catch(console.error);