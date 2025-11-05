// 左側欄收合按鈕
import { SELECTORS } from './constants.js';

export function installSidebarToggle() {
  const toggleBtn = document.querySelector(SELECTORS.leftsideBtn);
  toggleBtn?.addEventListener('click', () => {
    document.body.classList.toggle('sidebar-collapsed');
  });
}