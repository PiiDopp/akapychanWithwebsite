import re
import json
from typing import Optional, Any, List, Dict, Union

def extract_code_block(model_output: str) -> Optional[str]:
    # (維持原樣)
    m = re.search(r"```python\n(.*?)```", model_output, re.DOTALL)
    if m:
        return m.group(1).strip()
    # 有時候模型會忘記寫 python，只寫 ```
    m2 = re.search(r"```\n(.*?)```", model_output, re.DOTALL)
    return m2.group(1).strip() if m2 else None

def extract_json_block(text: str) -> Union[List, Dict, None]:
    """
    強健的 JSON 提取器。
    優先嘗試提取 ```json ... ``` 區塊，
    失敗時嘗試提取文字中第一個 '[' 或 '{' 到最後一個 ']' 或 '}' 的內容。
    """
    if not text:
        return None

    # 1. 嘗試標準的 Markdown 區塊 (允許 ```json 或單純 ```)
    match = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if match:
        block_content = match.group(1).strip()
        try:
            return json.loads(block_content)
        except json.JSONDecodeError:
            # 如果區塊內不是合法 JSON，繼續往下嘗試其他方法
            pass

    # 2. Fallback：嘗試在雜訊中尋找 JSON 結構
    # 尋找最外層的 [ ] 或 { }
    try:
        # 找到第一個 '[' 或 '{'
        start_match = re.search(r'[\[\{]', text)
        if start_match:
            start_index = start_match.start()
            # 從後面找最後一個 ']' 或 '}'
            # (這裡簡單處理，假設最後出現的括號是結尾)
            end_index = -1
            for i in range(len(text) - 1, start_index, -1):
                if text[i] in [']', '}']:
                    end_index = i + 1
                    break
            
            if end_index != -1:
                candidate = text[start_index:end_index]
                return json.loads(candidate)
    except Exception:
        pass

    print(f"[警告] 無法從模型輸出中提取 JSON。原始輸出前 100 字: {text[:100]!r}...")
    return None


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
