// 全域狀態（messages、chatId、旗標）
export const messages = (window.messages ||= []);
export const pushMsg = (window.pushMsg ||= function (role, content) {
  messages.push({ role, content });
  if (messages.length > 30) messages.shift();
});
export let currentChatId = (window.currentChatId ||= Date.now());

// 互動模式旗標
export let chosenMode = (window.chosenMode ??= null);
export function setChosenMode(v) { window.chosenMode = chosenMode = v; }

let _pendingMode = null;
export function setPendingMode(v){ _pendingMode = v; }
export function consumePendingMode() { const v=_pendingMode; _pendingMode=null; return v; }