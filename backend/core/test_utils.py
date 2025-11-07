import re
import json
import traceback
import random
import sys
import io
import trace
import textwrap
from typing import List, Dict, Any, Optional, Tuple, Set

# 導入新的 GA 提示
from core.model_interface import (
    generate_response, 
    build_virtual_code_prompt,
    build_initial_population_prompt, 
    build_crossover_prompt, 
    build_feedback_mutation_prompt
)
from core.validators import validate_main_function, _normalize_output
from core.code_extract import extract_code_block, extract_json_block

# === 適應度評估函式 (Fitness Function) ===
def _get_code_snippet(code: str, line_nums: Set[int], context=2) -> str:
    """輔助函式：從程式碼中提取未覆蓋行及其上下文"""
    lines = code.splitlines()
    snippet_lines = set()
    
    for line_num in line_nums:
        start = max(0, line_num - context - 1)
        end = min(len(lines), line_num + context)
        for i in range(start, end):
            snippet_lines.add(i)
            
    return "\n".join([f"{i+1: >4}: {lines[i]}" for i in sorted(list(snippet_lines))])

def _calculate_fitness(code: str, test_input: str) -> Tuple[float, Set[int]]:
    """
    計算測資的適應度 (Fitness)。
    返回: (分數, 未覆蓋的行號集合)
    """
    code_lines = set(range(1, code.count('\n') + 2))
    covered_lines = set()
    
    # [修改 1] 使用看起來像真實檔案的名稱，避免被 trace 過濾
    VIRTUAL_FILENAME = "ga_sandbox.py"

    # 1. 準備執行環境
    indented_code = textwrap.indent(code, '        ')
    
    # 我們在 wrapper 中加入標記行，方便定位
    wrapped_code = f"""
import sys
import io

def target_func():
    # 模擬 stdin
    sys.stdin = io.StringIO({repr(str(test_input))})
    try:
        # --- User Code Start (Line 10) ---
{indented_code}
        # --- User Code End ---
    except Exception:
        pass
"""
    
    # 2. 使用 trace 模組執行
    # ignoredirs=[sys.prefix, sys.exec_prefix] 可以減少追蹤標準庫，提高效能
    tracer = trace.Trace(count=1, trace=0, ignoredirs=[sys.prefix, sys.exec_prefix])
    
    try:
        namespace = {"io": io, "sys": sys}
        # 強制指定檔名進行編譯
        compiled = compile(wrapped_code, VIRTUAL_FILENAME, 'exec')
        exec(compiled, namespace)
        
        # 執行目標函式並追蹤
        tracer.runfunc(namespace['target_func'])
        
        # 3. 收集覆蓋結果
        results = tracer.results()
        
        # 從結果中找出我們的虛擬檔案
        if VIRTUAL_FILENAME in results.counts:
            for (filename, lineno), count in results.counts.items():
                if filename == VIRTUAL_FILENAME and count > 0:
                    # 扣除 wrapper header 的行數 (約 9 行)
                    # 實際使用者程式碼從 wrapped_code 的第 10 行開始
                    actual_lineno = lineno - 9
                    if actual_lineno > 0:
                        covered_lines.add(actual_lineno)

        fitness = len(covered_lines)
        uncovered_lines = code_lines - covered_lines
        
        # [修改 2] 啟用除錯：如果 fitness 為 0，印出到底追蹤到了什麼
        if fitness == 0 and random.random() < 0.1: # 只在 10% 的失敗情況下印出，避免洗版
             traced_files = set(f for f, l in results.counts.keys())
             print(f"    [DEBUG-GA] Fitness 0 for input {test_input!r}. Traced files: {list(traced_files)[:5]}...")

        return float(fitness), uncovered_lines

    except Exception as e:
        # print(f"[Fitness Calculation Error] {e}")
        return 0.0, code_lines

# === 基於 GA 的測試生成 (以下保持不變) ===

def _generate_tests_basic(user_need: str) -> List[list]:
    sys_prompt = build_initial_population_prompt(user_need, n=5)
    resp = generate_response(sys_prompt)
    json_tests = extract_json_block(resp)
    if json_tests and isinstance(json_tests, list):
        return [t for t in json_tests if isinstance(t, list) and len(t) == 2]
    return []

def generate_tests_hybrid_ga(user_need: str, code: str, generations=3, pop_size=6) -> List[List[str]]:
    print(f"\n[GA] 啟動演化式測試生成 (Generations={generations}, Pop={pop_size})...")
    
    init_prompt = build_initial_population_prompt(user_need, n=pop_size)
    init_resp = generate_response(init_prompt)
    population = extract_json_block(init_resp)
    
    if not population or not isinstance(population, list):
        print("[GA] 初始化失敗，回退到基本模式。")
        return _generate_tests_basic(user_need)
        
    valid_pop = []
    for p in population:
        if isinstance(p, list) and len(p) >= 1:
             inp = str(p[0])
             out = str(p[1]) if len(p) > 1 else ""
             valid_pop.append([inp, out])
    population = valid_pop

    if not population:
        print("[GA] 初始化後無有效測資，回退到基本模式。")
        return _generate_tests_basic(user_need)

    best_fitness_overall = -1.0
    
    for gen in range(generations):
        print(f"  [GA] Generation {gen+1}/{generations}...")
        
        scored_pop = []
        all_uncovered_this_gen = set()
        
        for individual in population:
            inp = individual[0]
            fitness, uncovered = _calculate_fitness(code, inp)
            scored_pop.append((individual, fitness, uncovered))
            all_uncovered_this_gen.update(uncovered)
        
        scored_pop.sort(key=lambda x: x[1], reverse=True)
        
        best_individual, best_fitness, best_uncovered = scored_pop[0]
        if best_fitness > best_fitness_overall:
            best_fitness_overall = best_fitness
            
        print(f"    > Best Fitness: {best_fitness:.1f} (Input: {best_individual[0]!r})")

        elite_count = max(2, int(pop_size * 0.5))
        elites = scored_pop[:elite_count]
        next_gen = [x[0] for x in elites]
        
        while len(next_gen) < pop_size:
            if random.random() < 0.6 and len(elites) >= 2:
                p1 = random.choice(elites)[0]
                p2 = random.choice(elites)[0]
                if p1 == p2 and len(elites) > 2:
                     p2 = elites[1][0] if p1 == elites[0][0] else elites[0][0]

                prompt = build_crossover_prompt(user_need, p1[0], p2[0])
                resp = generate_response(prompt) 
                children = extract_json_block(resp)
                if isinstance(children, list):
                    if children and isinstance(children[0], list):
                        for child in children:
                             if len(next_gen) < pop_size: next_gen.append(child)
                    else:
                         next_gen.append(children)

            else:
                parent_ind, _, parent_uncovered = random.choice(elites)
                target_lines = parent_uncovered if parent_uncovered else all_uncovered_this_gen
                if not target_lines:
                     snippet = "已全覆蓋，請嘗試極端邊界值"
                else:
                     snippet = _get_code_snippet(code, target_lines)

                prompt = build_feedback_mutation_prompt(user_need, parent_ind[0], snippet, target_lines)
                resp = generate_response(prompt)
                child = extract_json_block(resp)
                if isinstance(child, list):
                     next_gen.append(child)
            
        population = []
        for p in next_gen:
             if isinstance(p, list) and len(p) >= 1:
                 inp = str(p[0])
                 out = str(p[1]) if len(p) > 1 else ""
                 population.append([inp, out])
        
        while len(population) < pop_size:
             population.append(["", ""])

    print(f"[GA] 演化完成。最終族群前 3 名：")
    for i, p in enumerate(population[:3]):
        print(f"  {i+1}. Input: {p[0]!r}")
        
    return population

def generate_tests(user_need: str, code: str = None, mode: str = "GA") -> List[Any]:
    if mode.upper() == "GA" and code and user_need:
        try:
            return generate_tests_hybrid_ga(user_need, code)
        except Exception as e:
            print(f"[GA Error] {e}, falling back to basic mode.")
            # traceback.print_exc()
            return _generate_tests_basic(user_need)
    else:
        return _generate_tests_basic(user_need)


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
        vc_resp = generate_response(vc_prompt) #
        virtual_code = vc_resp 
        result["virtual_code"] = virtual_code

        if not virtual_code or not virtual_code.strip():
            print("     [錯誤] 模型未能生成虛擬碼。")
            result["error"] = "Failed to generate virtual code."
            return result

    except Exception as e:
        print(f"     [錯誤] 'generate_response' (虛擬碼階段) 失敗: {e}")
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

        code_resp = generate_response(code_prompt_string) #

    except Exception as e:
        print(f"     [錯誤] 'generate_response' (程式碼階段) 失敗: {e}")
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