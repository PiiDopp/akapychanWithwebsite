import { installPopstateHandler, initOnDOMContentLoaded } from './router.js';
import { installClickDelegation } from './events.js';
import { installEditorAndRunner } from './editor.js';
import { installSidebarToggle } from './sidebar.js';
import { setupButtons } from './buttons/index.js';

// 與舊 API 相容（必要時讓其他腳本可直接呼叫）
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