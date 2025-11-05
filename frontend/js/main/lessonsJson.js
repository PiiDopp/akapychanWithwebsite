// 與伺服器溝通的資料層
import { LESSON_BASE } from "./constants.js";

export function fetchLessonById(id) {
  if (id == null) throw new Error("缺少 lesson id");
  const base = String(LESSON_BASE || "/data/lessons").replace(/\/+$/, "");
  const url = `${base}/${encodeURIComponent(id)}.json`;

  return fetch(url, { credentials: "same-origin" }).then(async (res) => {
    if (!res.ok) {
      const hint = await res.text().catch(() => "");
      throw new Error(`讀取失敗：${url} (${res.status})\n${hint.slice(0,200)}`);
    }
    const ct = res.headers.get("content-type") || "";
    if (!/application\/json/i.test(ct)) {
      const txt = await res.text().catch(() => "");
      throw new Error(`Content-Type 非 JSON（${ct}）。前 200 字：\n${txt.slice(0,200)}`);
    }
    return res.json();
  });
}