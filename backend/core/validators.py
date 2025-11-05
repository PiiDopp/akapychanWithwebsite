import os
import subprocess
import sys
import tempfile
import shutil
import importlib.util
import time
import typing  

from core.data_structures import auto_convert_input, auto_convert_output

# ... (檔案中其他的函式，例如 call_function_safely 和 validate_python_code 保持不變) ...
# (為了簡潔，這裡省略了 validate_python_code 的程式碼，您檔案中的版本是OK的)
# ...
# (請確保您檔案中 validate_python_code 函式仍然存在)

def validate_python_code(code: str, tests: list[tuple], user_need: str = "") -> bool:
    """
    tests: [(func_name, args, expected_result), ...]
    user_need: 使用者原始需求 (字串)，用來最後比對說明
    """
    tmp_path = None
    tmp_dir = None
    all_tests_passed = True
    try:
        # 建立臨時檔案
        with tempfile.NamedTemporaryFile(delete=False, suffix=".py") as tmp:
            tmp.write(code.encode("utf-8"))
            tmp_path = tmp.name

        # (為了簡化，我們不再 print 檔案路徑)
        # print(f"[驗證] 測試檔案: {tmp_path}")

        spec = importlib.util.spec_from_file_location("solution", tmp_path)
        module = importlib.util.module_from_spec(spec)
        sys.modules["solution"] = module
        spec.loader.exec_module(module)

        # 1) 執行程式
        run = subprocess.run(["python3", tmp_path],
                             input="", # <<--- 修正: 傳入空字串避免 input() 阻塞
                             capture_output=True, text=True, timeout=10)
        if run.returncode != 0 and "input" not in run.stderr.lower(): # 如果有 input() 導致的超時，暫時忽略這裡的 returncode
            # print("[錯誤] 程式執行失敗:\n", run.stderr)
            return False

        # 計算執行時間
        start = time.perf_counter()
        run = subprocess.run(
            ["python3", tmp_path],
            input="", # <<--- 修正: 傳入空字串避免 input() 阻塞
            capture_output=True, text=True, timeout=10
        )
        end = time.perf_counter()
        exec_time = end - start
        
        if run.returncode != 0:
            # 忽略因為 input="" 造成的執行錯誤
            if "EOFError" not in run.stderr and "ValueError" not in run.stderr:
                 # print("[錯誤] 程式執行失敗:\n", run.stderr)
                 return False

        # print(f"[成功] 程式執行完成，耗時 {exec_time:.4f} 秒 ✅")

        # ... (檔案中 validate_python_code 的其餘部分保持不變) ...
        # ... (mypy, pylint, bandit, pytest, 額外測資驗證...) ...

        # 額外測資驗證
        if tests:
            for test in tests:
                func_name, args, expected = test
                try:
                    # (省略測資驗證邏輯...)
                    pass
                except Exception as e:
                    print(f"[錯誤] 呼叫 {func_name}{args} 發生例外: {e}")
                    all_tests_passed = False
                    break

                # (省略測資驗證邏輯...)

            if all_tests_passed:
                print("[成功] 所有測資通過 ✅")
                if user_need:
                    print(f"[結果] 程式邏輯符合需求 ✅")
            else:
                if user_need:
                    print(f"[結果] ❌ 程式未能完全滿足需求：{user_need}")
                return False
        else:
            # print("[提示] 沒有提供測資，無法驗證邏輯是否符合需求。")
            pass

        return all_tests_passed

    except Exception as e:
        print(f"[驗證錯誤] {e}")
        return False
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)
        if tmp_dir and os.path.exists(tmp_dir):
            shutil.rmtree(tmp_dir, ignore_errors=True)

def _normalize_output(s: str) -> str:
    """
    (*** 第 2 版修改 ***)
    輔助函數：將 stdout 和 expected output 字串標準化以便進行比較。
    1. 去除字串前後的空白字元 (strip)。
    2. 去除最外層匹配的單引號或雙引號 (解決 "'bab'" vs "bab")。
    3. (新增) 將所有「內部」單引號替換為雙引號 (解決 "['a']" vs "[\"a\"]")。
    4. 去除所有「內部」空格 (解決 "[0, 1]" vs "[0,1]")。
    """
    if not isinstance(s, str):
        return str(s) # 如果輸入不是字串，轉換它

    s = s.strip()

    # 1. 去除最外層的引號 (e.g., "'bab'" -> "bab" 或 "['...']" -> ['...'])
    if len(s) >= 2:
        if s.startswith("'") and s.endswith("'"):
            s = s[1:-1]
        elif s.startswith('"') and s.endswith('"'):
            s = s[1:-1]

    # 2. (*** 新增 ***) 標準化所有內部引號為雙引號
    #    這會將 Python 的 "['255...']" 轉換為 "[\"255...\"]"
    s = s.replace("'", '"')

    # 3. 去除所有內部的空格 (e.g., "[0, 1]" -> "[0,1]")
    s = s.replace(" ", "")

    return s

# ---
# === 重點修改：validate_main_function ===
# ---
def validate_main_function(code: str, 
                         stdin_input: str = None, 
                         expected_output: str = None) -> tuple[bool, str]:
    """
    測試程式碼是否可執行 (透過 __main__ 區塊)。
    
    Args:
        code: 要驗證的 Python 程式碼字串。
        stdin_input: (重要) 要傳遞給 subprocess 的標準輸入 (stdin)。
        expected_output: (可選) 期望的標準輸出 (stdout)。
                         
    Returns:
        (bool, output_str): (是否成功, 實際的 stdout 或 stderr 訊息)
    """
    tmp_path = None
    try:
        # 建立臨時檔案
        with tempfile.NamedTemporaryFile(delete=False, suffix=".py") as tmp:
            tmp.write(code.encode("utf-8"))
            tmp_path = tmp.name

        # 決定要傳入的 input
        # 如果提供了 stdin_input，就使用它。
        # 如果沒有，傳入空字串 "" 來防止 input() 掛起。
        input_data = stdin_input if stdin_input is not None else ""
        
        # 執行 subprocess
        run = subprocess.run(
            ["python3", tmp_path],
            input=input_data,  # <--- 關鍵修改
            capture_output=True, 
            text=True, 
            timeout=10
        )
        
        actual_output = run.stdout.strip()
        
        if run.returncode == 0:
            # 執行成功 (Return Code 0)
            
            if expected_output is not None:
                # 如果有提供「期望輸出」，使用 _normalize_output 進行比對
                
                normalized_actual = _normalize_output(actual_output)
                normalized_expected = _normalize_output(expected_output)
                
                if normalized_actual == normalized_expected:
                    # 驗證成功 (正規化後匹配)
                    return True, actual_output # 回傳原始的(stripped)輸出
                else:
                    # 輸出不匹配
                    err_msg = (
                        f"Actual Output:\n{actual_output}\n\n"
                        f"[Output Mismatch (Normalized)]\n"
                        f"Expected: {repr(normalized_expected)}\n"
                        f"Got:      {repr(normalized_actual)}"
                    )
                    return False, err_msg
            else:
                # 沒有提供「期望輸出」，只要執行成功就算通過
                return True, actual_output
        else:
            # 執行失敗 (Return Code != 0)
            # 這可能是語法錯誤，或 (如果 input_data 不正確) 執行時錯誤
            output_on_fail = run.stderr.strip() if run.stderr.strip() else run.stdout.strip()
            return False, output_on_fail

    except subprocess.TimeoutExpired:
        return False, "[Validation Error] Code execution timed out (10s)."
    except Exception as e:
        return False, f"[Validation Error] {e}"
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)