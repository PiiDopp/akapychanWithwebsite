// 呼叫後端 /api/ai/chat
import { API_BASE } from "./constants.js";

export async function chatToBackend(payload, signal) {
  const url = `${API_BASE}/api/ai/chat`.replace(/([^:])\/\/+/g, "$1/");
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
    signal
  });
  if (!res.ok) throw new Error(await res.text().catch(() => res.statusText));
  const data = await res.json();
  return (
    data?.text ??
    data?.message ??
    data?.output ??
    data?.response ??
    data?.choices?.[0]?.message?.content ??
    ""
  );
}