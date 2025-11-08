# backend/core/model_interface.py
import os
import re
import time
import requests
import subprocess
from core.io_utils import ThinkingDots
from typing import List, Optional, Tuple
from core.code_extract import extract_code_block
from core.validators import validate_main_function
import json

from langchain_community.chat_message_histories import ChatMessageHistory
from langchain_core.runnables.history import RunnableWithMessageHistory
from langchain_ollama import OllamaLLM
from langchain_core.prompts import ChatPromptTemplate

# ===== 基本設定 =====
OLLAMA_HOST   = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")
MODEL_NAME    = os.environ.get("MODEL_NAME",  "gpt-oss")         # 原本的完整模型（長文/正式）
FAST_MODEL    = os.environ.get("FAST_MODEL",  MODEL_NAME)        # 快速模型
KEEP_ALIVE    = os.environ.get("OLLAMA_KEEP_ALIVE", "5m")        # 預熱時間
# 快速路徑的生成上限與逾時（秒）
FAST_NUM_PREDICT = int(os.getenv("LLM_FAST_NUM_PREDICT", "160")) # 典型錯誤解釋 2~4 句
FAST_TIMEOUT_SEC = int(os.getenv("LLM_FAST_TIMEOUT", "12"))      # 逾時就放棄

def call_ollama_cli(prompt: str, model: str = MODEL_NAME) -> str:
    """
    透過 Ollama CLI 呼叫模型
    """
    try:
        proc = subprocess.run(
            ["ollama", "run", model, prompt],
            capture_output=True, text=True, timeout=300
        )
        return proc.stdout.strip() or proc.stderr.strip()
    except Exception as e:
        return f"[CLI 呼叫失敗] {e}"

def _post_ollama(prompt: str, model: str, *, num_predict: int | None, timeout_sec: int | None):
    """
    低階呼叫：可指定 num_predict 與 timeout。
    """
    url = f"{OLLAMA_HOST}/api/generate"
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "keep_alive": KEEP_ALIVE,
    }
    # 精簡生成
    options = {
        # 控制生成長度與速度
        **({"num_predict": num_predict} if num_predict is not None else {}),
        "temperature": 0.2,
        "top_k": 30,
        "top_p": 0.9,
        "repeat_penalty": 1.05,
    }
    payload["options"] = options
    # 有逾時則套用（connect/read 分開避免掛住）
    kwargs = {}
    if timeout_sec is not None and timeout_sec > 0:
        kwargs["timeout"] = (5, max(5, timeout_sec - 5))

    res = requests.post(url, json=payload, **kwargs)
    res.raise_for_status()
    data = res.json()
    return (data.get("response") or "").strip()

# ===================== 高階介面 =====================
def generate_response(prompt: str, model: str = MODEL_NAME) -> str:
    """
    正常/完整輸出（保留原本行為；不強制設定逾時與 num_predict）。
    """
    spinner = ThinkingDots("模型思考中")
    start_time = time.perf_counter()
    spinner.start()
    try:
        resp = _post_ollama(prompt, model, num_predict=None, timeout_sec=None)
        if not resp:
            return (
                "❌ 無法連線到本機模型（Ollama HTTP）。\n"
                f"1) 服務：{OLLAMA_HOST}\n"
                f"2) 模型：{model}\n"
                "3) Windows/WSL2/Docker 埠號是否正確。"
            )
        return resp
    except Exception as e:
        return f"[HTTP 呼叫失敗] {e}"
    finally:
        spinner.stop()
        print(f"[資訊] 模型思考時間: {time.perf_counter() - start_time:.3f} 秒")

# ===================== Prompt Builders =====================

def build_virtual_code_prompt(user_need: str) -> str:
    """
    產生虛擬碼 (Virtual Code)，類似流程圖的描述方式
    """
    return (
        "用繁體中文回答。\n"
        "你是一個虛擬碼生成助理。\n"
        "任務：根據使用者的自然語言需求，**逐行地**產生對應的虛擬碼 (Virtual Code)，並在每行虛擬碼之後**立即**提供該行的**簡短、直觀的解釋**。\n"
        "⚠️ 請勿輸出實際程式碼，只輸出結構化的步驟。\n\n"
        "**輸出格式要求**：\n"
        "1.  **逐行**輸出。\n"
        "2.  **每行**必須包含：`虛擬碼步驟` + `[空格]` + `// 解釋/說明`。\n"
        "3.  使用虛擬碼的箭頭 (`→`, `Yes →`, `No →`) 和結構 (`Start`, `End`, `Decision:`)。\n\n"
        "**格式範例**：\n"
        "```\n"
        "Start // 程式開始執行\n"
        "→ Step 1: 輸入使用者數字 // 從使用者處取得一個數值\n"
        "→ Decision: 如果數字大於 0? // 檢查數值是否為正\n"
        "    Yes → Step 2: 輸出 '正數' // 如果是正數，顯示該訊息\n"
        "    No  → Decision: 如果數字等於 0? // 如果不是正數，檢查是否為零\n"
        "        Yes → Step 3: 輸出 '零' // 數字是零，顯示該訊息\n"
        "        No  → Step 4: 輸出 '負數' // 否則數值是負數\n"
        "End // 程式執行結束\n"
        "```\n\n"
        f"使用者需求:\n{user_need}\n\n請根據**輸出格式要求**產生虛擬碼和逐行解釋："
    )

def build_code_prompt(user_need: str) -> str:
    """
    只產生 Python 程式碼，且程式碼必須包含 main() 函式。
    """
    return (
        "用繁體中文回答。\n"
        "你是程式碼生成助理。\n"
        "任務：依據使用者需求產生正確可執行的 Python 程式碼，並加上白話註解。\n\n"
        "⚠️ **重要**：請僅輸出一個 Python 程式碼區塊，絕對不要輸出任何額外文字或解釋。\n"
        "程式碼必須：\n"
        "  1) 定義一個 `def main():` 函式作為程式進入點，\n"
        "  2) 在 `main()` 函式內，**必須包含具體的測試案例程式碼**，展示如何呼叫你定義的函式，並用 `print()` 輸出結果。\n"
        "  3) 在檔案尾端包含 `if __name__ == \"__main__\":\\n    main()` 以便直接執行，\n"
        "  4) 包含必要的白話註解以說明主要步驟。\n\n"
        "輸出格式範例（務必遵守）：\n"
        "```python\n"
        "# 你的程式碼（包含 def main(): 與 if __name__ == \"__main__\": main() ）\n"
        "```\n\n"
        f"使用者需求:\n{user_need}\n\n"
        "請產生符合上述要求的 Python 程式碼："
    )



def build_test_prompt(user_need: str) -> str:
    """
    只產生測資
    """
    return (
        "用繁體中文回答。\n"
        "你是一個測資生成助理。\n"
        "任務：根據使用者需求，產生 3~5 組測資，格式如下：\n"
        "```json\n[[輸入, 輸出], [輸入, 輸出], ...]\n```\n"
        f"\n使用者需求:\n{user_need}\n\n請產生測資："
    )


def build_explain_prompt(user_need: str, code: str) -> str:
    """
    只解釋程式碼，避免混進程式或測資
    """
    return (
        "用繁體中文回答。\n"
        "你是一個程式解釋助理。\n"
        "任務：解釋下面的 Python 程式碼，請用白話淺顯的方式，避免使用專業術語。\n\n"
        f"使用者需求:\n{user_need}\n\n"
        f"程式碼:\n```python\n{code}```\n\n"
        "請輸出程式碼的功能說明："
    )

def build_translate_prompt(text: str, target_language: str = "English") -> str:
    """
    建立一個用於翻譯的提示。
    """
    return (
        f"你是一個專業的翻譯助理。\n"
        f"任務：將以下文字翻譯成「{target_language}」。\n"
        "⚠️ **重要**：請僅輸出翻譯後的文字，絕對不要輸出任何額外文字、解釋或引號。\n\n"
        f"原文：\n{text}\n\n"
        f"翻譯為「{target_language}」的結果："
    )

def build_initial_population_prompt(user_need: str, n=6) -> str:
    return (
        f"你是一個專業的軟體測試工程師。\n"
        f"請針對以下需求，設計 {n} 組「邊界測試案例」與「一般測試案例」。\n"
        f"需求：{user_need}\n\n"
        "規則：\n"
        "1. 每一組測資必須包含 [輸入字串, 預期輸出字串]。\n"
        "2. 輸入與輸出都必須是字串格式，如果是多行輸入請用 \\n 連接。\n"
        "3. 專注於邊界情況 (例如: 空輸入、最大值、最小值、特殊字元)。\n"
        "4. 絕對不要輸出任何解釋文字，只輸出 JSON。\n"
        "5. ⚠️務必使用 Markdown 程式碼區塊包住 JSON 輸出。\n\n"
        "輸出範例格式：\n"
        "```json\n"
        "[\n"
        "  [\"輸入1\", \"輸出1\"],\n"
        "  [\"輸入2\", \"輸出2\"]\n"
        "]\n"
        "```\n"
    )

def build_crossover_prompt(user_need: str, parent1: list, parent2: list) -> str:
    """
    [GA] 交配 (Crossover)：結合兩個父代測資的特徵產生子代。
    """
    return (
        "你是一個測試演化演算法的操作員。\n"
        f"任務：參考以下兩個父代測資，結合它們的特徵（例如：輸入的結構、邊界情況、資料類型），產生一個新的、合法的子代測資，以測試此需求：{user_need}。\n"
        f"父代 1: {json.dumps(parent1, ensure_ascii=False)}\n"
        f"父代 2: {json.dumps(parent2, ensure_ascii=False)}\n"
        "⚠️ 僅輸出一個新的 JSON 測資 `[新輸入, 新預期輸出]`，不要有其他文字。"
    )

def build_feedback_mutation_prompt(user_need: str, parent: list, code_snippet: str, uncovered_lines: set) -> str:
    """
    [GA] 突變 (Mutation)：根據「未覆蓋行」的回饋進行智慧突變。
    """
    uncovered_str = ", ".join(map(str, sorted(list(uncovered_lines))[:5])) # 最多顯示5行
    
    return (
        "你是一個測試演化演算法的操作員。\n"
        f"任務：對以下測資進行「突變」（微調），以嘗試執行到先前「未被覆蓋」的程式碼行。\n\n"
        f"使用者需求:\n{user_need}\n\n"
        f"程式碼片段 (包含未覆蓋行):\n```python\n{code_snippet}\n```\n\n"
        f"原始測資 (此測資未能執行到以下行號): {json.dumps(parent, ensure_ascii=False)}\n"
        f"**目標：產生一個新測資，使其能執行到行號 {uncovered_str} 附近的邏輯。**\n\n"
        "⚠️ 僅輸出突變後的 JSON 測資 `[新輸入, 新預期輸出]`，不要有其他文字。"
    )

def interactive_langchain_chat():
    """
    使用 LangChain 的 ConversationChain 實現多輪對話模式。
    """
    print("=== 模型互動聊天模式 (LangChain 多輪對話) ===")
    print(f"使用的模型: {MODEL_NAME}")
    print("對話會記住歷史紀錄。結束請輸入 'quit'。")

    try:
        llm = OllamaLLM(model=MODEL_NAME)

        # 2. 定義 prompt 模板
        prompt = ChatPromptTemplate.from_template("{input}")

        # 3. 建立對話記憶
        history = ChatMessageHistory()

        # 4. 建立對話鏈 (取代 ConversationChain)
        conversation = RunnableWithMessageHistory(
            prompt | llm,
            lambda session_id: history,
            input_messages_key="input",
        )

        while True:
            user_input = input("你 (輸入 'quit' 結束): ").strip()

            if user_input.lower() == "quit":
                print("離開互動聊天模式。")
                break

            if not user_input:
                continue
            
            # 使用 LangChain 的 ConversationChain 進行對話
            try:
                # 顯示思考點點
                spinner = ThinkingDots("模型思考中")
                start_time = time.perf_counter()
                spinner.start()

                # 呼叫對話鏈
                # LangChain 會自動處理 prompt 模板、歷史紀錄的插入
                resp = conversation.invoke({"input": user_input})['response']

                spinner.stop()
                duration = time.perf_counter() - start_time
                print(f"[資訊] 模型思考時間: {duration:.3f} 秒")
                
                print("\n=== 模型回覆 ===\n")
                print(resp)
                print("\n---------------------------------\n")

            except Exception as e:
                spinner.stop()
                print(f"\n[錯誤] LangChain 模型回覆失敗：{e}")
                print("請檢查 Ollama 服務是否啟動，以及模型是否已 Pull。")

    except ImportError:
        print("\n[錯誤] 缺少 LangChain 相關套件。請執行 'pip install langchain langchain-community'。")
    except Exception as e:
        print(f"\n[錯誤] 初始化 LangChain 失敗: {e}")
        print("請確保 Ollama 服務已啟動。")

def interactive_chat():
    """
    與模型進行互動式聊天或程式碼解釋。
    使用者可輸入自然語言或貼上 Python 程式碼。
    結束請輸入 'END'。
    """
    print("=== 模型互動聊天模式 ===")
    print("請輸入需求或程式碼，多行輸入，結束請輸入單獨一行 'END'。")
    print("輸入 'quit' 離開。")

    while True:
        lines = []
        while True:
            line = input()
            if line.strip().lower() in ("end", "quit"):
                break
            lines.append(line)

        if not lines:
            print("[提示] 沒有輸入任何內容。")
            continue

        # 若使用者輸入 quit 結束
        if lines and lines[0].strip().lower() == "quit":
            print("離開互動聊天模式。")
            break

        user_input = "\n".join(lines).strip()

        # 偵測是否貼了 Python 程式碼
        if "def " in user_input or "print(" in user_input or "for " in user_input:
            print("\n[提示] 偵測到 Python 程式碼，進入解釋模式...\n")
            prompt = build_explain_prompt("使用者貼上的程式碼", user_input)
        else:
            # 為基礎聊天模式加入助教身份
            prompt = (
                "用繁體中文回答。\n"
                "你是一位友善且專業的程式學習助教。\n"
                "請用白話、簡單易懂的方式回答使用者的程式相關問題。\n\n"
                f"使用者問題：\n{user_input}"
            )

        try:
            resp = generate_response(prompt)
            print("\n=== 模型回覆 ===\n")
            print(resp)
            print("\n---------------------------------\n")
        except Exception as e:
            print(f"[錯誤] 模型回覆失敗：{e}")

# ===================== API版本 (omm) =====================

# 供 API 版單輪聊天使用的程式碼檢測
_CODE_FENCE_RE = re.compile(r"```(?:python)?\s*(.*?)\s*```", re.DOTALL | re.IGNORECASE)

def interactive_chat_api(user_input: str) -> str:
    """
    API 版互動聊天（單輪）：
    - 若偵測到 Python 程式碼：用 build_explain_prompt 產生解釋
    - 否則：以助教口吻一般聊天回覆
    回傳：模型文字回覆
    """
    text = (user_input or "").strip()
    if not text:
        return "請先輸入一段訊息。"
    
    # 嘗試從 ``` 區塊取出程式碼；若沒有，就用原文字
    m = _CODE_FENCE_RE.search(text)
    code_candidate = m.group(1) if m else text

    # 簡單的程式碼偵測（含常見 Python 關鍵字／結構）
    looks_like_code = (
        "def " in code_candidate or "print(" in code_candidate or "for " in code_candidate or
        "while " in code_candidate or "class " in code_candidate or "import " in code_candidate or
        "if __name__" in code_candidate or "return " in code_candidate or
        (" = " in code_candidate and "(" in code_candidate and ")" in code_candidate)
    )

    if looks_like_code:
        prompt = build_explain_prompt("使用者貼上的程式碼", code_candidate)
    else:
        prompt = (
            "用繁體中文回答。\n"
            "你是一位友善且專業的程式學習助教。\n"
            "請用白話、簡單易懂的方式回答使用者的程式相關問題。\n\n"
            f"使用者問題：\n{text}"
        )

    try:
        return generate_response(prompt)  # ← 修正：呼叫本檔案的 generate_response
    except Exception as e:
        return f"[錯誤] 模型回覆失敗：{e}"

def interactive_code_modification_loop():
    print("=== 互動式程式碼開發與修正模式 (生成/修正/解釋) ===")

    # 1. 取得初始需求
    print("請輸入您的程式碼需求，多行輸入，結束請輸入單獨一行 'END'。")
    lines = []
    while True:
        try:
            line = input()
        except EOFError:
            break
        if line.strip() == "END":
            break
        lines.append(line)

    user_need = "\n".join(lines).strip()
    if not user_need:
        print("[提示] 沒有輸入需求，取消操作。")
        return

    current_code = ""
    history = [f"初始需求: {user_need}"]

    # 2. 初始生成
    print("\n[第一步] 產生初始程式碼...")

    # --- (可選) 略過虛擬碼步驟，直接生成程式碼 ---
    # 如果需要虛擬碼步驟，可以取消註解以下程式碼並修改邏輯
    # vc_prompt = build_virtual_code_prompt(user_need)
    # vc_resp = generate_response(vc_prompt)
    # print("\n=== 模型回覆 (虛擬碼) ===\n", vc_resp)
    # ---------------------------------------------

    code_prompt = build_code_prompt(user_need)
    code_resp = generate_response(code_prompt)
    current_code = extract_code_block(code_resp)

    if not current_code:
        print("[錯誤] 模型無法生成程式碼，請重試。")
        return

    print("\n=== 程式碼 (初始版本) ===\n")
    print(f"```python\n{current_code}\n```")

    # 3. 進入修正迴圈
    while True:
        print("\n" + "="*40)
        print("請輸入您的下一步操作：")
        print("  - [修改/優化/重構]：輸入您的需求說明 (例如: '請將迴圈改為列表推導式')")
        print("  - [驗證]：輸入 'VERIFY' 或 'V' (執行程式並檢查錯誤/邏輯)") # 修改說明
        print("  - [解釋]：輸入 'EXPLAIN' 或 'E' (取得當前程式碼的白話解釋)") # 修改說明
        print("  - [完成]：輸入 'QUIT' (結束開發，儲存最終程式碼)")
        print("="*40)

        user_input = input("您的操作 (或修改需求): ").strip()

        if user_input.upper() == "QUIT":
            print("\n開發模式結束。最終程式碼如下：")
            print(f"```python\n{current_code}\n```")
            break

        if user_input.upper() in ("VERIFY", "V"): # 修改判斷
            print("\n[驗證中] 執行程式碼並檢查錯誤...")
            # 假設 validate_main_function 返回 (bool, str) 分別表示成功與否和輸出/錯誤訊息
            success, validation_result = validate_main_function(current_code) # 修改接收方式
            print("\n=== 程式執行/錯誤報告 ===\n")
            print(validation_result)

            # 如果執行失敗，且 validation_result 包含錯誤訊息 (可以進一步判斷)
            # 這裡簡化，直接假設模型可能提供修正建議
            # 注意：原始程式碼中 validate_main_function 不直接調用模型解釋錯誤並提供修正版
            # 這部分邏輯需要依賴 validate_main_function 的實際行為或外部錯誤處理
            # 以下為示意性代碼，假設 validation_result 可能包含修正建議的標記
            if not success and "修正版程式" in validation_result: # 示意性判斷
                 temp_code = extract_code_block(validation_result)
                 if temp_code:
                     print("\n[提示] 模型提供了修正建議。是否要將當前程式碼替換為修正版？(y/n): ", end="")
                     choice = input().strip().lower()
                     if choice in ["y", "yes", "是", "好"]:
                         current_code = temp_code
                         history.append("自動採納模型修正版。")
                         print("\n[成功] 已採納修正版程式碼。")
                         print(f"```python\n{current_code}\n```")
                     else:
                         print("\n[提示] 已忽略修正建議，您可手動提供修改需求。")

        elif user_input.upper() in ("EXPLAIN", "E"): # 修改判斷
            print("\n[解釋中] 產生程式碼解釋...")
            explain_prompt = build_explain_prompt(user_need, current_code)
            explain_resp = generate_response(explain_prompt)
            print("\n=== 程式碼解釋 ===\n")
            print(explain_resp)

        else: # 修正需求
            modification_request = user_input
            print(f"\n[修正中] 正在根據您的要求 '{modification_request}' 修正程式碼...")

            # 構建修正提示
            fix_prompt = build_code_prompt(
                f"請根據以下歷史需求與當前程式碼，進行修正和重構：\n"
                f"--- 初始需求 ---\n"
                f"{user_need}\n"
                f"--- 當前程式碼 ---\n"
                f"```python\n{current_code}\n```\n"
                f"--- 新增修改需求 ---\n"
                f"{modification_request}\n"
                f"請確保輸出只有一個完整的 Python 程式碼區塊。"
            )

            fix_resp = generate_response(fix_prompt)
            new_code = extract_code_block(fix_resp)

            if new_code:
                current_code = new_code
                history.append(f"上次修改: {modification_request}")
                print("\n=== 程式碼 (新版本) ===\n")
                print(f"```python\n{current_code}\n```")
            else:
                print("[警告] 模型無法生成修正後的程式碼。請重試或輸入更明確的指令。")

    return current_code # 函數應回傳最終代碼

def build_stdin_code_prompt(user_need: str, virtual_code: str, json_tests: Optional[List[Tuple[str, str]]]) -> str:
    """
    (MODIFIED) 建立一個專門用於生成 stdin/stdout 程式碼的提示。
    採用 testrun.py 的提示邏輯。
    """
    code_prompt_lines = [
        "用繁體中文回答。\n你是程式碼生成助理。\n任務：依據使用者需求、虛擬碼、範例，產生正確可執行的 Python 程式碼，並加上白話註解。\n",
        f"原始需求：\n{user_need}\n",
        f"虛擬碼：\n{virtual_code}\n",
        "生成的程式碼必須包含一個 `if __name__ == \"__main__\":` 區塊。\n",
        "這個 `main` 區塊必須：\n"
        "1. 從標準輸入 (stdin) 讀取解決問題所需的所有數據（例如，使用 `input()` 或 `sys.stdin.read()`）。\n"
        "2. 處理這些數據。\n"
        "3. 將最終答案打印 (print) 到標準輸出 (stdout)。\n"
        "4. **不要** 在 `main` 區塊中硬編碼 (hard-code) 任何範例輸入或輸出。\n"
    ]

    if json_tests: # json_tests is List[List[str, str]]
        code_prompt_lines.append("\n以下是幾個範例，展示了程式執行時**應該**如何處理輸入和輸出（你的程式碼將透過 `stdin` 接收這些輸入）：\n")
        for i, (inp, out) in enumerate(json_tests):
            inp_repr = repr(str(inp)) # 確保是字串
            out_repr = repr(str(out)) # 確保是字串
            code_prompt_lines.append(f"--- 範例 {i+1} ---")
            code_prompt_lines.append(f"若 stdin 輸入為: {inp_repr}")
            code_prompt_lines.append(f"則 stdout 輸出應為: {out_repr}")
        code_prompt_lines.append("\n再次強調：你的 `main` 程式碼不應該包含這些範例，它應該是通用的，能從 `stdin` 讀取任何合法的輸入。\n")
    else:
        code_prompt_lines.append("由於沒有提供範例，請確保程式碼結構完整，包含 `if __name__ == \"__main__\":` 區塊並能從 `stdin` 讀取數據。\n")

    code_prompt_lines.append("⚠️ **重要**：請僅輸出一個 Python 程式碼區塊 ```python ... ```，絕對不要輸出任何額外文字或解釋。")
    return "".join(code_prompt_lines)

def build_fix_code_prompt(user_need: str, virtual_code: str, json_tests: Optional[List[Tuple[str, str]]], history: List[str], current_code: str, modification_request: str) -> str:
    """
    (MODIFIED) 建立一個用於「互動式修改」的提示。
    這會包含歷史紀錄、當前程式碼和修改需求。
    """
    code_prompt_lines = [
        "用繁體中文回答。\n你是程式碼生成助理。\n任務：依據使用者需求、虛擬碼、範例，產生正確可執行的 Python 程式碼，並加上白話註解。\n",
        f"原始需求：\n{user_need}\n",
        f"虛擬碼：\n{virtual_code}\n",
        f"歷史紀錄：\n{' -> '.join(history)}\n",
        f"--- 當前程式碼 (有問題或待修改) ---\n"
        f"```python\n{current_code}```\n"
        f"--- !! 新增修改需求 !! ---\n"
        f"{modification_request}\n\n",
        "--- 程式碼要求 (務必遵守) ---\n",
        "生成的程式碼必須包含一個 `if __name__ == \"__main__\":` 區塊。\n",
        "這個 `main` 區塊必須：\n"
        "1. 從標準輸入 (stdin) 讀取解決問題所需的所有數據。\n"
        "2. 處理這些數據。\n"
        "3. 將最終答案打印 (print) 到標準輸出 (stdout)。\n"
        "4. **不要** 在 `main` 區塊中硬編碼 (hard-code) 任何範例輸入或輸出。\n"
    ]

    if json_tests: # 重新使用先前生成的測資
        code_prompt_lines.append("\n以下是幾個範例，展示了程式執行時**應該**如何處理輸入和輸出（你的程式碼將透過 `stdin` 接收這些輸入）：\n")
        for i, (inp, out) in enumerate(json_tests):
            inp_repr = repr(str(inp))
            out_repr = repr(str(out))
            code_prompt_lines.append(f"--- 範例 {i+1} ---")
            code_prompt_lines.append(f"若 stdin 輸入為: {inp_repr}")
            code_prompt_lines.append(f"則 stdout 輸出應為: {out_repr}")
        code_prompt_lines.append("\n再次強調：你的 `main` 程式碼不應該包含這些範例，它應該是通用的，能從 `stdin` 讀取任何合法的輸入。\n")
    else:
        code_prompt_lines.append("由於沒有提供範例，請確保程式碼結構完整，包含 `if __name__ == \"__main__\":` 區塊並能從 `stdin` 讀取數據。\n")

    code_prompt_lines.append("⚠️ **重要**：請僅輸出一個 Python 程式碼區塊 ```python ... ```，絕對不要輸出任何額外文字或解釋。")
    
    return "".join(code_prompt_lines)

def build_hint_prompt(problem_description: str, user_code: str, error_message: Optional[str] = None) -> str:
    """
    建立一個用於生成程式碼提示的提示。
    """
    prompt_lines = [
        "用繁體中文回答。\n"
        "你是一位專業的程式解題助教。\n"
        "任務：根據使用者提供的題目描述和他們不完整的/錯誤的程式碼，提供一個具體的、有建設性的「提示」，引導他們思考正確的方向。\n",
        "**提示要求**：\n"
        "1.  **不要** 直接給出完整解答或修正後的程式碼。\n"
        "2.  針對程式碼中**最關鍵**的一個問題點提供指導。\n"
        "3.  如果程式碼看起來完全離題，請提示他們重新閱讀題目描述的關鍵部分。\n"
        "4.  如果提供了錯誤訊息，請優先針對錯誤訊息進行解釋和提示。\n"
        "5.  提示應簡短、精確，控制在 2-3 句話內。\n",
        f"--- 題目描述 ---\n{problem_description}\n",
        f"--- 使用者的程式碼 (有問題) ---\n```python\n{user_code}```\n"
    ]
    
    if error_message:
        prompt_lines.append(f"--- 錯誤訊息/執行失敗日誌 ---\n{error_message}\n")
    
    prompt_lines.append("\n請根據上述資料，提供一個簡短的、引導性的提示：")
    
    return "".join(prompt_lines)

def build_specific_explain_prompt(current_code: str, user_query: str) -> str:
    """
    針對使用者對特定程式碼片段的疑問，建立解釋用的 Prompt。
    """
    return (
        f"這是目前的 Python 程式碼:\n```python\n{current_code}\n```\n"
        f"使用者針對這段程式碼有以下具體問題或是想了解的部分:\n{user_query}\n"
        f"請以專業但易懂的方式，用繁體中文為使用者進行解釋。"
    )

# ===================== 正規化測資(omm) =====================
def _ensure_str(x) -> str:
    """確保值為字串（None 轉空字串）"""
    if x is None:
        return ""
    return x if isinstance(x, str) else str(x)

def _ensure_nl(s: str) -> str:
    """確保字串結尾有換行符號"""
    if not s:
        return "\n"
    return s if s.endswith("\n") else s + "\n"

def _normalize_stdin_for_stdin_mode(s: str) -> str:
    """
    若輸入長得像 JSON 陣列字串，轉成適合 stdin 的格式：
      "[2, 3]\n"       → "2\n3\n"
      "[[1,2],[3,4]]"  → "1 2\n3 4\n"
    其他情況則原樣（但保證以單一結尾換行收尾）。
    """
    if s is None:
        return "\n"
    txt = str(s).strip()
    import json
    if txt.startswith("[") and txt.endswith("]"):
        try:
            arr = json.loads(txt)
            def flatten_to_lines(x):
                if isinstance(x, list):
                    # [[1,2],[3,4]] → 多行
                    if x and all(isinstance(e, (list, tuple)) for e in x):
                        return "\n".join(" ".join(str(v) for v in row) for row in x)
                    # [1,2,3] → 每個元素一行 ✅
                    else:
                        return "\n".join(str(v) for v in x)
                return str(x)
            out = flatten_to_lines(arr)
            return out.rstrip("\n") + "\n"
        except Exception:
            pass
    # 非 JSON 陣列 → 保證最後有換行
    return txt if txt.endswith("\n") else (txt + "\n")

def normalize_tests(raw) -> list[dict]:
    """
    將模型回覆的多種格式轉成統一格式：
    [{"input": "...\\n", "output": "...\\n"}, ...]

    支援：
      - [{"input": "...", "output": "..."}]
      - [{"input": "...", "expected": "..."}]
      - [["2 3", "6"], ["10 5", "50"], ...]
      - {"input": "...", "output": "..."} (單一物件)
    """
    if raw is None:
        return []

    # 若是單一 dict → 包裝成 list
    if isinstance(raw, dict):
        raw = [raw]

    # 非 list → 無效
    if not isinstance(raw, list):
        return []

    norm = []
    for item in raw:
        if isinstance(item, dict):
            # input/output 或 input/expected
            if "input" in item and ("output" in item or "expected" in item):
                out_key = "output" if "output" in item else "expected"
                inp = _ensure_nl(_ensure_str(item["input"]))
                inp = _normalize_stdin_for_stdin_mode(inp)  
                out = _ensure_nl(_ensure_str(item[out_key]))
                norm.append({"input": inp, "output": out})
        elif isinstance(item, (list, tuple)) and len(item) == 2:
            inp = _ensure_nl(_ensure_str(item[0]))
            inp = _normalize_stdin_for_stdin_mode(inp)     
            out = _ensure_nl(_ensure_str(item[1]))
            norm.append({"input": inp, "output": out})
        # 其他型別略過
    return norm

def build_cot_test_prompt(user_need: str) -> str:
    """
    [改進版] 測試案例生成 Prompt，引入思維鏈 (CoT) 以提高覆蓋率與準確性。
    參考: arXiv:2504.20357 (強調系統化方法)
    """
    return (
        "用繁體中文回答。\n"
        "你是一位資深的軟體測試架構師。\n"
        "任務：請為以下需求設計一套高覆蓋率的測試案例。請先進行分析，再輸出 JSON。\n\n"
        f"需求描述:\n{user_need}\n\n"
        "**分析步驟 (Thinking Process)**:\n"
        "1. 識別核心功能與預期行為。\n"
        "2. 列出 3 個關鍵的「邊界條件 (Edge Cases)」(例如: 空值、最大最小值、邊界索引)。\n"
        "3. 列出 2 個可能的「異常輸入 (Invalid Inputs)」與預期錯誤處理（若適用）。\n\n"
        "**最終輸出**:\n"
        "請將上述分析轉化為一個 JSON 二維陣列，格式嚴格遵守 `[[輸入, 預期輸出], [輸入, 預期輸出], ...]`。\n"
        "⚠️ JSON 區塊前後請勿包含任何其他文字。\n"
        "```json\n"
    )
def build_mutation_killing_prompt(original_code: str, current_tests_str: str, mutant_info: str) -> str:
    """
    建立 MuTAP 提示詞：要求 AI 生成能殺死特定變異體的測資。
    """
    return f"""
        你是一位軟體測試專家。請幫助我強化測試用例。
        以下是原始程式碼，以及目前的測試輸入(JSON格式)。
        我們發現目前的測試無法檢測出一個潛在的錯誤版本（存活的變異體）。

        【原始程式碼 (Program Under Test)】
        {original_code}

        【目前已通過的測試輸入】
        {current_tests_str}

        【存活的變異體 (錯誤版本資訊)】
        {mutant_info}

        請分析變異體為何能存活，並提供一個**新的測試輸入與預期輸出**，它必須能區分原始代碼與變異體（即在原始代碼通過，但在變異體失敗）。
        請只回傳一個 JSON 格式的列表，包含這個新的測試案例，格式為： `[[input_string, expected_output_string]]`
        """
def build_ga_crossover_prompt(user_need: str, parent1: list, parent2: list) -> str:
    """
    [GA] 交配 (Crossover) 提示詞：要求 AI 結合兩個父代測資的特徵。
    """
    return (
        "用繁體中文回答。\n"
        "你是一個測試演化演算法的操作員。\n"
        f"任務：參考以下兩個父代測資，結合它們的特徵（例如：輸入的結構、邊界情況、資料類型），產生一個新的、合法的子代測資，以測試此需求：{user_need}。\n"
        f"父代 1: {json.dumps(parent1, ensure_ascii=False)}\n"
        f"父代 2: {json.dumps(parent2, ensure_ascii=False)}\n"
        "⚠️ 僅輸出一個新的 JSON 測資 `[新輸入, 新預期輸出]`，不要有其他文字。"
    )

def build_ga_mutation_prompt(user_need: str, parent: list) -> str:
    """
    [GA] 突變 (Mutation) 提示詞：要求 AI 對單一測資進行微調以探索鄰近邊界。
    """
    return (
        "用繁體中文回答。\n"
        "你是一個測試演化演算法的操作員。\n"
        f"任務：對以下測資進行「突變」（微調），例如改變數值大小、字串長度、特殊字元或邊界條件，使其能測試到不同的程式路徑，同時仍符合需求：{user_need}。\n"
        f"原始測資: {json.dumps(parent, ensure_ascii=False)}\n"
        "⚠️ 僅輸出突變後的 JSON 測資 `[新輸入, 新預期輸出]`，不要有其他文字。"
    )

def build_mutation_prompt(user_need: str, parent: list) -> str:
    """
    [GA] 突變 (Mutation)：對單一測資進行微小修改以探索新的邊界。
    """
    return (
        "你是一個測試演化演算法的操作員。\n"
        f"任務：對以下測資進行「突變」（微調），例如改變數值大小、字串長度、特殊字元或邊界條件，使其能測試到不同的程式路徑，同時仍符合需求：{user_need}。\n"
        f"原始測資: {json.dumps(parent, ensure_ascii=False)}\n"
        "⚠️ 僅輸出突變後的 JSON 測資 `[新輸入, 新預期輸出]`，不要有其他文字。"
    )

def build_high_confidence_test_prompt(user_need: str) -> str:
    """
    [準確度模式] 要求 AI 僅生成它最有信心的標準測試案例，避免模糊的邊界情況。
    """
    return (
        "用繁體中文回答。\n"
        "你是一位極度謹慎的測試工程師。\n"
        "任務：請為以下需求設計 3~5 組「絕對正確」的標準測試案例 (Happy Path)。\n"
        "**重要要求**：\n"
        "1. **不追求**複雜或極端的邊界情況。\n"
        "2. 只提供你 100% 確定輸入與輸出完全符合需求的例子。\n"
        "3. 如果有任何不確定的地方，請不要包含該測試案例。\n\n"
        f"需求描述:\n{user_need}\n\n"
        "請直接輸出一個 JSON 格式的二維陣列 `[[輸入, 預期輸出], ...]`，不要有任何額外分析文字。"
    )

def build_test_verification_prompt(user_need: str, test_input: any, test_expected: any) -> str:
    """
    [準確度模式] 要求 AI 扮演審查員，驗證單一測資是否正確。
    """
    return (
        "你是一位嚴格的程式需求審查員。\n"
        f"需求原始描述:\n{user_need}\n\n"
        "請審查以下這個測試案例是否「完全正確」符合上述需求：\n"
        f"輸入 (Input): {test_input}\n"
        f"預期輸出 (Expected Output): {test_expected}\n\n"
        "請先進行一步步的推理分析，驗證這個輸入在需求下是否必然得到這個輸出。\n"
        "最後，如果它絕對正確，請在最後一行輸出 'VERDICT: PASS'。\n"
        "如果有任何疑慮或錯誤，請在最後一行輸出 'VERDICT: FAIL'。"
    )