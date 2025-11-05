import re
import json
from typing import Optional


def extract_code_block(model_output: str) -> Optional[str]:
    m = re.search(r"```python\n(.*?)```", model_output, re.DOTALL)
    return m.group(1).strip() if m else None


def extract_json_block(model_output: str) -> list:
    m = re.search(r"```json\n(.*?)```", model_output, re.DOTALL)
    if not m:
        return []
    try:
        content = m.group(1).strip()
        return json.loads(content)
    except Exception:
        print("[警告] JSON 解析失敗，請檢查模型輸出格式。")
        return []


def parse_tests_from_text(user_need: str, func_name: str = "solution_func"):
    pattern = r"Input:\s*(.*?)\s*Output:\s*(.*?)\n"
    matches = re.findall(pattern, user_need, re.DOTALL)
    tests = []
    for m in matches:
        try:
            inputs = [eval(x.strip()) for x in m[0].split(",") if x.strip()]
            if len(inputs) == 1:
                inputs = inputs[0:1]
            output = eval(m[1].strip())
            tests.append((func_name, inputs, output))
        except Exception as e:
            print(f"[警告] 解析測資失敗: {m} -> {e}")
    return tests


def normalize_tests(func_name: str, raw_tests: list) -> list[tuple]:
    tests = []
    for t in raw_tests:
        if not isinstance(t, list) or len(t) != 2:
            continue
        inp, outp = t
        if isinstance(inp, list):
            tests.append((func_name, inp, outp))
        else:
            tests.append((func_name, [inp], outp))
    return tests
