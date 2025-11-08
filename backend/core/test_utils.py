import re
import json
import traceback
import random
from typing import List, Dict, Any, Optional
from io import StringIO
import unittest.mock as mock

from core.model_interface import (
    call_ollama_cli, build_virtual_code_prompt, generate_response,
    build_cot_test_prompt, build_mutation_killing_prompt,
    build_ga_crossover_prompt, build_ga_mutation_prompt,
    build_high_confidence_test_prompt, build_test_verification_prompt
)
from core.validators import validate_main_function, _normalize_output
from core.code_extract import extract_code_block, extract_json_block
from core.mutation_runner import MutationRunner

def json_to_unittest(json_tests: list) -> str:
    """
    將 JSON 測資轉換為 MutPy 可執行的 unittest 程式碼字串。
    [改進] 使用 patch('sys.stdin', StringIO(user_input)) 以同時支援 input() 和 sys.stdin.read()。
    """
    code_lines = [
        "import unittest",
        "from unittest.mock import patch",
        "from io import StringIO",
        "import sys",
        "",
        # 預先定義一個可能需要的 main，避免 import 錯誤
        "from solution import main as target_main" if "from solution" not in "".join(json_tests) else "", 
        "",
        "class TestSolution(unittest.TestCase):"
    ]

    for i, test in enumerate(json_tests):
        if not isinstance(test, list) or len(test) < 2:
            continue
            
        inp = str(test[0]).replace('\\', '\\\\').replace("'", "\\'").replace('"', '\\"')
        exp = str(test[1]).replace('\\', '\\\\').replace("'", "\\'").replace('"', '\\"')
        
        test_method = f"""
    def test_case_{i+1}(self):
        user_input = '{inp}'
        expected_output = '{exp}'
        with patch('sys.stdout', new=StringIO()) as fake_out:
            # [修正] 同時 Mock sys.stdin，支援兩種讀取方式
            with patch('sys.stdin', StringIO(user_input)):
                try:
                    # 嘗試呼叫被測模組的 main()
                    if 'target_main' in globals():
                        target_main()
                    elif 'main' in globals():
                        main()
                    else:
                        # 如果沒有 main，嘗試直接執行模組層級代碼 (較少見但可能)
                        pass
                except StopIteration: 
                    pass 
                except SystemExit:
                    pass
                    
        actual = fake_out.getvalue().strip()
        expected = expected_output.strip()
        # 簡單的斷言訊息
        msg = f"Input: {{user_input!r}}\\nExpected: {{expected!r}}\\nGot: {{actual!r}}"
        self.assertEqual(actual, expected, msg=msg)
"""
        code_lines.append(test_method)

    return "\n".join(code_lines)

def generate_tests(user_need: str, code: str, mode: str = "B") -> list[tuple]:
    """
    自動生成測資。
    mode="B": 標準模式
    mode="ACC": 高準確度模式 (雙重驗證)
    mode="GA": 遺傳演算法模式
    mode="MuTAP": 變異測試模式
    """
    func_name = "solution" # 簡化，預設使用 solution

    tests = []
    print(f"[generate_tests] 正在以模式 '{mode}' 生成測資...")

    # =========================================
    # 模式 A: 高準確度模式 (ACC) - 獨立路徑
    # =========================================
    if mode.upper() == "ACC":
        print("[ACC] 啟動高信心生成與雙重驗證機制...")
        prompt = build_high_confidence_test_prompt(user_need)
        resp = generate_response(prompt)
        candidates = extract_json_block(resp) or []
        
        if not candidates:
             # 嘗試用 regex 抓取
             m = re.findall(r"\[\s*\[.*?\]\s*\]", resp, re.DOTALL)
             if m:
                 try: candidates = json.loads(m[0])
                 except: pass

        print(f"[ACC] 初始生成了 {len(candidates)} 個候選測資，開始逐一驗證...")
        verified_count = 0
        for i, cand in enumerate(candidates):
            if isinstance(cand, list) and len(cand) >= 2:
                inp, exp = cand[0], cand[1]
                # 簡化顯示
                inp_show = str(inp)[:15] + "..." if len(str(inp)) > 15 else str(inp)
                exp_show = str(exp)[:15] + "..." if len(str(exp)) > 15 else str(exp)
                print(f"  > 驗證候選 {i+1}: Input='{inp_show}' | Expected='{exp_show}'")
                
                verify_prompt = build_test_verification_prompt(user_need, inp, exp)
                verify_resp = generate_response(verify_prompt)
                
                if "VERDICT: PASS" in verify_resp:
                    tests.append((func_name, [inp], exp))
                    print("    -> [通過] 驗證成功，已加入測資集。✅")
                    verified_count += 1
                else:
                     print("    -> [剔除] 驗證失敗，信心不足。❌")

        print(f"[ACC] 最終保留了 {verified_count}/{len(candidates)} 個高準確度測資。")
        return tests # ACC 模式在此結束，不執行後續

    # =========================================
    # 模式 B/GA/MuTAP: 共用初始生成路徑
    # =========================================
    prompt = build_cot_test_prompt(user_need)
    resp = generate_response(prompt)
    extracted_json = extract_json_block(resp)
    if not extracted_json:
         m = re.findall(r"\[\s*\[.*?\]\s*\]", resp, re.DOTALL)
         if m:
             try: extracted_json = json.loads(m[0])
             except: pass

    if extracted_json:
        for t in extracted_json:
            if isinstance(t, list) and len(t) >= 2:
                tests.append((func_name, [t[0]], t[1]))
    
    print(f"[generate_tests] 初始種群大小: {len(tests)}")

    # --- GA 演化 (僅 GA 模式) ---
    if mode.upper() == "GA" and len(tests) >= 2:
        print("\n[GA] 進入遺傳演算法演化循環...")
        GENERATIONS = 1       # 為了速度先設為 1 代
        OFFSPRING_PER_GEN = 2 # 每代產生 2 個子代
        current_population = [[t[1][0], t[2]] for t in tests]

        for gen in range(GENERATIONS):
            print(f"  > [GA] 第 {gen+1} 代演化中...")
            for _ in range(OFFSPRING_PER_GEN):
                if random.random() > 0.3: # 交配
                    parents = random.sample(current_population, 2)
                    ga_prompt = build_ga_crossover_prompt(user_need, parents[0], parents[1])
                    op = "交配"
                else: # 突變
                    parent = random.choice(current_population)
                    ga_prompt = build_ga_mutation_prompt(user_need, parent)
                    op = "突變"
                
                ga_resp = generate_response(ga_prompt)
                child = extract_json_block(ga_resp)
                if child and isinstance(child, list) and len(child) >= 2:
                     # 簡單去重
                     if not any(str(existing[0]) == str(child[0]) for existing in current_population):
                         current_population.append([child[0], child[1]])
                         print(f"    [GA] ({op}) 產生新測資: Input='{str(child[0])[:10]}...'")

        tests = [(func_name, [p[0]], p[1]) for p in current_population]
        print(f"[GA] 演化完成，最終測資數: {len(tests)}")

    # --- MuTAP 增強 (僅 MuTAP 模式) ---
    elif mode.upper() == "MUTAP" and code.strip() and tests:
        print("\n[MuTAP] 進入變異測試增強循環...")
        current_json_tests = [[t[1][0], t[2]] for t in tests]
        unittest_code = json_to_unittest(current_json_tests)
        runner = MutationRunner(target_code=code, test_code=unittest_code)
        survivors = runner.find_surviving_mutants()

        if survivors:
             print(f"[MuTAP] 發現 {len(survivors)} 個存活變異體，嘗試生成殺手測資...")
             for i, mutant in enumerate(survivors[:2]): # 限制處理 2 個
                 kill_prompt = build_mutation_killing_prompt(code, json.dumps(current_json_tests, ensure_ascii=False), mutant)
                 kill_resp = generate_response(kill_prompt)
                 new_tests = extract_json_block(kill_resp)
                 if new_tests:
                     for nt in new_tests:
                         if isinstance(nt, list) and len(nt) >= 2:
                             tests.append((func_name, [nt[0]], nt[1]))
                             print(f"    [MuTAP] + 新增殺手測資: Input='{str(nt[0])[:10]}...'")
        else:
            print("[MuTAP] 未發現存活變異體或執行失敗。")

    return tests

# ... (保留 generate_and_validate, generate_tests_with_oracle 不變) ...
def generate_and_validate(user_need: str, examples: List[Dict[str, str]], solution: Optional[str]) -> Dict[str, Any]:
    """
    (從 testrun.py 移入)
    1. Need -> 虛擬碼
    2. 虛擬碼 + Examples + Solution -> 程式碼
    3. 驗證 (M 模式，使用 JSON 中的 examples)
    """
    result = {
        "success": False,
        "virtual_code": None,
        "generated_code": None,
        "validation_results": [],
        "reference_solution_provided": bool(solution),
        "error": None
    }

    # ---
    # === 階段 1: 生成虛擬碼 ===
    # ---
    try:
        print("     [階段 1] 正在生成虛擬碼...")
        vc_prompt = build_virtual_code_prompt(user_need) #
        vc_resp = call_ollama_cli(vc_prompt) #
        virtual_code = vc_resp 
        result["virtual_code"] = virtual_code

        if not virtual_code or not virtual_code.strip():
            print("     [錯誤] 模型未能生成虛擬碼。")
            result["error"] = "Failed to generate virtual code."
            return result

    except Exception as e:
        print(f"     [錯誤] 'call_ollama_cli' (虛擬碼階段) 失敗: {e}")
        result["error"] = f"Virtual code generation failed: {e}"
        return result

    # ---
    # === 階段 2: 依照虛擬碼、範例和參考解法生成程式碼 ===
    # ---
    try:
        print("     [階段 2] 正在根據虛擬碼、範例及參考解法生成程式碼...")

        # *** 動態構建包含 solution 的提示 (邏輯同 testrun.py) ***
        code_prompt_lines = [
            "用繁體中文回答。\n你是程式碼生成助理。\n任務：依據使用者需求、虛擬碼、範例，並參考提供的解法，產生正確可執行的 Python 程式碼，並加上白話註解。\n",
            f"原始需求：\n{user_need}\n",
            f"虛擬碼：\n{virtual_code}\n", 
            "生成的程式碼必須包含一個 `if __name__ == \"__main__\":` 區塊。\n",
            "這個 `main` 區塊必須：\n"
            "1. 從標準輸入 (stdin) 讀取解決問題所需的所有數據（例如，使用 `input()` 或 `sys.stdin.read()`）。\n"
            "2. 處理這些數據。\n"
            "3. 將最終答案打印 (print) 到標準輸出 (stdout)。\n"
            "4. **不要** 在 `main` 區塊中硬編碼 (hard-code) 任何範例輸入或輸出。\n"
        ]

        if examples:
            code_prompt_lines.append("\n以下是幾個範例，展示了程式執行時**應該**如何處理輸入和輸出（你的程式碼將透過 `stdin` 接收這些輸入）：\n")
            for i, ex in enumerate(examples):
                inp_repr = repr(ex['input'])
                out_repr = repr(ex['output'])
                code_prompt_lines.append(f"--- 範例 {i+1} ---")
                code_prompt_lines.append(f"若 stdin 輸入為: {inp_repr}")
                code_prompt_lines.append(f"則 stdout 輸出應為: {out_repr}")
            code_prompt_lines.append("\n再次強調：你的 `main` 程式碼不應該包含這些範例，它應該是通用的，能從 `stdin` 讀取任何合法的輸入。\n")
        else:
            code_prompt_lines.append("由於沒有提供範例，請確保程式碼結構完整，包含 `if __name__ == \"__main__\":` 區塊並能從 `stdin` 讀取數據。\n")

        if solution:
            code_prompt_lines.append("您可以參考以下的參考解法：\n")
            code_prompt_lines.append(f"```python\n{solution}\n```\n")
            code_prompt_lines.append("請學習此解法（但不一定要完全照抄），並生成包含 main 區塊且能通過上述範例測試的完整程式碼。\n")

        code_prompt_lines.append("⚠️ **重要**：請僅輸出一個 Python 程式碼區塊 ```python ... ```，絕對不要輸出任何額外文字或解釋。")

        code_prompt_string = "".join(code_prompt_lines)

        code_resp = call_ollama_cli(code_prompt_string) #

    except Exception as e:
        print(f"     [錯誤] 'call_ollama_cli' (程式碼階段) 失敗: {e}")
        result["error"] = f"Code generation failed: {e}"
        return result

    # ---
    # === 階段 3: 提取程式碼 ===
    # ---
    code = extract_code_block(code_resp) #
    if not code:
        print("     [錯誤] 未能從模型回覆中提取程式碼。")
        result["error"] = "Failed to extract code from model response."
        result["validation_results"].append({
            "example_index": -1,
            "input": None,
            "expected_output": None,
            "success": False,
            "output": code_resp
        })
        return result

    result["generated_code"] = code

    # ---
    # === 階段 4: 驗證 ===
    # ---
    all_examples_passed = True
    if not examples:
        print("     [提示] JSON 檔案未提供範例，無法進行輸入輸出驗證。僅檢查程式碼是否可執行。")
        try:
             validation_result = validate_main_function(code, stdin_input="", expected_output=None) #
             success, output_str = validation_result
             result["validation_results"].append({
                 "example_index": 0,
                 "input": "",
                 "expected_output": None,
                 "success": success,
                 "output": output_str
             })
             if success:
                 print("     [成功] 程式碼可執行 ✅")
                 if output_str:
                     print(f"       > 實際輸出: {repr(output_str)}")
                 result["success"] = True
             else:
                 print(f"     [失敗] 執行錯誤 ❌")
                 print(f"       > 實際輸出/錯誤: {repr(output_str)}")
                 result["error"] = "Code failed basic execution check."
                 all_examples_passed = False

        except Exception as e:
            print(f"     [嚴重錯誤] 'validate_main_function' 執行時發生例外: {e}")
            result["error"] = f"Validator crashed during basic execution check: {e}"
            result["validation_results"].append({
                 "example_index": 0,
                 "input": "",
                 "expected_output": None,
                 "success": False,
                 "output": traceback.format_exc()
            })
            all_examples_passed = False
    else:
        print(f"     [階段 3] 正在驗證 {len(examples)} 個範例...")
        for i, ex in enumerate(examples):
            stdin_input = ex['input']
            expected_output = ex['output']
            print(f"       [範例 {i+1}/{len(examples)}] 輸入: {repr(stdin_input)}, 期望輸出: {repr(expected_output)}")

            try:
                # 1. 呼叫 validator (不自動比對)
                validation_result = validate_main_function(code, stdin_input=stdin_input, expected_output=None) #
                exec_success, raw_output_str = validation_result
                
                success = False
                output_to_store = raw_output_str 

                if exec_success:
                    # 2. 執行成功，進行「標準化比對」
                    norm_expected = _normalize_output(expected_output) #
                    norm_actual = _normalize_output(raw_output_str) #
                    
                    if norm_expected == norm_actual:
                        success = True
                    else:
                        output_to_store = (
                            f"[Output Mismatch (Normalized)]\n"
                            f"Expected (Norm): {repr(norm_expected)}\n"
                            f"Got (Norm):      {repr(norm_actual)}\n"
                            f"--- (Raw) ---\n"
                            f"Raw Expected: {repr(expected_output)}\n"
                            f"Raw Got:      {repr(raw_output_str)}"
                        )
                else:
                    pass 
                
                result["validation_results"].append({
                    "example_index": i,
                    "input": stdin_input,
                    "expected_output": expected_output,
                    "success": success,
                    "output": output_to_store
                })

                if success:
                    print(f"       [成功] 範例 {i+1} 通過 ✅")
                else:
                    print(f"       [失敗] 範例 {i+1} 失敗 ❌")
                    print(f"         > 期望 (Raw): {repr(expected_output)}")
                    print(f"         > 實際 (Raw): {repr(raw_output_str)}")
                    if exec_success:
                        print(f"         > 期望 (Norm): {repr(_normalize_output(expected_output))}")
                        print(f"         > 實際 (Norm): {repr(_normalize_output(raw_output_str))}")
                    all_examples_passed = False

            except Exception as e:
                print(f"       [嚴重錯誤] 'validate_main_function' 對範例 {i+1} 執行時發生例外: {e}")
                result["error"] = f"Validator crashed on example {i+1}: {e}"
                result["validation_results"].append({
                    "example_index": i,
                    "input": stdin_input,
                    "expected_output": expected_output,
                    "success": False,
                    "output": traceback.format_exc()
                })
                all_examples_passed = False

    if all_examples_passed:
        result["success"] = True
        print("     [總結] 所有範例驗證通過 ✅")
    else:
         result["success"] = False
         if examples:
             print("     [總結] 部分或全部範例驗證失敗 ❌")

    return result

def generate_tests_with_oracle(user_need: str, reference_code: str, num_tests: int = 5) -> list:
    """
    [高準確率模式] 利用參考解法 (Oracle) 自動計算預期輸出。
    1. 要求 LLM 僅生成具備高覆蓋率的「輸入 (stdin)」。
    2. 執行 reference_code 以獲取絕對正確的「輸出 (stdout)」。
    """
    sys_prompt = (
        "你是一位專業的測試工程師。請分析以下程式需求，生成一組具備高覆蓋率的「純輸入」資料。\n"
        "請專注於設計各種邊界情況 (Edge Cases) 與極端輸入，以確保程式的穩健性。\n"
        f"需求描述:\n{user_need}\n\n"
        "請直接輸出一個 JSON 格式的字串陣列 (List of Strings)，每一項代表一次完整的標準輸入 (stdin) 內容。\n"
        "不需要任何解釋或其他文字。\n"
        "格式範例: [\"輸入1第一行\\n輸入1第二行\", \"輸入2僅一行\", \"1 2 3\\n4 5 6\"]\n"
    )
    
    print("     [Oracle] 正在生成高覆蓋率輸入...")
    resp = generate_response(sys_prompt)
    inputs = extract_json_block(resp)

    if not inputs or not isinstance(inputs, list):
        print(f"     [Oracle 警告] 無法從模型回覆中提取輸入列表。")
        return []

    valid_tests = []
    print(f"     [Oracle] 正在透過參考解法計算 {len(inputs)} 組標準答案...")

    for i, inp in enumerate(inputs):
        stdin_input = str(inp)
        # 執行參考解法來獲取標準輸出
        # 注意：這要求 reference_code 必須是完整的可執行腳本 (包含讀取 stdin 的部分)
        success, oracle_output = validate_main_function(reference_code, stdin_input, expected_output=None)

        if success:
            # 成功獲得 Oracle 輸出，這組測資是可信的
            valid_tests.append([stdin_input, oracle_output.strip()])
        else:
             print(f"     [Oracle 失敗] 參考解法無法處理第 {i+1} 組輸入，已略過。")

    return valid_tests[:num_tests]
