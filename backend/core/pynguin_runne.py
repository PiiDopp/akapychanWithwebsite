import os
import subprocess
import tempfile
import shutil
import sys

def run_pynguin_on_code(code_str: str, timeout: int = 20) -> dict:
    """
    在背景對給定的程式碼字串執行 Pynguin。
    :param code_str: 要測試的完整 Python 程式碼
    :param timeout: Pynguin 執行的最大秒數 (建議不要太長以免卡住 API)
    :return: 執行結果摘要 (例如: 生成了多少測試、是否發現 Crash)
    """
    # 1. 建立獨立的暫存工作目錄
    work_dir = tempfile.mkdtemp(prefix="pynguin_work_")
    module_name = "user_module"
    module_path = os.path.join(work_dir, f"{module_name}.py")
    output_dir = os.path.join(work_dir, "pynguin_out")

    try:
        # 2. 將使用者程式碼寫入檔案
        with open(module_path, "w", encoding="utf-8") as f:
            f.write(code_str)

        # 3. 建構 Pynguin 命令
        # 注意：Pynguin 需要指定模組名稱和輸出路徑
        cmd = [
            sys.executable, "-m", "pynguin",
            f"--project-path", work_dir,
            f"--output-path", output_dir,
            f"--module-name", module_name,
            "--timeout", str(timeout),  # 限制生成時間
            "-v" # verbose
        ]

        # 4. 執行 Pynguin
        # 使用 subprocess.run 捕獲輸出，並設定超時防止卡死
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout + 10 # 給予稍微多一點的緩衝時間
        )

        # 5. 分析結果
        # 檢查 output_dir 下是否有生成 test_user_module.py
        test_file = os.path.join(output_dir, f"test_{module_name}.py")
        generated_tests = ""
        has_tests = False
        
        if os.path.exists(test_file):
            has_tests = True
            with open(test_file, "r", encoding="utf-8") as f:
                generated_tests = f.read()

        return {
            "success": True,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "has_tests": has_tests,
            "test_code": generated_tests,
            "work_dir": work_dir # 回傳以供除錯，實際使用可能需要刪除
        }

    except subprocess.TimeoutExpired:
        return {"success": False, "error": "Pynguin execution timed out."}
    except Exception as e:
        return {"success": False, "error": str(e)}
    finally:
        # 清理暫存目錄 (在開發階段可以先註解掉以便除錯)
        # shutil.rmtree(work_dir, ignore_errors=True)
        pass