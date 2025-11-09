import { installPopstateHandler, initOnDOMContentLoaded } from './router.js';
import { installClickDelegation } from './events.js';
import { installEditorAndRunner } from './editor.js';
import { installSidebarToggle } from './sidebar.js';
import { setupButtons } from './buttons/index.js';
import { installRandomPicker } from './random.js';
import { getSetId, loadCur } from './state.js';
window.getSetId = getSetId;
window.loadCur = loadCur;

// 安裝各模組
installPopstateHandler();
initOnDOMContentLoaded();
installClickDelegation();
installEditorAndRunner();
installSidebarToggle();
setupButtons();

document.addEventListener('DOMContentLoaded', () => {
  installRandomPicker();
});

document.addEventListener('click', (e) => {
  // 開啟 chatbot 的按鈕
  const openBtn = e.target.closest('.openChat');
  const hideBtn = e.target.closest('.hiddenBtn');

  // 取得目標元素
  const chatbot = document.querySelector('.chat-editor .chatbot');
  const editor = document.querySelector('.chat-editor .editor');
  if (!chatbot || !editor) return;

  // 如果點擊 .openChat
  if (openBtn) {
    chatbot.classList.add('open');
    editor.classList.add('shrink');
    return;
  }

  // 如果點擊 .hiddenBtn
  if (hideBtn) {
    chatbot.classList.remove('open');
    editor.classList.remove('shrink');
    return;
  }
});

const area = document.querySelector('.scroll-area');

function updateOverflowState() {
  area.classList.toggle('has-overflow', area.scrollHeight > area.clientHeight);
}

updateOverflowState();
window.addEventListener('resize', updateOverflowState);
area.addEventListener('scroll', updateOverflowState);