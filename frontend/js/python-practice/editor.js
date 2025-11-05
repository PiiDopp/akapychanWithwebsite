// Monaco Editor 建立
import { MONACO, SELECTORS } from './constants.js';

export function installEditorAndRunner() {
  const monacoPaths = { vs: `https://cdn.jsdelivr.net/npm/monaco-editor@${MONACO.cdnVersion}/min/vs` };
  if (window.require?.config) window.require.config({ paths: monacoPaths });

  window.require(['vs/editor/editor.main'], function () {
    // 建立 Monaco Editor
    window.editor = monaco.editor.create(
      document.querySelector(SELECTORS.editorContainer),
      {
        value: '',
        language: MONACO.defaultLang,
        theme: MONACO.theme,
        automaticLayout: true,
        fontSize: MONACO.fontSize,
        minimap: { enabled: false },
        wordWrap: 'on',
      }
    );

    // 通知其他模組：編輯器已經建立好
    document.dispatchEvent(new CustomEvent('editor:ready'));
  });
}