// 共用常數：選擇器、API/路徑、Storage key 前綴、逾時秒數、Monaco CDN 版本等。
export const SELECTORS = {
  mainMenu: '#mainMenu',
  practiceArea: '#practiceArea',
  output: '#output',
  backBtn: '#backToMenuBtn',
  preview: '.preview',
  leftsideBtn: '.leftsideBtn',
  editorContainer: '#editorContainer',
  runBtn: '.runBtn',
};

export const STORAGE = {
  curPrefix: 'py.cur.', // sessionStorage key prefix
};

export const PATHS = {
  dataRoot: '/data',
  leetRoot: '/data/Leetcode',
  leetIndex: '/data/leetcode_index.json',
  judge: '/api/judge',
  translate: '/api/translate',
};

export const UI = {
  judgeTimeoutMs: 10_000,
};

export const MONACO = {
  cdnVersion: '0.44.0',
  theme: 'hc-black',
  defaultLang: 'python',
  fontSize: 18,
};