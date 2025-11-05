import express from "express";
import cors from "cors";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const app = express();
const PORT = process.env.PORT || 4000;
const PY_BACKEND = process.env.PY_BACKEND || "http://127.0.0.1:8000";

app.use(cors({ origin: true, credentials: true }));
app.use(express.json({ limit: "1mb" }));

const FRONTEND_DIR = path.join(__dirname, "../frontend");
app.use(express.static(path.join(FRONTEND_DIR, "html"))); // 讓 /A.html 能直接命中
app.use(express.static(FRONTEND_DIR));

// /data → 指到 frontend/data
app.use(
  "/data",
  express.static(path.join(FRONTEND_DIR, "data"), {
    setHeaders(res) {
      res.type("application/json; charset=utf-8");
      res.set("Cache-Control", "public, max-age=60");
    },
  })
);

app.post("/api/ai/chat", async (req, res) => {
  try {
    const upstream = await fetch(`${PY_BACKEND}/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(req.body), // 前端已送 messages，直接轉發
    });

    const text = await upstream.text().catch(() => "");
    let data = null;
    try {
      data = text ? JSON.parse(text) : null;
    } catch {}

    if (!upstream.ok) {
      const msg =
        data?.error || data?.detail || text || `HTTP ${upstream.status}`;
      return res
        .status(upstream.status)
        .json({ error: `Python 服務錯誤：${String(msg).slice(0, 200)}` });
    }
    if (!data || typeof data !== "object") {
      return res.status(502).json({ error: "上游回應非 JSON 或為空" });
    }
    return res.json(data);
  } catch (err) {
    console.error("[/api/ai/chat] proxy error:", err);
    return res.status(500).json({ error: String(err?.message || err) });
  }
});

app.post("/api/translate", async (req, res) => {
  try {
    const {
      text,
      sourceLang = "英文",
      targetLang = "繁體中文",
      temperature = 0.2,
    } = req.body || {};

    if (!text || typeof text !== "string" || !text.trim()) {
      return res.status(400).json({ error: "缺少 text 或 text 為空字串" });
    }

    // 呼叫 Python 的 /translate
    const upstream = await fetch(`${PY_BACKEND}/translate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, sourceLang, targetLang, temperature }),
    });

    const raw = await upstream.text().catch(() => "");
    let data = null;
    try { data = raw ? JSON.parse(raw) : null; } catch {}

    if (!upstream.ok) {
      const msg = (data?.error || data?.detail || raw || `HTTP ${upstream.status}`);
      return res.status(upstream.status).json({
        error: `Python 服務錯誤：${String(msg).slice(0, 200)}`
      });
    }

    if (!data || typeof data !== "object") {
      return res.status(502).json({ error: "上游回應非 JSON 或為空" });
    }

    const translation = data?.translation?.trim?.() || "";
    return res.json({ ok: true, translation });
  } catch (err) {
    console.error("[/api/translate] proxy error:", err);
    return res.status(500).json({ error: String(err?.message || err) });
  }
});


app.post("/api/judge", async (req, res) => {
  try {
    const { data_id, dataId, practice_idx, practiceIdx, code } = req.body || {};

    // 自動兼容駝峰命名
    const bodyForPython = {
      data_id: data_id ?? dataId ?? null,
      practice_idx: practice_idx ?? practiceIdx ?? null,
      code: code ?? "",
    };

    if (!bodyForPython.data_id) {
      return res
        .status(400)
        .json({ error: "缺少 data_id（前端未帶或命名錯）" });
    }
    if (bodyForPython.practice_idx == null) {
      return res.status(400).json({ error: "缺少 practice_idx" });
    }

    console.log("[/api/judge] forwarding →", bodyForPython);

    const upstream = await fetch(`${PY_BACKEND}/judge`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(bodyForPython),
    });

    const text = await upstream.text().catch(() => "");
    let data = null;
    try {
      data = text ? JSON.parse(text) : null;
    } catch {}

    if (!upstream.ok) {
      const msg =
        data?.error || data?.detail || text || `HTTP ${upstream.status}`;
      return res.status(upstream.status).json({
        error: `Python 服務錯誤：${String(msg).slice(0, 200)}`,
      });
    }

    if (!data || typeof data !== "object") {
      return res.status(502).json({ error: "上游回應非 JSON 或為空" });
    }

    return res.json(data);
  } catch (err) {
    console.error("[/api/judge] proxy error:", err);
    return res.status(500).json({ error: String(err?.message || err) });
  }
});

app.all("/api/judge", (req, res) => {
  if (req.method !== "POST") {
    return res
      .status(405)
      .json({ error: `Method ${req.method} not allowed. Use POST /api/judge` });
  }
  return res.status(404).json({ error: "Not found" });
});

app.post("/api/hint", async (req, res) => {
  try {
    const {
      problem_id, data_id,
      code, user_code,
      practice_idx, practiceIdx,
      data_path, dataPath,
      source, data_source,
      mode, force_mode,
    } = req.body || {};

    // 統一成 Python 端要的鍵名
    const bodyForPython = {
      problem_id: String(problem_id ?? data_id ?? ""),
      code: code ?? user_code ?? "",
      practice_idx: practice_idx ?? practiceIdx ?? undefined,
      data_path: data_path ?? dataPath ?? undefined,
      source: source ?? data_source ?? undefined,
      mode: mode ?? force_mode ?? undefined,
    };

    if (!bodyForPython.problem_id) {
      return res.status(400).json({ error: "缺少 problem_id" });
    }
    if (!bodyForPython.code) {
      return res.status(400).json({ error: "缺少 code（或 user_code）" });
    }

    const upstream = await fetch(`${PY_BACKEND}/hint`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(bodyForPython),
    });

    const text = await upstream.text().catch(() => "");
    let data = null;
    try { data = text ? JSON.parse(text) : null; } catch {}

    if (!upstream.ok) {
      const msg = data?.error || data?.detail || text || `HTTP ${upstream.status}`;
      return res.status(upstream.status).json({
        error: `Python 服務錯誤：${String(msg).slice(0, 200)}`
      });
    }
    if (!data || typeof data !== "object") {
      return res.status(502).json({ error: "上游回應非 JSON 或為空" });
    }
    return res.json(data);
  } catch (err) {
    console.error("[/api/hint] proxy error:", err);
    return res.status(500).json({ error: String(err?.message || err) });
  }
});

app.all("/api/hint", (req, res) => {
  if (req.method !== "POST") {
    return res.status(405).json({ error: `Method ${req.method} not allowed. Use POST /api/hint` });
  }
  return res.status(404).json({ error: "Not found" });
});

app.post("/api/answer", async (req, res) => {
  try {
    const { problem_id, data_id, practice_idx, practiceIdx } = req.body || {};

    const bodyForPython = {
      problem_id: String(problem_id ?? data_id ?? ""),
      practice_idx: practice_idx ?? practiceIdx ?? 0,
    };

    if (!bodyForPython.problem_id) {
      return res.status(400).json({ error: "缺少 problem_id（或 data_id）" });
    }

    const upstream = await fetch(`${PY_BACKEND}/answer`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(bodyForPython),
    });

    const text = await upstream.text().catch(() => "");
    let data = null;
    try { data = text ? JSON.parse(text) : null; } catch {}

    if (!upstream.ok) {
      const msg = data?.error || data?.detail || text || `HTTP ${upstream.status}`;
      return res.status(upstream.status).json({
        error: `Python 服務錯誤：${String(msg).slice(0, 200)}`,
      });
    }

    if (!data || typeof data !== "object") {
      return res.status(502).json({ error: "上游回應非 JSON 或為空" });
    }

    return res.json(data);
  } catch (err) {
    console.error("[/api/answer] proxy error:", err);
    return res.status(500).json({ error: String(err?.message || err) });
  }
});

app.all("/api/answer", (req, res) => {
  if (req.method !== "POST") {
    return res.status(405).json({ error: `Method ${req.method} not allowed. Use POST /api/answer` });
  }
  return res.status(404).json({ error: "Not found" });
});

// 根路徑回主頁（避免 * 兜回所有路徑導致 A 連結無法跳頁）
app.get("/", (_req, res) => {
  res.sendFile(path.join(FRONTEND_DIR, "html", "welcome.html"));
});

app.listen(PORT, () => {
  console.log(`✅ Frontend server ready: http://127.0.0.1:${PORT}`);
  console.log(`↔️  Proxying API to: ${PY_BACKEND}`);
});
