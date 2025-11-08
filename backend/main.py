from __future__ import annotations

# ====== 標準庫 / 第三方 ======
import os, sys, re, io, json, textwrap, tempfile, subprocess, contextlib
from typing import Any, Dict, List, Optional, Tuple

from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware

# ====== 你既有的核心（互動開發 / 驗證 / 解釋 用）======
from core import (
    extract_code_block, generate_response,
    validate_main_function, validate_python_code,
    extract_json_block, parse_tests_from_text
)
from core.model_interface import (
    build_virtual_code_prompt, build_test_prompt, build_explain_prompt,
    build_stdin_code_prompt, build_fix_code_prompt, build_hint_prompt, build_specific_explain_prompt,
    interactive_chat_api, normalize_tests
)
from explain_user_code import explain_user_code
from explain_error import explain_code_error
from core.mutation_runner import MutationRunner
from core.test_utils import generate_tests

# ====== 判題核心（LeetCode / STDIN）======
from core.judge_core import (
    # 驗證器
    validate_stdin_code,
    validate_leetcode_code,

    # 測資轉換
    build_leetcode_tests_from_examples,

    # 推斷工具
    infer_method_name_from_code,
    infer_arg_names_from_examples,

    # 題目載入
    load_problem_cases,

    # 資料結構/比對
    BuildSpec, ListNode, TreeNode,
    list_to_listnode, listnode_to_list,
    list_to_btree, btree_to_list,
    deep_compare,

    # 小工具
    normalize, parse_expected, kv_pairs_from_input,
)

# ====== FastAPI 初始化 ======
app = FastAPI(title="AkaPyChan API", version="1.0.0")

ALLOWED_ORIGINS = ["http://127.0.0.1:4000", "http://localhost:4000"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/healthz")
def healthz():
    return {"ok": True}

# ====== 內部會話狀態 ======
SESSIONS: Dict[str, Dict[str, Any]] = {}

def run_model(prompt: str) -> str:
    resp = generate_response(prompt)
    return resp or "[模型沒有回覆內容]"

def _mode1_make_need_text(ctx: Dict[str, str]) -> str:
    parts = []
    if ctx.get("need"):
        parts.append(f"需求：{ctx['need']}")
    if ctx.get("revise"):
        parts.append(f"額外修改建議：{ctx['revise']}")
    return "\n".join(parts).strip()

def _mode1_generate_virtual_code(ctx: Dict[str, Any]) -> str:
    need_text = _mode1_make_need_text(ctx)
    prompt = build_virtual_code_prompt(need_text or (ctx.get("need") or ""))
    return run_model(prompt)

def run_mode_3(user_code: str) -> str:
    user_code = (user_code or "").strip()
    if not user_code:
        return "請貼上要解釋的 Python 程式碼。"
    return explain_user_code(user_code)

# [新增] 輔助函數：標準化 stdin 輸入，處理列表形式的測資
def _normalize_stdin(val: Any) -> str:
    if val is None:
        return ""
    if isinstance(val, list):
        # 如果是列表，將其元素用換行符連接，確保傳入的是多行純文本
        return "\n".join(str(v) for v in val)
    return str(val)

# ====== 聊天入口（給前端）======
@app.post("/chat")
async def chat(request: Request):
    data = await request.json()
    chat_id = str(data.get("chat_id", "default"))
    messages: List[Dict[str, str]] = data.get("messages", [])
    last_user = next((m.get("content", "") for m in reversed(messages) if m.get("role") == "user"), "").strip()

    m = re.match(r"^進入\s*模式\s*([123])", last_user)
    if m:
        last_user = m.group(1)

    session = SESSIONS.setdefault(chat_id, {"mode": None, "awaiting": False, "step": None, "ctx": {}})
    mode = session.get("mode")

    MENU_TEXT = (
        "已返回主選單。\n\n請選擇模式：\n"
        "模式 1｜互動開發（貼需求 → 產生程式碼 → 可使用 驗證 / 解釋 / 修改）\n"
        "模式 2｜程式驗證（貼程式碼 → 貼需求 → AI 自動生成測資並驗證）\n"
        "模式 3｜程式解釋（貼上要解釋的 Python 程式碼）\n\n"
        "**點「輸入框上方的按鈕」即可選擇模式。**或直接輸入文字開始一般聊天。"
    )

    if last_user.lower() == "q":
        session.update({"mode": None, "awaiting": False, "step": None, "ctx": {}})
        return {"text": MENU_TEXT}

    if not mode:
        if last_user in {"1", "2", "3"}:
            session["mode"] = last_user
            session["awaiting"] = True
            session["step"] = None
            session["ctx"] = {}
            if last_user == "1":
                session["step"] = "need"
                return {"text": "**模式 1｜互動開發**\n\n請描述你的功能需求（一句或一段話即可）。"}
            if last_user == "2":
                session["step"] = "code"
                return {"text": "**模式 2｜程式驗證**\n\n請貼上要驗證的 Python 程式碼："}
            if last_user == "3":
                return {"text": "**模式 3｜程式解釋**\n\n請貼上要解釋的 Python 程式碼："}

        if last_user:
            reply = interactive_chat_api(last_user)
            if not isinstance(reply, str):
                reply = str(reply)
            return {"text": reply + "\n\n**點「輸入框上方的按鈕」可返回主選單。**"}

        return {"text": MENU_TEXT}
    
    # === 模式 1：互動開發 ===
    if mode == "1":
        ctx = session.get("ctx") or {}
        step = session.get("step") or "need"
        msg = last_user

        def _preview(text: str, n=1200):
            return (text or "").strip()[:n]

        def _append_history(item: str):
            hist = ctx.get("history", [])
            hist.append(item)
            ctx["history"] = hist

        if not msg and step == "need":
            return {"text": "**模式 1｜互動開發**\n\n請描述你的功能需求（一句或一段話即可）。"}

        if step == "need":
            ctx["need"] = msg.strip()
            vc_preview = _mode1_generate_virtual_code(ctx)
            ctx["virtual_code_preview"] = vc_preview or ""
            session["ctx"] = ctx
            session["step"] = "vc_confirm"
            _append_history("虛擬碼產生完成(候選)")
            return {
                "text": (
                    "=== 虛擬碼 (預覽) ===\n"
                    f"```\n{_preview(vc_preview)}\n```\n\n"
                    "是否符合需求？\n"
                    "**點「輸入框上方的按鈕」即可選擇。**"
                )
            }

        if step == "vc_confirm":
            choice = (msg or "").strip().lower()
            if choice in ("", "y", "yes"):
                ctx["virtual_code"] = ctx.get("virtual_code_preview", "")
                _append_history("接受虛擬碼")

                # 1. 先產生測資 (使用 build_test_prompt)
                test_prompt = build_test_prompt(ctx["need"])
                test_resp = run_model(test_prompt)
                raw_tests = extract_json_block(test_resp)
                json_tests = normalize_tests(raw_tests) 
                if not json_tests:
                    json_tests = normalize_tests(parse_tests_from_text(ctx["need"]))

                ctx["tests"] = json_tests or []

                # 2. 再產生程式碼
                code_prompt_string = build_stdin_code_prompt(
                    ctx["need"],
                    ctx.get("virtual_code", ""),
                    ctx.get("tests", [])
                )
                code_resp = generate_response(code_prompt_string)
                code_block = extract_code_block(code_resp)

                if isinstance(code_block, list):
                    def _pick_python_code(blocks):
                        for b in blocks:
                            if isinstance(b, str) and ("def main(" in b or "__name__" in b or "input(" in b):
                                return b
                        for b in blocks:
                            if isinstance(b, str):
                                return b
                        return None
                    code_block = _pick_python_code(code_block)

                if not code_block or not isinstance(code_block, str) or not code_block.strip():
                    session["ctx"] = ctx
                    session["step"] = "need"
                    return {"text": "模型暫時無法產生程式碼，請換個說法或補充需求後再試。"}

                explain_prompt = build_explain_prompt(ctx["need"], code_block)
                explain_resp = run_model(explain_prompt)

                ctx.update({
                    "code": code_block,
                    "need_text": ctx["need"],
                })

                if "history" not in ctx:
                    ctx["history"] = []
                _append_history(f"測資筆數: {len(ctx['tests'])}")
                _append_history("初始程式產生完成（stdin 版本）")
                session["ctx"] = ctx
                session["step"] = "verify_prompt"

                body = (
                    "=== 程式碼（初始版，stdin/stdout） ===\n"
                    f"```python\n{code_block}\n```\n\n"
                    "=== 程式碼解釋 ===\n"
                    f"{explain_resp}\n\n"
                    "要執行程式（main 測試）嗎？\n"
                    "**點「輸入框上方的按鈕」即可選擇。**"
                )
                return {"text": body}

            elif choice in ("n", "no"):
                vc_preview = _mode1_generate_virtual_code(ctx)
                ctx["virtual_code_preview"] = vc_preview or ""
                session["ctx"] = ctx
                session["step"] = "vc_confirm"
                _append_history("重新產生虛擬碼")
                return {
                    "text": (
                        "=== 虛擬碼 (預覽-NEW) ===\n"
                        f"```\n{_preview(vc_preview)}\n```\n\n"
                        "是否符合需求？\n"
                        "**點「輸入框上方的按鈕」即可選擇。**"
                    )
                }

            elif choice == "a":
                session["ctx"] = ctx
                session["step"] = "need_append"
                return {"text": "請輸入補充說明（單段文字即可）。"}
            else:
                session["ctx"] = ctx
                session["step"] = "vc_confirm"
                return {"text": "無效輸入，請點擊「輸入框上方的按鈕」。"}

        if step == "need_append":
            extra = (msg or "").strip()
            if extra:
                ctx["need"] = (ctx.get("need", "").strip() + f"\n(補充說明: {extra})").strip()
            vc_preview = _mode1_generate_virtual_code(ctx)
            ctx["virtual_code_preview"] = vc_preview or ""
            session["ctx"] = ctx
            session["step"] = "vc_confirm"
            return {
                "text": (
                    "=== 虛擬碼 (預覽-含補充) ===\n"
                    f"```\n{vc_preview}\n```\n\n"
                    "是否符合需求？\n"
                    "**點「輸入框上方的按鈕」即可選擇。**"
                )
            }
        
        if step == "verify_prompt":
            choice = (msg or "").strip().upper()
            code = ctx.get("code") or ""
            need_text = ctx.get("need_text", "")
            tests = ctx.get("tests") or []

            if choice == "M":
                report_lines = []
                if tests:
                    all_passed = True
                    report_lines.append("=== 程式執行/驗證結果（依測資逐筆） ===")
                    for i, t in enumerate(tests, 1):
                        # [修改] 使用 _normalize_stdin 處理輸入
                        inp_val = t.get("input") if isinstance(t, dict) else (t[0] if isinstance(t, (list, tuple)) and len(t) >= 2 else None)
                        exp_val = t.get("output") if isinstance(t, dict) else (t[1] if isinstance(t, (list, tuple)) and len(t) >= 2 else None)
                        
                        stdin_str = _normalize_stdin(inp_val)
                        expected_str = _normalize_stdin(exp_val) # 輸出通常也是字串，用同樣方式正規化較保險

                        input_display = stdin_str.replace("\n", "\\n")
                        output_display = expected_str.strip()
                        report_lines.append(f"\n--- 測試案例 {i} ---")
                        report_lines.append(f"輸入: {input_display}")
                        report_lines.append(f"輸出: {output_display}")

                        ok, detail = validate_main_function(
                            code=code,
                            stdin_input=stdin_str,
                            expected_output=expected_str
                        )
                        report_lines.append("結果: [通過]" if ok else "結果: [失敗]")
                        report_lines.append(f"你的輸出:\n{detail}")
                        if not ok:
                            all_passed = False

                    report_lines.append("\n" + "="*20)
                    report_lines.append("總結: [成功] 所有測資均已通過。" if all_passed else "總結: [失敗] 部分測資未通過。")
                    session["step"] = "modify_gate"
                    return {"text": "\n".join(report_lines) + "\n\n是否進入互動式修改模式？\n**點「輸入框上方的按鈕」即可選擇。**"}

                else:
                    ok, detail = validate_main_function(code, stdin_input="", expected_output=None)
                    session["step"] = "modify_gate"
                    return {
                        "text": (
                            "=== 程式執行/驗證結果（無測資，空輸入）===\n"
                            f"{detail}\n\n"
                            "是否進入互動式修改模式？\n"
                            "**點「輸入框上方的按鈕」即可選擇。**"
                        )
                    }

            elif choice == "N":
                try:
                    validate_python_code(code, [], need_text)
                except Exception:
                    pass
                session["step"] = "modify_gate"
                return {
                    "text": (
                        "已略過執行驗證。\n\n是否進入互動式修改模式？\n"
                        "**點「輸入框上方的按鈕」即可選擇。**"
                    )
                }
            else:
                return {"text": "要執行程式（main 測試）嗎？\n**點「輸入框上方的按鈕」即可選擇。**"}

        if step == "modify_gate":
            ans = (msg or "").strip().lower()
            if ans in ("y", "yes"):
                session["step"] = "modify_loop"
                return {"text": "\n=== 進入互動式修改模式 ===\n"
                                "請選擇您的下一步操作：\n"
                                "  - 修改：直接輸入您的修正需求\n"
                                "  - 驗證 VERIFY\n"
                                "  - 解釋 EXPLAIN\n"
                                "  - 完成 QUIT\n"}
            elif ans in ("n", "no"):
                final_code = ctx.get("code") or ""
                session.update({"mode": None, "awaiting": False, "step": None, "ctx": {}})
                return {"text": f"開發模式結束。最終程式如下：\n```python\n{final_code}\n```"}
            else:
                return {"text": "請輸入 y 或 n。"}
        
        if step == "modify_explain_wait":
            explain_query = (msg or "").strip()
            code = ctx.get("code") or ""
            need_text = ctx.get("need_text", "")

            if explain_query and explain_query.upper() != "ALL":
                prompt = build_specific_explain_prompt(code, explain_query)
            else:
                prompt = build_explain_prompt(need_text, code)

            resp = run_model(prompt)
            session["step"] = "modify_loop"
            return {"text": f"=== 程式碼解釋 ===\n{resp}\n\n"
                            "請選擇您的下一步操作：\n"
                            "  - 修改：直接輸入您的修正需求\n"
                            "  - 驗證 VERIFY\n"
                            "  - 解釋 EXPLAIN\n"
                            "  - 完成 QUIT\n"}

        if step == "modify_loop":
            choice = (msg or "").strip()
            code = ctx.get("code") or ""
            need_text = ctx.get("need_text", ctx.get("need", ""))
            virtual_code = ctx.get("virtual_code", "")
            json_tests = ctx.get("tests", [])
            history = ctx.get("history", [])
            u = choice.upper()

            if u in {"V", "VERIFY"}:
                print("[Mode 1 VERIFY] 正在重新生成測資 (Standard Prompt)...")
                test_prompt = build_test_prompt(need_text)
                test_resp = run_model(test_prompt)
                raw_tests = extract_json_block(test_resp)
                json_tests = normalize_tests(raw_tests)
                if not json_tests:
                    json_tests = normalize_tests(parse_tests_from_text(need_text))

                ctx["tests"] = json_tests or []
                tests = ctx["tests"]
                history.append(f"重新生成測資 (共 {len(tests)} 筆)")

                ctx["history"] = history
                session["ctx"] = ctx

                if not tests:
                    ok, detail = validate_main_function(code, stdin_input="", expected_output=None)
                    return {
                        "text": (
                            "=== 程式執行/驗證結果 (無新測資，空輸入) ===\n"
                            f"{detail}\n\n"
                            "請選擇您的下一步操作：\n"
                            "  - 修改：直接輸入您的修正需求\n"
                            "  - 驗證 VERIFY\n"
                            "  - 解釋 EXPLAIN\n"
                            "  - 完成 QUIT\n"
                        )
                    }
                
                report_lines = []
                all_passed = True
                report_lines.append("=== 程式執行/驗證結果 (依*新*測資逐筆) ===")
                for i, t in enumerate(tests, 1):
                    # [修改] 使用 _normalize_stdin 處理輸入
                    inp_val = t.get("input") if isinstance(t, dict) else (t[0] if isinstance(t, (list, tuple)) and len(t) >= 2 else None)
                    exp_val = t.get("output") if isinstance(t, dict) else (t[1] if isinstance(t, (list, tuple)) and len(t) >= 2 else None)
                    
                    stdin_str = _normalize_stdin(inp_val)
                    expected_str = _normalize_stdin(exp_val)

                    input_display = stdin_str.replace("\n", "\\n")
                    output_display = expected_str.strip()
                    report_lines.append(f"\n--- 測試案例 {i} ---")
                    report_lines.append(f"輸入: {input_display}")
                    report_lines.append(f"輸出: {output_display}")

                    ok, detail = validate_main_function(code=code, stdin_input=stdin_str, expected_output=expected_str)
                    report_lines.append("結果: [通過]" if ok else "結果: [失敗]")
                    report_lines.append(f"你的輸出:\n{detail}")
                    if not ok: all_passed = False

                report_lines.append("\n" + "="*20)
                report_lines.append("總結: [成功] 所有新測資均已通過。" if all_passed else "總結: [失敗] 部分新測資未通過。")
                
                return {"text": "\n".join(report_lines) + "\n\n"
                                "請選擇您的下一步操作：\n"
                                "  - 修改：直接輸入您的修正需求\n"
                                "  - 驗證 VERIFY\n"
                                "  - 解釋 EXPLAIN\n"
                                "  - 完成 QUIT\n"}

            if u in {"E", "EXPLAIN"}:
                session["step"] = "modify_explain_wait"
                return {"text": "請輸入您想了解的具體部分 (若要解釋全文，請輸入 'ALL'):"}

            if u in {"Q", "QUIT"}:
                final_code = ctx.get("code") or ""
                session.update({"mode": None, "awaiting": False, "step": None, "ctx": {}})
                return {"text": f"已結束互動式修改模式。最終程式如下：\n```python\n{final_code}\n```"}

            modification_request = choice
            fix_prompt_string = build_fix_code_prompt(
                need_text,
                virtual_code,
                json_tests,
                history,
                code,
                modification_request
            )
            fix_resp = generate_response(fix_prompt_string)
            new_code = extract_code_block(fix_resp)

            if new_code:
                ctx["code"] = new_code
                history.append(f"修改: {modification_request}")
                ctx["history"] = history
                session["ctx"] = ctx
                return {"text": f"=== 程式碼（新版本） ===\n```python\n{new_code}\n```\n"
                                "請輸入下一步（修改 / VERIFY / EXPLAIN / QUIT）"}
            else:
                return {"text": "模型無法生成修正後的程式碼，請重試或輸入更明確的修改需求。\n"
                                "或輸入 VERIFY / EXPLAIN / QUIT"}

        session["step"] = "need"
        return {"text": "請描述你的需求："}

    # === 模式 2：程式驗證 ===
    if mode == "2":
        ctx = session.get("ctx") or {}
        step = session.get("step") or "code"
        msg = last_user

        # [步驟 1] 等待程式碼
        if step == "code":
            if not msg or not msg.strip():
                return {"text": "**模式 2｜程式驗證**\n\n請貼上要驗證的 Python 程式碼："}
            ctx["code"] = msg
            session["ctx"] = ctx
            session["step"] = "need"
            return {"text": "已收到程式碼。\n請輸入這段程式碼的「需求說明」，AI 將以此生成測資來驗證。\n(若不提供，請直接輸入 'skip' 或 '無')"}

        # [步驟 2] 等待需求
        if step == "need":
            ctx["need"] = msg.strip()
            session["ctx"] = ctx
            session["step"] = "strategy"
            return {
                "text": (
                    "請選擇測資生成策略：\n"
                    "  [1] 標準模式 (Standard) - 平衡覆蓋率與速度\n"
                    "  [2] 高準確度模式 (Accuracy) - 雙重驗證，寧缺勿濫 (推薦)\n"
                    "  [3] 遺傳演算法 (GA) - 透過演化探索多樣化邊界\n"
                    "  [4] 變異測試 (MuTAP) - 找出程式盲點 (較慢)\n\n"
                    "請輸入選項數字 (1~4)，預設為 [1]："
                )
            }

        # [步驟 3] 選擇策略並執行驗證
        if step == "strategy":
            strategy_map = {"1": "B", "2": "ACC", "3": "GA", "4": "MUTAP"}
            selected_mode = strategy_map.get(msg.strip(), "B")
            
            user_code = ctx.get("code", "")
            user_need = ctx.get("need", "")
            if user_need.lower() in ["skip", "no", "無", ""]:
                user_need = ""

            report_lines = []
            if not user_need:
                 report_lines.append("（未提供需求，僅執行程式一次）\n")
                 ok, out_msg = validate_main_function(user_code, stdin_input=None, expected_output=None)
                 if ok:
                     report_lines.append("=== 執行成功 (Exit 0) ===\n輸出:\n" + out_msg)
                 else:
                     report_lines.append("=== 執行失敗 (Non-zero exit) ===\n錯誤訊息:\n" + out_msg)
            else:
                report_lines.append(f"[處理中] 正在以 '{selected_mode}' 模式生成測資，請稍候...\n")
                
                try:
                    # 呼叫核心函式生成測資
                    raw_tests = generate_tests(user_need, user_code, mode=selected_mode)
                except Exception as e:
                    raw_tests = []
                    report_lines.append(f"[錯誤] 測資生成失敗: {e}")

                if not raw_tests:
                     report_lines.append("⚠️ 未能生成任何有效測資。")
                else:
                    report_lines.append(f"✅ 已生成 {len(raw_tests)} 筆測資，開始驗證...\n")
                    all_passed = True
                    pass_count = 0
                    
                    for i, test_tuple in enumerate(raw_tests, 1):
                        # test_tuple 格式: (func_name, [input_args], expected_output)
                        try:
                            # 取出輸入與預期輸出
                            inp_arg = test_tuple[1][0] if test_tuple[1] else ""
                            expected = test_tuple[2]
                            
                            # 正規化為字串
                            inp_str = _normalize_stdin(inp_arg)
                            exp_str = _normalize_stdin(expected)

                            # 執行驗證
                            ok, actual_out = validate_main_function(user_code, inp_str, exp_str)

                            report_lines.append(f"\n--- 測試 {i} ---")
                            report_lines.append(f"輸入: {inp_str.replace('\n', '\\n')}")
                            report_lines.append(f"預期: {exp_str.strip()}")
                            
                            if ok:
                                report_lines.append("結果: [通過] ✅")
                                pass_count += 1
                            else:
                                report_lines.append("結果: [失敗] ❌")
                                report_lines.append(f"實際: {actual_out.strip()}")
                                all_passed = False
                        except Exception as e:
                             report_lines.append(f"\n[跳過] 測試 {i} 格式異常: {e}")
                             all_passed = False

                    report_lines.append("\n" + "="*30)
                    report_lines.append(f"驗證完成！ 通過率: {pass_count}/{len(raw_tests)}")
                    if all_passed:
                        report_lines.append("🎉 恭喜！您的程式碼通過了所有測試案例。")
                    else:
                        report_lines.append("⚠️ 存在失敗的測試案例，請參考上方資訊進行除錯。")

            # 結束 Mode 2 會話
            session.update({"mode": None, "awaiting": False, "step": None, "ctx": {}})
            return {"text": "\n".join(report_lines)}

    # === 模式 3：一次性回應 ===
    try:
        if mode == "3":
            output = run_mode_3(last_user)
        else:
            output = "[錯誤] 未知模式"
    except Exception as e:
        output = f"[例外錯誤] {e}"

    session.update({"mode": None, "awaiting": False, "step": None, "ctx": {}})
    return {"text": output}


# ====== 判題 API（整合 judge_core）======
_here = os.path.dirname(os.path.abspath(__file__))
ALLOWED_BASES = [
    os.path.abspath(os.path.join(_here,"..", "..", "frontend", "data")),
]
_lessons_dir_env = os.getenv("LESSONS_DIR")
if _lessons_dir_env:
    ALLOWED_BASES.insert(0, os.path.abspath(_lessons_dir_env))

STDIN_WHITELIST: set[str] = {
    "200","300","400","500","600","700","800","900","1000","1100","1200",
}

def _should_force_stdin(data_id) -> bool:
    return str(data_id) in STDIN_WHITELIST

@app.get("/judge")
async def judge_ping():
    return {"ok": False, "error": "Use POST /judge"}

@app.post("/judge")
async def judge(request: Request):
    payload = await request.json()

    data_id = str(payload.get("data_id") or "").strip()
    practice_idx = int(payload.get("practice_idx") or 0)
    user_code = textwrap.dedent((payload.get("code") or "").strip())
    user_output_direct = payload.get("user_output")
    data_path = payload.get("data_path")
    method_from_payload = (payload.get("method") or "").strip() or None

    per_arg_build_raw = payload.get("per_arg_build")
    expect_kind = payload.get("expect_kind")
    float_tol = float(payload.get("float_tol", 1e-6))
    unordered = bool(payload.get("unordered", False))

    if not data_id and not data_path:
        raise HTTPException(status_code=400, detail="缺少 data_id 或 data_path")

    try:
        prob = load_problem_cases(
            data_id=data_id or "",
            practice_idx=practice_idx,
            data_path=data_path,
            allowed_bases=ALLOWED_BASES,
            lessons_dir_env=os.getenv("LESSONS_DIR"),
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    tests = prob["tests"]
    force_stdin = _should_force_stdin(data_id)

    if isinstance(user_output_direct, str) and len(tests) == 1:
        expected = normalize(tests[0]["expected"])
        if normalize(user_output_direct) == expected:
            return {"ok": True, "verdict": "correct"}
        suggestions = "❌ 錯誤（輸出與期望不相符）\n請檢查格式與輸出內容。"
        return {"ok": False, "verdict": "wrong", "suggestions": suggestions}

    if not user_code:
        raise HTTPException(status_code=400, detail="缺少 code 或 user_output")

    payload_arg_names = payload.get("arg_names")
    if isinstance(payload_arg_names, list) and all(isinstance(x, str) for x in payload_arg_names):
        arg_names = payload_arg_names
    else:
        arg_names = infer_arg_names_from_examples(tests)

    method_name = method_from_payload or infer_method_name_from_code(user_code)

    def _build_core_tests() -> Optional[List[Tuple[str, tuple, Any]]]:
        if force_stdin: return None
        if not arg_names or not method_name: return None
        try:
            return build_leetcode_tests_from_examples(method_name, tests, arg_names=arg_names)
        except Exception:
            return None

    core_tests = _build_core_tests()

    if core_tests is not None:
        per_arg_build: Optional[List[BuildSpec]] = None
        if isinstance(per_arg_build_raw, list):
            tmp_list: List[BuildSpec] = []
            for k in per_arg_build_raw:
                if isinstance(k, str):
                    tmp_list.append(BuildSpec(k))
            per_arg_build = tmp_list or None

        ok, runlog = validate_leetcode_code(
            user_code, core_tests, class_name="Solution",
            per_arg_build=per_arg_build, expect_kind=expect_kind,
            float_tol=float_tol, unordered=unordered,
            user_need=prob.get("description", "")
        )
        if ok:
            return {"ok": True, "verdict": "correct", "log": runlog}
        else:
            return {"ok": False, "verdict": "wrong", "suggestions": "❌ 測資未全過：\n\n" + runlog}

    stdin_examples = [{"input": t["input"], "output": t["expected"]} for t in tests]
    ok2, log2 = validate_stdin_code(user_code, stdin_examples, timeout_sec=5)
    if ok2:
        return {"ok": True, "verdict": "correct", "log": log2}
    else:
        return {"ok": False, "verdict": "wrong", "suggestions": log2}

# ====== 翻譯 api ======
@app.post("/translate")
async def translate_api(req: Request):
    data = await req.json()
    text = (data.get("text") or "").strip()
    source = (data.get("sourceLang") or "英文").strip()
    target = (data.get("targetLang") or "繁體中文").strip()
    temperature = data.get("temperature", 0.2)

    if not text:
        raise HTTPException(status_code=400, detail="缺少 text")

    prompt = (
        f"你是一位專業中英翻譯員。請將以下文本由{source}翻譯為{target}，"
        "保持術語準確、語氣自然。只輸出譯文，不要解釋：\n\n"
        f"{text}"
    )
    try:
        translation = (generate_response(prompt) or "").strip()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"翻譯失敗：{e}")

    return {"ok": True, "translation": translation}

# ====== 獲取提示 API ======
@app.post("/hint")
async def get_hint(request: Request):
    try:
        data = await request.json()
        problem_id = data.get("problem_id") or data.get("data_id") 
        user_code = data.get("code") or data.get("user_code")
        practice_idx = int(data.get("practice_idx") or 0)

        if not problem_id or not user_code:
            raise HTTPException(status_code=400, detail="缺少 problem_id 或 code")

        possible_paths = [
            f"../frontend/data/{problem_id}.json",
            f"../frontend/data/Leetcode/{problem_id}.json",
        ]
        filepath = next((p for p in possible_paths if os.path.exists(p)), None)
        if not filepath:
            raise HTTPException(status_code=404, detail=f"找不到 {problem_id}.json")

        with open(filepath, "r", encoding="utf-8") as f:
            content = json.load(f)

        if "coding_practice" in content:
            items = content.get("coding_practice", [])
            if items:
                item = items[practice_idx] if 0 <= practice_idx < len(items) else items[0]
                problem_description = item.get("description", "無題目描述")
                examples = item.get("examples", [])
                if examples:
                    example_text = "\n".join([
                        f"範例 {i+1}:\n  輸入: {ex.get('input')}\n  輸出: {ex.get('output')}"
                        for i, ex in enumerate(examples[:2])
                    ])
                    problem_description += f"\n\n--- 範例 ---\n{example_text}"
            else:
                problem_description = "（無法載入題目描述）"
        else:
            problem_description = content.get("description") or content.get("title") or "（無法載入題目描述）"

        explanation = None
        follow_up = None
        if "coding_practice" in content:
            item = content["coding_practice"][practice_idx]
            explanation = item.get("explanation")
            follow_up = item.get("follow up")

        if explanation:
            problem_description += f"\n\n--- 題目說明 ---\n{explanation}"
        if follow_up:
            problem_description += f"\n\n--- 進階提示 ---\n{follow_up}"

        hint_prompt = build_hint_prompt(
            problem_description=problem_description,
            user_code=user_code,
            error_message=None
        )
        hint_text = run_model(hint_prompt)

        return {"ok": True, "hint": hint_text}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"獲取提示失敗：{e}")

# ====== 獲取解答 API ======
@app.post("/answer")
async def get_answer(request: Request):
    try:
        data = await request.json()
        problem_id = data.get("problem_id")
        practice_idx = data.get("practice_idx", 0)

        possible_paths = [
            f"../frontend/data/{problem_id}.json",
            f"../frontend/data/Leetcode/{problem_id}.json",
        ]
        filepath = next((p for p in possible_paths if os.path.exists(p)), None)
        if not filepath:
            raise HTTPException(status_code=404, detail=f"找不到 {problem_id}.json")

        with open(filepath, "r", encoding="utf-8") as f:
            content = json.load(f)

        practices = content.get("coding_practice")
        if not practices:
            raise HTTPException(status_code=400, detail=f"檔案中沒有 coding_practice 資料")

        if not (0 <= practice_idx < len(practices)):
            raise HTTPException(status_code=400, detail=f"practice_idx 超出範圍")

        practice = practices[practice_idx]
        solution = practice.get("solution", "(無解答)")
        explanation = practice.get("explanation", "(無說明)")

        return {"ok": True, "answer": solution, "explanation": explanation, "source_path": filepath}

    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"題目 {problem_id} 的資料不存在")
    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail=f"JSON 格式錯誤")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"獲取解答失敗：{e}")