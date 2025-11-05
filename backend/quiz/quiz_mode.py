import os
import json
import random
import subprocess
import tempfile
from verify_and_explain import verify_and_explain_user_code  # 你的模型驗證函式

def list_obj_units(obj_root="./obj"):
    return sorted([d for d in os.listdir(obj_root) if os.path.isdir(os.path.join(obj_root, d))])

def load_all_coding_practice(obj_root="./obj", unit=None):
    practice_list = []
    search_path = os.path.join(obj_root, unit) if unit else obj_root
    for root, dirs, files in os.walk(search_path):
        for file in files:
            if file.endswith(".json"):
                path = os.path.join(root, file)
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        if "coding_practice" in data:
                            for item in data["coding_practice"]:
                                practice_list.append({
                                    "title": item.get("title", ""),
                                    "description": item.get("description", ""),
                                    "examples": item.get("examples", {}),
                                    "solution": item.get("solution", ""),
                                    "source_file": path
                                })
                except Exception as e:
                    print(f"[讀取失敗] {path}: {e}")
    return practice_list

def run_user_code_with_input(user_code: str, test_input: str) -> str:
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8") as tmp:
            tmp.write(user_code)
            tmp_path = tmp.name
        run = subprocess.run(
            ["python3", tmp_path],
            input=test_input,
            capture_output=True,
            text=True,
            timeout=10
        )
        return run.stdout.strip(), run.stderr.strip()
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)

def quiz_mode():
    units = list_obj_units()
    if not units:
        print("[提示] 找不到任何單元資料夾。")
        return

    print("請選擇單元：")
    for idx, name in enumerate(units, 1):
        print(f"{idx}. {name}")

    sel = input("輸入單元編號: ").strip()
    if not sel.isdigit() or not (1 <= int(sel) <= len(units)):
        print("[提示] 請輸入有效的編號。")
        return

    unit = units[int(sel) - 1]
    practices = load_all_coding_practice(unit=unit)
    if not practices:
        print("[提示] 此單元沒有練習題。")
        return

    q = random.choice(practices)
    print(f"\n=== 出題模式 ===\n單元: {unit}\n標題: {q['title']}\n描述: {q['description']}\n")
    if q.get("examples"):
        print("範例輸入/輸出：", q["examples"])

    # 使用者輸入程式碼
    print("\n請輸入你的 Python 解答，多行輸入，結束請輸入單獨一行 'END'。")
    user_lines = []
    while True:
        line = input()
        if line.strip() == "END":
            break
        user_lines.append(line)
    user_code = "\n".join(user_lines).strip()

    if not user_code:
        print("[提示] 沒有輸入程式碼，取消驗證。")
        return

    # 執行使用者程式碼，並比對範例輸入/輸出
    example = q.get("examples", {})
    if example:
        test_input = example.get("input", "")
        expected_output = example.get("output", "").strip()
        user_output, err = run_user_code_with_input(user_code, test_input)
        if err:
            print("\n[程式執行錯誤]")
            print(err)
            # 執行失敗才呼叫模型解釋
            result = verify_and_explain_user_code(user_code, reference_solution=q.get("solution", ""))
            print("\n=== 模型解釋 ===\n")
            print(result)
        else:
            print("\n[範例測資比對]")
            print(f"輸入：\n{test_input}")
            print(f"使用者輸出：\n{user_output}")
            print(f"期望輸出：\n{expected_output}")
            if user_output == expected_output:
                print("[成功] 使用者程式碼正確 ✅")
            else:
                print("[錯誤] 使用者程式碼輸出與期望不符 ❌")
                # 錯誤才呼叫模型解釋
                result = verify_and_explain_user_code(user_code, reference_solution=q.get("solution", ""))
                print("\n=== 模型解釋 ===\n")
                print(result)

    # 顯示參考解答
    print("\n=== 參考解答 ===\n")
    print(q.get("solution", "[無解答]"))
