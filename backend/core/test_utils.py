import re
import json
from core.model_interface import generate_response


def generate_tests(user_need: str, code: str, mode: str = "B") -> list[tuple]:
    """
    自動生成測資，回傳格式: [(func_name, [args], expected), ...]
    mode: "B" = 自動生成, "C" = 混合模式
    """
    func_name = None
    for line in code.splitlines():
        if line.strip().startswith("def "):
            func_name = line.split()[1].split("(")[0]
            break
    if not func_name:
        print("[警告] 無法找到函式名稱。")
        return []

    tests = []
    if mode.upper() == "B":
        sys_prompt = (
            "請根據以下需求，生成 3~5 組測資，格式為 JSON 陣列：\n"
            f"需求: {user_need}\n"
            "格式範例: [[輸入, 輸出], ...]\n"
        )
        resp = generate_response(sys_prompt)
        m = re.findall(r"\[[^\]]+\]", resp)
        try:
            parsed = json.loads("[" + ",".join(m) + "]")
        except Exception:
            parsed = []
        for t in parsed:
            if isinstance(t, list) and len(t) == 2:
                tests.append((func_name, [t[0]], t[1]))

    return tests
