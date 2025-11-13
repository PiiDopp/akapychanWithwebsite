from __future__ import annotations

# ====== 標準庫 / 第三方 ======
import os, sys, re, io, json, textwrap, tempfile, subprocess, contextlib, ast
from typing import Any, Dict, List, Optional, Tuple

from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware

# ====== 你既有的核心（互動開發 / 驗證 / 解釋 用）======
from core import (
    extract_code_block, generate_response,
    validate_main_function, validate_python_code,
    extract_json_block, parse_tests_from_text,
)
from core.model_interface import (
    build_virtual_code_prompt, build_test_prompt, build_explain_prompt,
    build_stdin_code_prompt, build_fix_code_prompt,build_hint_prompt, generate_structured_tests,
    #omm
    interactive_chat_api, normalize_tests
)

from core.explain_user_code import explain_user_code
from core.explain_error import explain_code_error
from core.pynguin_runne import run_pynguin_on_code

# ====== 判題核心（LeetCode / STDIN）(omm)======
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
# 結構：SESSIONS[chat_id] = { mode, awaiting, step, ctx:{...} }
SESSIONS: Dict[str, Dict[str, Any]] = {}

# ====== 通用預匯入 (Prelude) ======
# 用於模式 2 等需要直接執行使用者片段程式碼的場景，模擬 LeetCode 環境
PYTHON_PRELUDE = """
import sys, os, math, collections, itertools, functools, heapq, bisect, re, random, copy
from typing import *
from collections import Counter, defaultdict, deque, OrderedDict
from functools import lru_cache, cache, cmp_to_key, reduce
from heapq import heapify, heappush, heappop, heappushpop, heapreplace, nlargest, nsmallest
from itertools import accumulate, permutations, combinations, combinations_with_replacement, product, groupby, cycle, islice, count
from bisect import bisect_left, bisect_right, insort, insort_left, insort_right
from math import gcd, ceil, floor, sqrt, log, log2, log10, pi, inf, factorial, comb, perm
"""

def _run_agent3_analysis(user_need: str, user_code: str, error_msg: str) -> str:
    """呼叫 Agent 3 針對錯誤進行分析並提供提示"""
    prompt = build_hint_prompt(
        problem_description=user_need,
        user_code=user_code,
        error_message=error_msg
    )
    return run_model(prompt)
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

# ====== 輔助函式：分析 Solution 類別 ======
def get_solution_method_info(code: str) -> Tuple[Optional[str], int]:
    """
    使用 AST 分析使用者程式碼中的 Solution 類別，
    找出最可能的主要解題方法及其參數個數（不含 self）。
    回傳: (method_name, arg_count)
    """
    try:
        tree = ast.parse(textwrap.dedent(code))
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == 'Solution':
                # 找到 Solution 類別，尋找第一個非底線開頭的方法
                for subnode in node.body:
                    if isinstance(subnode, ast.FunctionDef) and not subnode.name.startswith('_'):
                        # 計算參數個數 (扣除 self)
                        arg_count = len(subnode.args.args)
                        if arg_count > 0 and subnode.args.args[0].arg == 'self':
                            arg_count -= 1
                        return subnode.name, max(0, arg_count)
    except Exception:
        pass # 解析失敗則回傳預設值
    return None, 0

# ====== 輔助函式：嘗試攤平輸入/輸出 (針對簡單 STDIN 腳本) ======
def _try_flatten_input(s: str, code: str) -> str:
    """
    如果輸入看起來是結構化的 (含有 [ 或 {)，但程式碼似乎只用 .split() 來解析，
    嘗試將結構化符號替換為空格，以利簡單的 int(x) 轉換。
    """
    if not s: return s
    # 簡單偵測程式碼是否使用 split() 且沒有使用 json/ast 解析
    if ".split()" in code and "json.loads" not in code and "ast.literal_eval" not in code:
         if '[' in s or '{' in s or ',' in s:
             return s.replace('[', ' ').replace(']', ' ').replace('{', ' ').replace('}', ' ').replace(',', ' ').strip()
    return s

def _try_flatten_output_str(s: str) -> Optional[str]:
    """
    嘗試將 JSON 陣列字串攤平為空白分隔的值。
    例如: '[0, 1]' -> '0 1'
    """
    s = (s or "").strip()
    if s.startswith('[') and s.endswith(']'):
        try:
            # 嘗試解析為 JSON 列表
            val = json.loads(s)
            if isinstance(val, list):
                # 將所有元素轉為字串並用空白連接
                return " ".join(str(x) for x in val)
        except:
            pass
    return None

# ====== 輔助函式：更強健的測資提取 ======
def _robust_extract_tests(model_response: str, user_need: str = "") -> List[Dict[str, Any]]:
    """
    嘗試從模型回覆中提取測資，支援多種格式與回退機制。
    """
    # 1. 標準提取 (尋找 ```json 區塊)
    raw_tests = extract_json_block(model_response)

    # 2. 回退機制 A: 如果沒找到區塊，嘗試直接解析整個回覆
    if not raw_tests:
        trimmed = model_response.strip()
        if (trimmed.startswith('[') and trimmed.endswith(']')):
            try:
                raw_tests = json.loads(trimmed)
            except:
                pass

    # 3. 回退機制 B (強力模式): 在整篇回覆中尋找最大的 [...] 區塊
    # 這能解決模型在 ```json 區塊外還有其他文字，或是區塊標記錯誤的問題
    if not raw_tests:
        try:
            start_idx = model_response.find('[')
            end_idx = model_response.rfind(']')
            if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
                potential_json = model_response[start_idx : end_idx + 1]
                raw_tests = json.loads(potential_json)
        except:
            pass

    # 4. 正規化 (如果抓到的是 dict，嘗試轉成 list)
    if isinstance(raw_tests, dict):
        # 有時模型會回傳 {"tests": [...]} 或 {"reasoning": "...", "data": [...]}
        for key in ["tests", "data", "examples", "cases"]:
            if key in raw_tests and isinstance(raw_tests[key], list):
                raw_tests = raw_tests[key]
                break
        else:
            # 如果還是 dict 且沒找到已知 key，嘗試把它當成單一測試案例包成 list
            raw_tests = [raw_tests]

    # 確保 raw_tests 是列表，否則正規化可能會失敗
    if not isinstance(raw_tests, list):
        raw_tests = []

    # 5. 呼叫核心的 normalize_tests
    # 注意：需要確保 core.model_interface 有匯出這個函式
    try:
        json_tests = normalize_tests(raw_tests)
    except Exception as e:
        print(f"[警告] normalize_tests 失敗: {e}")
        json_tests = []

    # 6. 回退機制 C: 從文字描述中解析 (最後手段)
    if not json_tests and user_need:
         # 這裡使用既有的 parse_tests_from_text，但它可能需要特定格式
         try:
            text_parsed = parse_tests_from_text(user_need)
            if text_parsed:
                # 這裡可能需要根據 parse_tests_from_text 的回傳格式做調整
                # 假設它回傳的是可以直接用的格式
                pass 
         except:
             pass
         
    return json_tests or []



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
        "模式 2｜程式驗證（貼程式碼 → 貼需求(可選) → AI 生成測資驗證）\n"
        "模式 3｜程式解釋（貼上要解釋的 Python 程式碼）\n\n"
        "**點「輸入框上方的按鈕」即可選擇模式。**或直接輸入文字開始一般聊天。"
    )

    # 全域：輸入 'q' 回主選單
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
                session["step"] = "awaiting_code"
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

        if not msg:
            session["step"] = "need"
            return {"text": "**模式 1｜互動開發**\n\n請描述你的功能需求（一句或一段話即可）。"}

        if step == "need":
            ctx["need"] = msg.strip()
            vc_preview = _mode1_generate_virtual_code(ctx)
            ctx["virtual_code_preview"] = vc_preview or ""
            session["ctx"] = ctx
            session["step"] = "vc_confirm"
            _append_history("Agent 1: 虛擬碼產生完成")
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
                _append_history("確認虛擬碼")

                raw_tests = generate_structured_tests(ctx["need"])
                json_tests = normalize_tests(raw_tests)
                ctx["tests"] = json_tests or []

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
                            if isinstance(b, str): return b
                        return None
                    code_block = _pick_python_code(code_block)

                if not code_block or not isinstance(code_block, str) or not code_block.strip():
                    session["ctx"] = ctx
                    session["step"] = "need"
                    return {"text": "Agent 2 無法產生有效程式碼，請嘗試補充需求細節。"}

                explain_prompt = build_explain_prompt(ctx["need"], code_block)
                explain_resp = run_model(explain_prompt)

                ctx.update({
                    "code": code_block,
                    "need_text": ctx["need"],
                })

                py_res = run_pynguin_on_code(PYTHON_PRELUDE + "\n" + code_block, timeout=10)
                pynguin_note = ""
                if py_res["success"] and py_res["has_tests"]:
                    pynguin_note = "\n(✅ 系統已通過自動化工具初步驗證此程式碼的可測試性)"

                session["ctx"] = ctx
                session["step"] = "verify_prompt"

                body = (
                    "=== 程式碼（初始版，stdin/stdout） ===\n"
                    f"```python\n{code_block}\n```\n"
                    f"{pynguin_note}\n"
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
                _append_history("Agent 1: 重新生成虛擬碼")
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
        
        # 共用驗證邏輯 (Agent 3)
        def _perform_verification(code: str, tests: List[Dict]) -> Tuple[str, str]:
            code_to_run = PYTHON_PRELUDE + "\n" + code
            all_passed = False
            report_lines = []
            error_for_agent3 = ""

            # LeetCode 模式
            is_leetcode = "class Solution" in code
            if is_leetcode:
                try:
                    method_name, expected_arg_count = get_solution_method_info(code)
                    if not method_name: method_name = infer_method_name_from_code(code)
                    if method_name:
                        core_tests = []
                        for t in tests:
                            inp = t.get("input")
                            out = t.get("output")
                            args = None
                            if isinstance(inp, list) and expected_arg_count > 1 and len(inp) == expected_arg_count:
                                args = tuple(inp)
                            else:
                                args = (inp,)
                            core_tests.append((method_name, args, out))

                        all_passed, runlog = validate_leetcode_code(code_to_run, core_tests, class_name="Solution")
                        report_lines.append(runlog)
                        if not all_passed: error_for_agent3 = runlog
                except Exception:
                    is_leetcode = False

            # STDIN 模式
            if not is_leetcode:
                if tests:
                    report_lines.append("=== 程式執行/驗證結果（依測資逐筆） ===")
                    all_passed = True
                    for i, t in enumerate(tests, 1):
                        stdin_str = str(t.get("input", ""))
                        expected_str = str(t.get("output", ""))
                        stdin_to_use = _try_flatten_input(stdin_str, code)
                        
                        ok, detail = validate_main_function(code_to_run, stdin_input=stdin_to_use, expected_output=expected_str)
                        
                        if not ok:
                            flat_exp = _try_flatten_output_str(expected_str)
                            if flat_exp and flat_exp != expected_str:
                                ok2, detail2 = validate_main_function(code_to_run, stdin_input=stdin_to_use, expected_output=flat_exp)
                                if ok2: 
                                    ok = True
                                    detail = detail2 # 成功時更新為 Output

                        # [修改] 顯示 Input, Output, Expected
                        status_icon = '[通過]✅' if ok else '[失敗]❌'
                        sb = [f"Case {i}: {status_icon}"]
                        sb.append(f"  Input: {stdin_str.strip()}")
                        sb.append(f"  Output: {detail.strip()}")
                        
                        if not ok:
                            sb.append(f"  Expected: {expected_str.strip()}")

                        report_lines.append("\n".join(sb))
                        report_lines.append("") # 分隔線

                        if not ok: 
                            all_passed = False
                            if not error_for_agent3: error_for_agent3 = detail
                else:
                    ok, detail = validate_main_function(code_to_run, stdin_input="", expected_output=None)
                    report_lines.append(f"執行結果:\n{detail}")
                    if not ok: error_for_agent3 = detail

            return "\n".join(report_lines), error_for_agent3

        # 初次驗證
        if step == "verify_prompt":
            choice = (msg or "").strip().upper()
            code = ctx.get("code") or ""
            tests = ctx.get("tests") or []

            if choice == "M": 
                session["step"] = "modify_gate"
                report_text, error_msg = _perform_verification(code, tests)
                
                if error_msg:
                    report_text += "\n\n[Agent 3] 偵測到錯誤，正在分析原因並提供提示...\n"
                    try:
                        analysis = _run_agent3_analysis(ctx["need"], code, error_msg)
                        report_text += f"=== Agent 3 分析報告 ===\n{analysis}"
                    except Exception as e:
                        report_text += f"[Agent 3 分析失敗] {e}"

                return {"text": report_text + "\n\n是否進入互動式修改模式？\n**點「輸入框上方的按鈕」即可選擇。**"}

            elif choice == "N":
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

        if step == "modify_loop":
            choice = (msg or "").strip()
            code = ctx.get("code") or ""
            need_text = ctx.get("need_text", "")
            virtual_code = ctx.get("virtual_code", "")
            json_tests = ctx.get("tests", [])
            history = ctx.get("history", [])
            u = choice.upper()

            if u in {"V", "VERIFY"}:
                report_text, error_msg = _perform_verification(code, json_tests)
                if error_msg:
                    report_text += "\n\n[Agent 3] 偵測到錯誤，正在分析原因並提供提示...\n"
                    try:
                        analysis = _run_agent3_analysis(need_text, code, error_msg)
                        report_text += f"=== Agent 3 分析報告 ===\n{analysis}"
                    except Exception as e:
                        report_text += f"[Agent 3 分析失敗] {e}"
                
                return {"text": f"{report_text}\n\n請選擇您的下一步操作：\n"
                                "  - 修改：直接輸入您的修正需求\n"
                                "  - 驗證 VERIFY\n"
                                "  - 解釋 EXPLAIN\n"
                                "  - 完成 QUIT\n"}

            if u in {"E", "EXPLAIN"}:
                explain_prompt = build_explain_prompt(need_text, code)
                text = f"=== Agent 4: 程式碼解釋 ===\n{run_model(explain_prompt)}"
                return {"text": f"{text}\n\n請選擇您的下一步操作：\n"
                                "  - 修改：直接輸入您的修正需求\n"
                                "  - 驗證 VERIFY\n"
                                "  - 解釋 EXPLAIN\n"
                                "  - 完成 QUIT\n"}

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
                text = f"=== Agent 4: 修正後程式碼 ===\n```python\n{new_code}\n```"
            else:
                text = "Agent 4 無法生成修正後的程式碼，請輸入更明確的需求。"

            return {"text": f"{text}\n\n請選擇您的下一步操作：\n"
                            "  - 修改：直接輸入您的修正需求\n"
                            "  - 驗證 VERIFY\n"
                            "  - 解釋 EXPLAIN\n"
                            "  - 完成 QUIT\n"}

        session["step"] = "need"
        return {"text": "請描述你的需求："}

    # === 模式 2：程式驗證 (互動式) ===
    if mode == "2":
        ctx = session.get("ctx") or {}
        step = session.get("step") or "awaiting_code"
        msg = last_user

        if step == "awaiting_code":
            if not msg.strip():
                 return {"text": "**模式 2｜程式驗證**\n\n請貼上要驗證的 Python 程式碼："}
            ctx["code"] = msg
            session["ctx"] = ctx
            session["step"] = "awaiting_need"
            return {"text": "已收到程式碼。\n\n請輸入這段程式碼的「需求說明」，AI 將以此生成測資來驗證。\n(若不想使用測資驗證，請直接輸入 **SKIP** 或 **跳過**，將僅執行一次程式)"}

        if step == "awaiting_need":
            user_need = msg.strip()
            raw_user_code = ctx.get("code", "")
            user_code_to_run = PYTHON_PRELUDE + "\n" + raw_user_code
            report = []

            if user_need and user_need.upper() not in ["SKIP", "跳過"]:
                report.append(f"[提示] 正在根據需求說明生成測資...\n需求：{user_need[:100]}...\n")
                
                py_res = run_pynguin_on_code(user_code_to_run, timeout=15)
                if py_res["success"] and py_res["has_tests"]:
                     report.append(f"[Pynguin] ✅ 已自動生成額外的單元測試。\n")
                
                try:
                    need_with_context = f"需求: {user_need}\n\n程式碼:\n```python\n{raw_user_code}\n```"
                    raw_tests = generate_structured_tests(need_with_context)
                    json_tests = normalize_tests(raw_tests)

                    if json_tests:
                        report.append(f"[提示] 已提取 {len(json_tests)} 筆測資。開始驗證...\n")
                        is_leetcode = "class Solution" in raw_user_code
                        if is_leetcode:
                            try:
                                method, cnt = get_solution_method_info(raw_user_code)
                                if not method: method = infer_method_name_from_code(raw_user_code)
                                if method:
                                    core = []
                                    for t in json_tests:
                                        inp, out = t.get("input"), t.get("output")
                                        args = tuple(inp) if isinstance(inp, list) and cnt > 1 and len(inp) == cnt else (inp,)
                                        core.append((method, args, out))
                                    ok, log = validate_leetcode_code(user_code_to_run, core, class_name="Solution")
                                    report.append(log)
                                    if not ok:
                                        report.append("\n[Agent 3] 分析失敗原因...\n")
                                        report.append(_run_agent3_analysis(user_need, raw_user_code, log))
                            except Exception as e:
                                report.append(f"[LeetCode 驗證錯誤] {e}")
                        else:
                            # [修改] 模式 2 的 STDIN 驗證報告也同步更新
                            for i, t in enumerate(json_tests, 1):
                                inp = str(t.get("input",""))
                                out = str(t.get("output",""))
                                inp_flat = _try_flatten_input(inp, user_code_to_run)
                                ok, det = validate_main_function(user_code_to_run, stdin_input=inp_flat, expected_output=out)
                                
                                status_icon = '[通過]✅' if ok else '[失敗]❌'
                                sb = [f"Case {i}: {status_icon}"]
                                sb.append(f"  Input: {inp.strip()}")
                                sb.append(f"  Output: {det.strip()}")
                                if not ok:
                                    sb.append(f"  Expected: {out.strip()}")
                                report.append("\n".join(sb))
                                
                                if not ok:
                                     report.append("\n[Agent 3] 分析失敗原因...\n")
                                     report.append(_run_agent3_analysis(user_need, raw_user_code, det))
                                     break 
                    else:
                        report.append("[警告] 未能提取有效測資，僅執行一次。")
                        ok, det = validate_main_function(user_code_to_run, None, None)
                        report.append(det)
                except Exception as e:
                    report.append(f"[錯誤] {e}")
            else:
                report.append("[提示] 跳過測資生成，僅執行。")
                ok, det = validate_main_function(user_code_to_run, None, None)
                report.append(det)

            session.update({"mode": None, "awaiting": False, "step": None, "ctx": {}})
            return {"text": "\n".join(report)}

    # === 模式 3：一次性回應 ===
    try:
        if mode == "3":
            output = run_mode_3(last_user)
        else:
            output = "[錯誤] 未知模式或是該模式尚未實作完成。"
    except Exception as e:
        output = f"[例外錯誤] {e}"

    session.update({"mode": None, "awaiting": False, "step": None, "ctx": {}})
    return {"text": output}


# ====== 判題 API（整合 judge_core）(omm)======
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
    data_path = payload.get("data_path")  # 例如 /Leetcode/leetcode1.json
    method_from_payload = (payload.get("method") or "").strip() or None

    # LeetCode 進階參數（可選）
    per_arg_build_raw = payload.get("per_arg_build")  # 例：["listnode","raw"]
    expect_kind = payload.get("expect_kind")          # "listnode" / "btree" / None
    float_tol = float(payload.get("float_tol", 1e-6))
    unordered = bool(payload.get("unordered", False))

    if not data_id and not data_path:
        raise HTTPException(status_code=400, detail="缺少 data_id 或 data_path")

    # 載題（交給 judge_core）
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
    print(f"[DEBUG] data_id={data_id!r}, force_stdin={force_stdin}, "
          f"payload.force_mode={payload.get('force_mode')!r}, "
          f"prob.force_mode={prob.get('force_mode')!r}")

    # A) 使用者直接提供輸出（僅單一測資）
    if isinstance(user_output_direct, str) and len(tests) == 1:
        expected = normalize(tests[0]["expected"])
        if normalize(user_output_direct) == expected:
            return {"ok": True, "verdict": "correct"}
        suggestions = "❌ 錯誤（輸出與期望不相符）\n請檢查格式與輸出內容。"
        return {"ok": False, "verdict": "wrong", "suggestions": suggestions}

    if not user_code:
        raise HTTPException(status_code=400, detail="缺少 code 或 user_output")

    # 嘗試 OJ（LeetCode）模式；若推不出 method/arg，就回退 STDIN
    payload_arg_names = payload.get("arg_names")
    if isinstance(payload_arg_names, list) and all(isinstance(x, str) for x in payload_arg_names):
        arg_names = payload_arg_names
    else:
        arg_names = infer_arg_names_from_examples(tests)

    method_name = method_from_payload or infer_method_name_from_code(user_code)

    def _build_core_tests() -> Optional[List[Tuple[str, tuple, Any]]]:
        if force_stdin:
            return None
        if not arg_names or not method_name:
            return None
        try:
            return build_leetcode_tests_from_examples(method_name, tests, arg_names=arg_names)
        except Exception:
            return None

    core_tests = _build_core_tests()

    # 模式一：LeetCode / OJ
    if core_tests is not None:
        print("[MODE] OJ]")
        per_arg_build: Optional[List[BuildSpec]] = None
        if isinstance(per_arg_build_raw, list):
            tmp_list: List[BuildSpec] = []
            for k in per_arg_build_raw:
                if isinstance(k, str):
                    tmp_list.append(BuildSpec(k))
            per_arg_build = tmp_list or None

        ok, runlog = validate_leetcode_code(
            user_code,
            core_tests,
            class_name="Solution",
            per_arg_build=per_arg_build,
            expect_kind=expect_kind,
            float_tol=float_tol,
            unordered=unordered,
            user_need=prob.get("description", "")
        )
        if ok:
            return {"ok": True, "verdict": "correct", "log": runlog}
        else:
            return {"ok": False, "verdict": "wrong", "suggestions": "❌ 測資未全過：\n\n" + runlog}

    # 模式二：STDIN
    print("[MODE] STDIN")
    stdin_examples = [{"input": t["input"], "output": t["expected"]} for t in tests]
    ok2, log2 = validate_stdin_code(user_code, stdin_examples, timeout_sec=5)
    if ok2:
        return {"ok": True, "verdict": "correct", "log": log2}
    else:
        return {"ok": False, "verdict": "wrong", "suggestions": log2}

# ====== 翻譯 api(omm)======
@app.post("/translate")
async def translate_api(req: Request):
    """
    翻譯 API
    入參(JSON):
      { "text": "...", "sourceLang": "英文", "targetLang": "繁體中文", "temperature": 0.2 }
    回傳(JSON):
      { "ok": true, "translation": "..." }
    """
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

# ====== 新增 /hint 路由 (STUB) ======
@app.post("/hint")
async def get_hint(request: Request):
    """
    獲取提示 API
    入參(JSON):
      {
        "problem_id": "...",
        "practice_idx": 1,
        "code": "...",
        "data_path": "...",
        "mode": "stdin",
        "source": "builtin"
      }
    回傳(JSON):
      { "ok": true, "hint": "..." }
    """
    try:
        data = await request.json()
        problem_id = data.get("problem_id") or data.get("data_id")  # 相容舊版欄位
        user_code = data.get("code") or data.get("user_code")       # 改用 code
        practice_idx = int(data.get("practice_idx") or 0)
        data_path = data.get("data_path")
        # 'mode' and 'source' are not used by the hint logic, but are part of the request

        if not problem_id or not user_code:
            raise HTTPException(status_code=400, detail="缺少 problem_id 或 code")

        # 1. 載入題目描述
        problem_description = "（無法載入題目描述）"
        try:
            prob = load_problem_cases(
                data_id=problem_id or "",
                practice_idx=practice_idx,
                data_path=data_path,
                allowed_bases=ALLOWED_BASES,
                lessons_dir_env=os.getenv("LESSONS_DIR"),
            )
            problem_description = prob.get("description", "無題目描述")
            
            # 嘗試獲取更詳細的描述或標題
            if problem_description == "無題目描述":
                problem_description = prob.get("title", "無題目描述")
            
            # 獲取範例測資作為額外上下文
            tests = prob.get("tests", [])
            if tests:
                examples = "\n".join([
                    f"範例 {i+1}:\n  輸入: {t.get('input')}\n  輸出: {t.get('expected')}" 
                    for i, t in enumerate(tests[:2]) # 最多取 2 個範例
                ])
                problem_description += f"\n\n--- 範例 ---\n{examples}"

        except Exception as e:
            print(f"[警告] /hint 路由無法載入題目 ({problem_id}): {e}")
            # 即使載入失敗，還是繼續，只是描述會比較少
            pass

        # 2. 建立提示 Prompt (目前不執行程式碼，未來可擴充)
        error_message = None 
        
        hint_prompt = build_hint_prompt(
            problem_description=problem_description,
            user_code=user_code,
            error_message=error_message
        )

        # 3. 呼叫模型 (run_model 已在 main.py 中定義)
        hint_text = run_model(hint_prompt)

        print(f"[INFO] /hint 路由被呼叫, problem_id: {problem_id}")
        return {"ok": True, "hint": hint_text}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"獲取提示失敗：{e}")
# ====== 新增 /answer 路由 (STUB) ======
@app.post("/answer")
async def get_answer(request: Request):
    try:
        data = await request.json()
        problem_id = data.get("problem_id")
        practice_idx = data.get("practice_idx", 0)

        # 讀取對應題目的 JSON 檔案
        possible_paths = [
            f"../frontend/data/{problem_id}.json",
            f"../frontend/data/Leetcode/{problem_id}.json",
        ]
        filepath = next((p for p in possible_paths if os.path.exists(p)), None)
        if not filepath:
            raise HTTPException(status_code=404, detail=f"找不到 {problem_id}.json")

        # 讀取 JSON
        with open(filepath, "r", encoding="utf-8") as f:
            content = json.load(f)

        # 取出題目陣列
        practices = content.get("coding_practice")
        if not practices:
            raise HTTPException(status_code=400, detail=f"檔案中沒有 coding_practice 資料")

        # 防止 practice_idx 超出範圍
        if not (0 <= practice_idx < len(practices)):
            raise HTTPException(
                status_code=400,
                detail=f"practice_idx {practice_idx} 超出範圍 (共有 {len(practices)} 題)"
            )

        # 抓出對應題目
        practice = practices[practice_idx]
        solution = practice.get("solution", "(無解答)")
        explanation = practice.get("explanation", "(無說明)")

        print(f"[INFO] /answer 讀取成功: {filepath}")
        return {
            "ok": True,
            "answer": solution,
            "explanation": explanation,
            "source_path": filepath  # 可用於除錯
        }

    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"題目 {problem_id} 的資料不存在")
    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail=f"JSON 格式錯誤：{problem_id}.json")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"獲取解答失敗：{e}")