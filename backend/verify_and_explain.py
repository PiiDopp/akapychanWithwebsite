import tempfile
import os
import sys
import importlib.util
from io import StringIO
import contextlib

from core.model_interface import generate_response
from core.data_loader import load_all_json_from_dir, format_data_for_rag

RAG_CONTEXT = ""
try:
    all_data = load_all_json_from_dir(root_dir="../frontend/data/Leetcode")
    # 限制 RAG 內容長度，避免 Prompt 過長
    RAG_CONTEXT = format_data_for_rag(all_data) 
except Exception as e:
    # 忽略載入錯誤，繼續執行，只在 stderr 輸出警告
    sys.stderr.write(f"[RAG 警告] 無法載入或格式化 RAG 資料: {e}\n")

def call_function_safely(module, func_name="main", args=None):
    """
    安全呼叫函式或類別方法，支援 main() 或其他函式
    """
    args = args or []

    # 嘗試普通函式
    if hasattr(module, func_name):
        func = getattr(module, func_name)
        return func(*args)

    # 嘗試類別方法
    for obj_name in dir(module):
        obj = getattr(module, obj_name)
        if isinstance(obj, type) and hasattr(obj, func_name):
            try:
                instance = obj()
            except TypeError:
                continue
            method = getattr(instance, func_name)
            return method(*args)

    return None


def verify_and_explain_user_code(user_code: str, reference_solution: str = "", func_name="main", args=None) -> str:
    """
    嘗試執行使用者程式碼（呼叫函式方式），並使用 RAG 輔助解釋錯誤。
    - 執行成功：回傳程式輸出結果
    - 執行失敗：呼叫模型解釋錯誤原因 (RAG 輔助)
    - 提供 reference_solution 時進行驗證
    """
    tmp_path = None
    args = args or []

    try:
        # 建立臨時檔案
        with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8") as tmp:
            tmp.write(user_code)
            tmp_path = tmp.name

        # 載入模組
        spec = importlib.util.spec_from_file_location("solution", tmp_path)
        module = importlib.util.module_from_spec(spec)
        sys.modules["solution"] = module
        spec.loader.exec_module(module)

        # 捕捉 print 輸出
        user_output = None

        try:
            buf = StringIO()
            with contextlib.redirect_stdout(buf):
                result = call_function_safely(module, func_name, args)
                if result is None:
                    # 無函式可呼叫 → 執行整個檔案 __main__ 區塊
                    exec(open(tmp_path, encoding="utf-8").read(), {"__name__": "__main__"})
            user_output = buf.getvalue().strip()

        except Exception as e:
            # 發生錯誤 → 呼叫模型解釋 (RAG 輔助)
                    
            # --- RAG Injection ---
            rag_prefix = ""
            if RAG_CONTEXT:
                rag_prefix = (
                    "--- RAG 輔助資料 (編碼練習題) ---\n"
                    f"{RAG_CONTEXT}\n"
                    "請參考上述資料，這些資訊可能與使用者正在嘗試解決的 LeetCode 類型問題相關，用來輔助你生成更精確的錯誤解釋與修正建議。\n"
                    "--- RAG 輔助資料結束 ---\n\n"
                )
            # --- End RAG Injection ---

            prompt = (
                f"{rag_prefix}" # <-- 注入 RAG context
                "你是一個 Python 教學助理，專門幫助使用者理解錯誤訊息。\n"
                f"以下是使用者貼的程式碼：\n```\n{user_code}\n```\n"
                f"執行函式 {func_name}({args}) 時發生錯誤:\n```\n{e}\n```\n"
                "請用繁體中文詳細解釋錯誤原因，並給出可能的修正建議。\n"
                "注意：用簡單語言解釋，避免專業術語。"
            )
            explanation = generate_response(prompt)
            return explanation

        # 成功後，若提供參考解答，進行驗證
        if reference_solution:
            validation_prompt = (
                "你是一個 Python 教學助理，幫助使用者驗證程式碼。\n"
                f"以下是使用者程式碼的輸出：\n```\n{user_output}\n```\n"
                f"以下是參考解答程式碼：\n```\n{reference_solution}\n```\n"
                "請檢查使用者程式碼是否符合參考解答，"
                "並回傳簡單結論（符合或不符合），若不符合，簡述差異。\n"
                "請用繁體中文回答。"
            )
            validation_result = generate_response(validation_prompt)
            return (
                f"[成功] 函式 {func_name} 執行完成 ✅\n"
                f"程式輸出:\n{user_output}\n\n"
                f"=== 驗證結果 ===\n{validation_result}"
            )

        # 執行成功，無參考解答
        return f"[成功] 函式 {func_name} 執行完成 ✅\n程式輸出:\n{user_output}"

    except Exception as e:
        return f"[錯誤] 驗證或解釋程式碼時發生例外: {e}"

    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)
