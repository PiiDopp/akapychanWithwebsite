import { PATHS } from '../constants.js';

export async function handleHint(e) {
  e.preventDefault();
  try {
    const resp = await fetch(PATHS.chat, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action: 'hint' }),
    });
    const data = await resp.json().catch(() => ({}));
    show(data.reply ?? '（沒有提示）');
  } catch (err) {
    show(`[錯誤] ${err.message || err}`);
  }
}

function show(text) {
  const el = document.querySelector('#output');
  if (el) el.textContent = text;
}