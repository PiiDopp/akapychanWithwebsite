import subprocess
import os
import tempfile
import shutil
import re

class MutationRunner:
    """
    執行 MutPy 以找出存活的變異體 (Surviving Mutants)。
    這些變異體代表了目前測試案例的盲點。
    """

    def __init__(self, target_code: str, test_code: str, module_name: str = "solution"):
        self.target_code = target_code
        self.test_code = test_code
        self.module_name = module_name

    def find_surviving_mutants(self) -> list[str]:
        """
        執行變異測試並回傳存活變異體的詳細資訊。
        """
        # 建立臨時工作目錄
        temp_dir = tempfile.mkdtemp()
        target_file = os.path.join(temp_dir, f"{self.module_name}.py")
        test_file = os.path.join(temp_dir, "test_solution.py")

        try:
            # 寫入標準答案
            with open(target_file, "w", encoding="utf-8") as f:
                f.write(self.target_code)

            # 寫入現有的單元測試 (確保它能 import 標準答案)
            # 我們在測試程式碼前插入 import 語句
            full_test_code = f"from {self.module_name} import *\n" + self.test_code
            with open(test_file, "w", encoding="utf-8") as f:
                f.write(full_test_code)

            # 執行 MutPy
            # 注意：需要確保執行環境中有安裝 mutpy
            cmd = [
                "mut.py",
                "--target", self.module_name,
                "--unit-test", "test_solution",
                "--runner", "unittest",
                "--show-mutants"  # 顯示變異體的具體程式碼差異
            ]

            # 執行命令並捕獲輸出
            result = subprocess.run(
                cmd,
                cwd=temp_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding='utf-8',
                errors='ignore' # 忽略可能的編碼錯誤
            )

            return self._parse_mutpy_output(result.stdout)

        finally:
            # 清理臨時目錄
            shutil.rmtree(temp_dir, ignore_errors=True)

    def _parse_mutpy_output(self, output: str) -> list[str]:
        """
        解析 MutPy 的文字輸出，提取出存活變異體的程式碼。
        這是一個簡化的解析器範例。
        """
        surviving_mutants = []
        # MutPy 的輸出格式通常包含 "survived" 關鍵字
        # 我們用正規表達式或簡單的字串分割來找出相關區塊
        
        # 簡單範例：假設 MutPy 輸出會列出每個變異體的 diff
        if "survived" in output:
             # 這裡需要根據實際 MutPy 版本輸出調整解析邏輯
             # 以下為模擬捕捉到的變異體區塊
            parts = output.split('*' * 20)
            for part in parts:
                if "survived" in part:
                    surviving_mutants.append(part.strip())
                     
        return surviving_mutants