// 工具列建立、顯示控制、與文字分析（完全版）
import { el } from "./dom-utils.js";
import { setChosenMode, setPendingMode } from "./state.js";

// 保持與舊版相容：第二個參數 chatbox 不用也不影響
export function mountToolbars(chatRoot, _chatbox, sendViaUI) {
  // 1) 只保留一個 <div class="toolbar"></div> 作為母容器
  const host = chatRoot.parentNode.querySelector(".toolbar");
  if (!host) {
    console.warn("[toolbars] 未找到主 toolbar 容器，跳過初始化");
    return { analyzeAssistantText() {} };
  }

  host.innerHTML = "";
  host.style.margin = "6px 0";

  // 2) 動態建立所有 toolbar 群組
  const mkGroup = (id, tagText, buttons, hidden = true) => {
    const group = el("div", "toolbar-group");
    group.id = id;
    if (hidden) group.style.display = "none";

    if (tagText) {
      const tag = el("span", "tag", tagText);
      group.appendChild(tag);
    }

    buttons.forEach((btn) => {
      const b = el("button", "btn", btn.text);
      if (btn.display) b.dataset.display = btn.display; // 使用者泡泡顯示
      if (btn.payload) b.dataset.payload = btn.payload; // 後端 payload
      group.appendChild(b);
    });

    host.appendChild(group);
    return group;
  };

  // === 你的自訂文字（可改） ===
  const modeButtons = mkGroup("modeButtons", "選擇模式：", [
    {
      text: "模式 1｜互動開發",
      display: "進入 模式 1｜互動開發",
      payload: "1",
    },
    {
      text: "模式 2｜程式驗證",
      display: "進入 模式 2｜程式驗證",
      payload: "2",
    },
    {
      text: "模式 3｜程式解釋",
      display: "進入 模式 3｜程式解釋",
      payload: "3",
    },
  ]);

  const loopButtons = mkGroup("loopButtons", "互動修改模式：", [
    { text: "驗證", display: "驗證程式碼", payload: "V" },
    { text: "解釋", display: "解釋程式碼", payload: "E" },
    { text: "回到主選單", display: "回到主選單", payload: "q" },
  ]);

  const vc_confirmButtons = mkGroup("vc_confirmButtons", "是否符合需求？", [
    { text: "是", display: "是", payload: "y" },
    { text: "重新生成", display: "重新生成", payload: "n" },
    { text: "新增補充說明", display: "新增補充說明", payload: "a" },
  ]);

  const verifyButtons = mkGroup("verifyButtons", "執行 main 測試？", [
    { text: "執行測試", display: "執行測試", payload: "M" },
    { text: "不驗證", display: "不驗證", payload: "N" },
  ]);

  const enterLoopButtons = mkGroup(
    "enterLoopButtons",
    "是否進入互動式修改模式？",
    [
      { text: "是", display: "是", payload: "y" },
      { text: "否", display: "否", payload: "n" },
    ]
  );

  const backToMenuBtn = mkGroup("backToMenuBtn", "", [
    { text: "回到主選單", display: "回到主選單", payload: "q" },
  ]);

  // 3) 綁定事件（所有按鈕統一委派）
  host.addEventListener("click", (e) => {
    const btn = e.target.closest("button");
    if (!btn) return;

    const display = btn.dataset.display || btn.textContent.trim();
    const payload = btn.dataset.payload;

    if (!payload) return; // 保險：沒有 payload 就不送

    // 若是選模式（1 / 2 / 3），同步設定狀態
    if (["1", "2", "3"].includes(payload)) {
      setPendingMode(payload);
      setChosenMode(payload);
      hideAll();
    }

    // 顯示漂亮文案，但送後端精簡 payload
    sendViaUI({ display, payload });
  });

  // 4) 顯示控制
  const show = (el, on) => (el.style.display = on ? "" : "none");
  const hideAll = () => {
    [
      modeButtons,
      loopButtons,
      vc_confirmButtons,
      verifyButtons,
      enterLoopButtons,
      backToMenuBtn,
    ].forEach((el) => show(el, false));
  };

  // 5) 文案分析邏輯（決定顯示哪組）
  function analyzeAssistantText(text) {
    const t = String(text || "");

    const needMode = /請選擇以下模式|選擇模式：/i.test(t);
    const inMode1Loop = /請選擇您的下一步操作：|互動修改模式/i.test(t);
    const backToMenu = /已返回主選單|回到主選單/i.test(t);
    const inMode1Need = /你選擇了模式\s*1|請描述你的功能需求/i.test(t);
    const inMode2 = /你選擇了模式\s*2|貼上要驗證的\s*Python/i.test(t);
    const inMode3 = /你選擇了模式\s*3|貼上要解釋的\s*Python/i.test(t);
    const vc_confirmPrompt = /是否符合需求？|虛擬碼/i.test(t);
    const verifyPrompt = /要執行程式（main 測試）嗎？/i.test(t);
    const enterLoopPrompt = /是否進入互動式修改模式？/i.test(t);

    hideAll();

    if (backToMenu) return show(modeButtons, true);
    if (verifyPrompt) return show(verifyButtons, true);
    if (enterLoopPrompt) return show(enterLoopButtons, true);
    if (vc_confirmPrompt) return show(vc_confirmButtons, true);
    if (inMode1Loop) return show(loopButtons, true);
    if (needMode) return show(modeButtons, true);
    if (inMode1Need || inMode2 || inMode3) return show(backToMenuBtn, true);

    // 預設顯示回主選單
    show(backToMenuBtn, true);
  }

  // 6) 初始顯示
  show(modeButtons, true);

  return { analyzeAssistantText };
}
