# backend/core/model_interface.py
import os
import re
import time
import requests
import subprocess
from core.io_utils import ThinkingDots
from typing import List, Optional, Tuple, Dict, Any, Callable
from core.code_extract import extract_code_block
from core.validators import validate_main_function
import json

from langchain_ollama import OllamaLLM
from langchain_core.prompts import ChatPromptTemplate, PromptTemplate, FewShotPromptTemplate
from langchain_community.chat_message_histories import ChatMessageHistory
from langchain_core.runnables.history import RunnableWithMessageHistory
from langchain_core.output_parsers import PydanticOutputParser, JsonOutputParser, StrOutputParser
from pydantic import BaseModel, Field

# ===== 基本設定 =====
OLLAMA_HOST   = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")
MODEL_NAME    = os.environ.get("MODEL_NAME",  "gpt-oss")         # 原本的完整模型（長文/正式）
FAST_MODEL    = os.environ.get("FAST_MODEL",  MODEL_NAME)        # 快速模型
KEEP_ALIVE    = os.environ.get("OLLAMA_KEEP_ALIVE", "5m")        # 預熱時間
# 快速路徑的生成上限與逾時（秒）
FAST_NUM_PREDICT = int(os.getenv("LLM_FAST_NUM_PREDICT", "160")) # 典型錯誤解釋 2~4 句
FAST_TIMEOUT_SEC = int(os.getenv("LLM_FAST_TIMEOUT", "12"))      # 逾時就放棄

# ===================== 1. 定義測資的預期結構 (Pydantic) =====================
class TestCase(BaseModel):
    input: Any = Field(description="輸入參數。多參數請用陣列 [arg1, arg2]。")
    output: Any = Field(description="預期的正確輸出結果。")
    type: str = Field(description="測資分類：Normal, Edge, Exception, MutationKiller", default="Normal")
    note: str = Field(description="測試目的說明", default="")

class TestSuite(BaseModel):
    # Chain of Thought 核心：強制模型在生成 cases 前先輸出 reasoning
    reasoning: str = Field(description="請先在此欄位描述你的測試策略：你考慮了哪些邊界情況(Edge Cases)？為什麼選擇這些範例？")
    cases: List[TestCase] = Field(description="包含 5 到 10 筆具代表性的測試資料列表。")

# ===================== 2. 定義 Few-Shot 範例 =====================
few_shot_examples = [
    {
        "user_need": "寫一個函式 twoSum(nums, target)，回傳陣列中兩個數字相加等於 target 的索引。",
        "output": """
{{
    "reasoning": "此題需要測試基本功能，並考慮邊界情況：1. 答案在陣列開頭或結尾。 2. 陣列中包含負數或零。 3. 確保不會重複使用同一個元素(例如 [3,3] target 6 應回傳 [0,1] 而非 [0,0])。",
    "cases": [
        {{"input": [[2, 7, 11, 15], 9], "output": [0, 1]}},
        {{"input": [[3, 2, 4], 6], "output": [1, 2]}},
        {{"input": [[3, 3], 6], "output": [0, 1]}},
        {{"input": [[-1, -2, -3, -4, -5], -8], "output": [2, 4]}},
        {{"input": [[0, 4, 3, 0], 0], "output": [0, 3]}}
    ]
}}
"""
    },
    {
        "user_need": "反轉一個字串。",
        "output": """
{{
    "reasoning": "基本字串操作。測試策略應包含：1. 一般英文字串。 2. 空字串(Empty String)的邊界測試。 3. 只有一個字元的字串。 4. 包含空白、特殊符號或中文的字串，確保編碼處理正確。",
    "cases": [
        {{"input": "hello", "output": "olleh"}},
        {{"input": "", "output": ""}},
        {{"input": "a", "output": "a"}},
        {{"input": "race car", "output": "rac ecar"}},
        {{"input": "你好世界", "output": "界世好你"}}
    ]
}}
"""
    }
]

# ===================== LangChain Helper =====================
def get_ollama_llm(
    model: str = MODEL_NAME,
    temperature: float = 0.2,
    num_predict: Optional[int] = None,
    timeout_sec: Optional[int] = None
) -> OllamaLLM:
    return OllamaLLM(
        base_url=OLLAMA_HOST,
        model=model,
        temperature=temperature,
        top_k=30,
        top_p=0.9,
        repeat_penalty=1.05,
        num_predict=num_predict,
        keep_alive=KEEP_ALIVE,
        request_timeout=timeout_sec if timeout_sec and timeout_sec > 0 else None,
    )

# ===================== 高階介面 =====================
def generate_response(prompt: str, model: str = MODEL_NAME, num_predict: Optional[int] = None, timeout: Optional[int] = None) -> str:
    """通用文字生成 (保持不變以相容舊程式碼)"""
    spinner = ThinkingDots("模型思考中")
    spinner.start()
    try:
        llm = get_ollama_llm(model=model, num_predict=num_predict, timeout_sec=timeout)
        resp = llm.invoke(prompt)
        return resp.strip() if resp else "[警告] 模型回傳空值"
    except Exception as e:
        return f"[模型錯誤] {e}"
    finally:
        spinner.stop()

# ===================== 核心：強健的 JSON 解析器 =====================
def try_parse_json(text: str) -> Optional[Dict[str, Any]]:
    """
    嘗試多層次策略從混雜文字中提取並解析 JSON 物件。
    """
    if not text: return None
    text = text.strip()

    # 策略 1: 假設整段就是合法的 JSON
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # 策略 2: 嘗試提取 Markdown code block 中的內容
    # 使用非貪婪匹配抓取第一個可能的 JSON 區塊
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL | re.IGNORECASE)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    # 策略 3: 暴力法 - 尋找最外層的 {}
    # 這能處理模型在 JSON 前後加上大量廢話的情況
    start_idx = text.find('{')
    end_idx = text.rfind('}')
    if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
        potential_json = text[start_idx : end_idx + 1]
        try:
            return json.loads(potential_json)
        except json.JSONDecodeError:
            pass

    return None

class ChainOfThoughtTestAgent:
    """
    整合 LangChain 的五階段測資生成與驗證代理人。
    - Module A: CoT 需求分析
    - Module B: 結構化測資生成
    - Module C: 執行介面 (透過 callback)
    - Module D: 結果反饋與修正
    - Module E: 變異測試 (Mutation Testing)
    """
    def __init__(self, model_name=MODEL_NAME):
        self.llm = get_ollama_llm(model=model_name, temperature=0.2)
        self.memory = ChatMessageHistory()

    def _get_analysis_chain(self):
        """Agent A: 需求分析與邏輯拆解"""
        prompt = PromptTemplate(
            template="""
            你扮演 **Agent A：程式碼測試架構師**。
            
            使用者需求：
            {user_need}
            
            請進行 Chain of Thought 邏輯分析：
            1. **I/O 規格**：輸入參數個數、型態；輸出型態。
            2. **邏輯路徑**：正常情況 (Happy Path)。
            3. **邊界與例外**：列出至少 3 種邊界情況 (Edge Cases，如空值、極值、負數)。
            
            請輸出你的分析報告：
            """,
            input_variables=["user_need"]
        )
        return prompt | self.llm | StrOutputParser()

    def _get_generation_chain(self):
        """Agent B: 結構化測資生成"""
        prompt = PromptTemplate(
            template="""
            你扮演 **Agent B：測資工程師**。
            
            參考分析報告：{analysis_result}
            原始需求：{user_need}
            
            任務：生成 5-8 筆 JSON 格式的測試案例。
            
            格式要求 (JSON Array of Objects):
            [
              {{ "input": [參數1, 參數2], "output": 預期結果, "type": "Normal", "note": "基本測試" }},
              {{ "input": [邊界參數], "output": 預期結果, "type": "Edge", "note": "邊界測試" }}
            ]
            
            **注意**：若函式有多個參數，input 必須是包含所有參數的陣列，例如 `[nums, target]`。
            
            請直接回傳 JSON，不要包含 Markdown 標記：
            """,
            input_variables=["user_need", "analysis_result"]
        )
        return prompt | self.llm | StrOutputParser()

    def _get_feedback_chain(self):
        """Agent D: 錯誤分析與反饋"""
        prompt = PromptTemplate(
            template="""
            你扮演 **Agent D：除錯專家**。
            測試執行失敗，請分析原因。
            
            錯誤報告：
            {execution_report}
            
            需求：{user_need}
            
            請分析：
            1. 是程式邏輯錯誤？還是測資預期輸出有誤？
            2. 給出具體的修正建議 (Actionable Advice)。
            """,
            input_variables=["user_need", "execution_report"]
        )
        return prompt | self.llm | StrOutputParser()

    def _get_mutant_generation_chain(self):
        """Agent E: 生成變異體 (Mutants)"""
        prompt = PromptTemplate(
            template="""
            你扮演 **Agent E：變異測試專家**。
            
            請將以下正確的 Python 程式碼修改出 {num_mutants} 個「變異體 (Mutants)」。
            每個變異體包含一個微小的邏輯錯誤 (如 > 改 >=, + 改 -, 忽略邊界等)，用以測試測資的品質。
            
            目標程式碼：
            ```python
            {target_code}
            ```
            
            請回傳 JSON 列表：
            [ {{ "description": "將迴圈範圍減一", "code": "def..." }} ]
            
            只回傳 JSON。
            """,
            input_variables=["target_code", "num_mutants"]
        )
        return prompt | self.llm | StrOutputParser()

    def _get_mutant_killer_chain(self):
        """Agent E: 生成殺手測資"""
        prompt = PromptTemplate(
            template="""
            你扮演 **Agent B+：高階測資工程師**。
            變異測試中，目前的測資無法區分「正確程式碼」與「變異體」。
            
            變異體描述：{mutant_desc}
            
            請設計一個新的測試案例 (JSON)，讓正確程式碼通過，但變異體失敗 (Output 不同)。
            
            格式：[ {{ "input": ..., "output": ..., "type": "MutationKiller", "note": "殺死變異體: {mutant_desc}" }} ]
            """,
            input_variables=["mutant_desc"]
        )
        return prompt | self.llm | StrOutputParser()

    def run_pipeline(self, user_need: str, target_code: Optional[str] = None, execution_callback: Optional[Callable] = None) -> Dict[str, Any]:
        """
        執行完整閉環：分析 -> 生成 -> (執行) -> (反饋/變異測試)
        """
        # 1. Module A: Analysis
        print(f"\n[Agent A] 分析需求中...")
        analysis_res = self._get_analysis_chain().invoke({"user_need": user_need})
        print(f"[Agent A 分析]\n{analysis_res[:200]}...\n")

        # 2. Module B: Generation
        print(f"\n[Agent B] 生成測資中...")
        raw_tests = self._get_generation_chain().invoke({"user_need": user_need, "analysis_result": analysis_res})
        test_cases = try_parse_json(raw_tests) or []
        
        # 確保格式是 List
        if isinstance(test_cases, dict): test_cases = test_cases.get("cases", [])
        if not isinstance(test_cases, list): test_cases = []
        
        # 補全欄位預設值
        for tc in test_cases:
            if "type" not in tc: tc["type"] = "Normal"
            if "note" not in tc: tc["note"] = "Generated case"

        result = {
            "analysis": analysis_res,
            "test_cases": test_cases,
            "feedback": None,
            "mutation_report": None
        }

        # 3. Module C: Execution (若有提供 Callback)
        if execution_callback and target_code and test_cases:
            print(f"\n[Agent C] 執行驗證中...")
            success, report = execution_callback(target_code, test_cases)
            
            if not success:
                # 4. Module D: Feedback
                print(f"\n[Agent D] 測試失敗，偵測到錯誤...")
                feedback = self._get_feedback_chain().invoke({"user_need": user_need, "execution_report": report})
                result["feedback"] = feedback
                print(f"[Agent D 建議]\n{feedback}")
            else:
                # 5. Module E: Mutation Testing
                print(f"[Agent C] 基礎驗證通過！啟動變異測試 (Mutation Testing)...")
                mutation_stats = self._run_mutation(target_code, test_cases, execution_callback)
                result["mutation_report"] = mutation_stats
                
                if mutation_stats.get("new_cases"):
                    print(f"[Agent E] 自動補充了 {len(mutation_stats['new_cases'])} 筆殺手測資。")
                    # 將新測資合併回結果
                    result["test_cases"].extend(mutation_stats["new_cases"])

        return result

    def _run_mutation(self, target_code, current_tests, runner):
        """執行變異測試迴圈"""
        chain = self._get_mutant_generation_chain()
        raw = chain.invoke({"target_code": target_code, "num_mutants": 3})
        mutants = try_parse_json(raw) or []
        
        killed = 0
        new_cases = []
        survivors = []

        for m in mutants:
            # 執行變異體
            # Pass (True) = 變異體存活 (Bad) -> 測資不足
            # Fail (False) = 變異體被殺死 (Good) -> 測資有效
            is_passed, _ = runner(m.get("code", ""), current_tests)
            if not is_passed:
                killed += 1
            else:
                survivors.append(m)
        
        score = (killed / len(mutants)) * 100 if mutants else 0
        print(f"[Agent E] 變異得分: {score:.1f}% ({killed}/{len(mutants)})")

        # 對存活者生成新測資
        if survivors:
            print(f"[Agent E] 針對 {len(survivors)} 個存活變異體生成新測資...")
            killer_chain = self._get_mutant_killer_chain()
            for sm in survivors:
                raw_k = killer_chain.invoke({"mutant_desc": sm.get("description", "unknown mutant")})
                k_cases = try_parse_json(raw_k)
                if isinstance(k_cases, list):
                    for k in k_cases: k["type"] = "MutationKiller"
                    new_cases.extend(k_cases)
        
        return {"score": score, "killed": killed, "total": len(mutants), "new_cases": new_cases}

# ===================== 4. 執行適配器 (關鍵修正) =====================

def leetcode_execution_adapter(code: str, test_cases: List[Dict]) -> Tuple[bool, str]:
    """
    Agent C (實作): 將 JSON 測資轉為 judge_core 可執行的格式。
    ★ 解決 'missing 1 required positional argument' 錯誤的關鍵。
    """
    # 確保引用
    try:
        from core.judge_core import infer_method_name_from_code, validate_leetcode_code
    except ImportError:
        return False, "[系統錯誤] 無法匯入 judge_core 模組。"

    method_name = infer_method_name_from_code(code)
    if not method_name:
        return False, "無法從程式碼中推斷方法名稱 (請定義 class Solution)。"

    formatted_tests = []
    for tc in test_cases:
        inp = tc.get("input")
        exp = tc.get("output")
        
        # [關鍵修正]: 
        # 如果輸入是 List (例如 [nums, target])，必須轉為 Tuple (nums, target)
        # 這樣 judge_core 內部的 func(*args) 才能正確解包為多個參數。
        if isinstance(inp, list):
            args = tuple(inp)
        else:
            # 單一參數的情況
            args = (inp,)
            
        formatted_tests.append((method_name, args, exp))

    # 呼叫 judge_core
    success, log = validate_leetcode_code(
        code=code,
        tests=formatted_tests,
        class_name="Solution"
    )
    
    return success, log


# ===================== 5. 對外介面 =====================

def generate_and_run_tests(user_need: str, code: str) -> Dict[str, Any]:
    """
    供 API 或主程式呼叫的入口函式。
    """
    agent = ChainOfThoughtTestAgent()
    # 傳入 adapter 作為 callback
    result = agent.run_pipeline(user_need, target_code=code, execution_callback=leetcode_execution_adapter)
    return result

def generate_structured_tests(user_need: str, model_name: str = MODEL_NAME) -> List[Dict[str, Any]]:
    """舊介面相容 (只生成不執行)"""
    agent = ChainOfThoughtTestAgent(model_name)
    res = agent.run_pipeline(user_need)
    return res["test_cases"]
def build_virtual_code_prompt(user_need: str) -> str:
    """
    產生結構化虛擬碼 (Virtual Code)。
    採用結構化模板：(1)問題分析 (2)演算法邏輯 (3)邊界條件。
    此 Prompt 引導模型先進行 CoT 推理（分析與邊界考慮），再生成虛擬碼。
    """
    template = (
        "用繁體中文回答。\n"
        "你是一個專業的演算法設計助理。\n"
        "任務：根據使用者的需求，產生一份**結構化**的虛擬碼設計文件。\n"
        "為了確保後續程式碼轉換的精準度，請務必嚴格遵守以下三個固定區段的輸出格式：\n\n"
        "### (1) 問題分析與輸入／輸出定義\n"
        "- **分析**：簡述題目目標，將需求拆解為思考步驟。\n"
        "- **Input**：說明輸入資料的型態與結構。\n"
        "- **Output**：說明預期輸出的結果。\n\n"
        "### (2) 演算法邏輯步驟 (Virtual Code)\n"
        "請使用結構化的虛擬碼描述流程 (包含箭頭 `→` 與縮排)，範例如下：\n"
        "```text\n"
        "Start // 程式開始\n"
        "→ Step 1: 初始化變數... // 說明\n"
        "→ Loop: 針對每一個元素... // 迴圈說明\n"
        "    → Decision: 若符合條件? // 判斷說明\n"
        "        Yes → 執行動作 A\n"
        "        No  → 執行動作 B\n"
        "End // 程式結束\n"
        "```\n\n"
        "### (3) 邊界條件與例外情況處理\n"
        "- 列出潛在的邊界情況 (Edge Cases) (如：空陣列、負數、資料型態錯誤...等)。\n"
        "- 說明針對這些情況的處理邏輯或防禦性程式設計策略。\n\n"
        "---\n"
        "使用者需求：\n{user_need}\n"
        "---\n"
        "請依照上述結構產生完整回應："
    )

    # 使用 LangChain 的 PromptTemplate 實作，確保變數正確注入
    prompt = PromptTemplate(
        input_variables=["user_need"],
        template=template
    )
    
    return prompt.format(user_need=user_need)
def build_code_prompt(user_need: str, virtual_code: Optional[str] = None) -> str:
    """
    Agent 2: 程式碼轉換模組
    將使用者需求 (與 Agent 1 的虛擬碼) 轉換為可執行的 Python 程式碼。
    """
    prompt = (
        "用繁體中文回答。\n"
        "你扮演 **Agent 2：程式碼轉換模組** 的角色。\n"
        "任務：依據使用者需求" + ("與結構化虛擬碼 (Virtual Code)" if virtual_code else "") + "，產生正確可執行的 Python 程式碼。\n\n"
        "⚠️ **重要**：請僅輸出一個 Python 程式碼區塊，絕對不要輸出任何額外文字或解釋。\n"
        "程式碼必須：\n"
        "  1) 定義一個 `def main():` 函式作為程式進入點，\n"
        "  2) 在 `main()` 函式內，**必須包含具體的測試案例程式碼**，展示如何呼叫你定義的函式，並用 `print()` 輸出結果。\n"
        "  3) 在檔案尾端包含 `if __name__ == \"__main__\":\\n    main()` 以便直接執行，\n"
        "  4) 包含必要的白話註解以說明主要步驟。\n\n"
        f"使用者需求:\n{user_need}\n\n"
    )
    
    if virtual_code:
        prompt += f"參考虛擬碼設計:\n{virtual_code}\n\n"

    prompt += "請產生符合上述要求的 Python 程式碼："
    return prompt



def build_test_prompt(need: str) -> str:
    """
    建立請求模型生成測試資料的 Prompt。
    """
    return (
        "你是一個專業的軟體測試工程師。請根據以下需求，生成 5 到 10 筆具代表性的測試資料。\n"
        "請以 JSON 格式陣列回傳，每筆資料包含 `input` 和 `output` 欄位。\n\n"
        "**重要格式說明：**\n"
        "1. 如果目標函式需要 **多個參數**（例如 `twoSum(nums, target)`），請將 `input` 寫成一個 **JSON 陣列**，按順序包含所有參數。\n"
        "   - 正確範例: `{\"input\": [[2, 7, 11, 15], 9], \"output\": [0, 1]}`\n"
        "   - 錯誤範例: `{\"input\": \"[2, 7, 11, 15]\\n9\", ...}` (請勿使用換行來分隔參數)\n"
        "2. 如果目標函式只需 **一個參數**，則 `input` 直接為該值即可。\n"
        "   - 範例: `{\"input\": \"hello\", \"output\": \"olleh\"}`\n\n"
        f"需求說明:\n---\n{need}\n---\n\n"
        "請僅回傳 JSON 格式的測資陣列，例如：\n"
        "[\n"
        "  {\"input\": [[2, 7, 11, 15], 9], \"output\": [0, 1]},\n"
        "  {\"input\": [[3, 2, 4], 6], \"output\": [1, 2]}\n"
        "]"
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
    print("=== 互動式程式碼開發與修正模式 (Agent 迴圈) ===")

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
    virtual_code_content = "" # 用於儲存 Agent 1 的產出
    history = [f"初始需求: {user_need}"]

    # 2. Agent 1: 虛擬碼生成
    print("\n[Agent 1] 啟動虛擬碼生成模組...")
    vc_prompt = build_virtual_code_prompt(user_need)
    virtual_code_content = generate_response(vc_prompt)
    print("\n=== Agent 1 產出 (虛擬碼設計) ===\n")
    print(virtual_code_content)
    
    # 3. Agent 2: 程式碼生成
    print("\n[Agent 2] 啟動程式碼轉換模組...")
    # 將 Agent 1 的產出傳給 Agent 2
    code_prompt = build_code_prompt(user_need, virtual_code=virtual_code_content) 
    code_resp = generate_response(code_prompt)
    current_code = extract_code_block(code_resp)

    if not current_code:
        print("[錯誤] 模型無法生成程式碼，請重試。")
        return

    print("\n=== Agent 2 產出 (Python 程式碼) ===\n")
    print(f"```python\n{current_code}\n```")

    # 4. 進入修正迴圈 (Agent 3 & 4 互動)
    while True:
        print("\n" + "="*40)
        print("請輸入您的下一步操作：")
        print("  - [修改/優化]：輸入需求說明 (Agent 4 介入)")
        print("  - [驗證]：輸入 'VERIFY' (Agent 3 進行測試與分析)")
        print("  - [解釋]：輸入 'EXPLAIN' (Agent 4 進行解釋)")
        print("  - [完成]：輸入 'QUIT'")
        print("="*40)

        user_input = input("您的操作: ").strip()

        if user_input.upper() == "QUIT":
            break

        if user_input.upper() in ("VERIFY", "V"):
            print("\n[Agent 3] 啟動測試驗證模組...")
            success, validation_result = validate_main_function(current_code)
            print("\n=== Agent 3 分析報告 ===\n")
            print(validation_result)
            
            # 若有錯誤，這裡未來可自動呼叫 build_hint_prompt 進行分析

        elif user_input.upper() in ("EXPLAIN", "E"):
            print("\n[Agent 4] 啟動程式碼解釋模組...")
            explain_prompt = build_explain_prompt(user_need, current_code)
            explain_resp = generate_response(explain_prompt)
            print("\n=== Agent 4 解釋 ===\n")
            print(explain_resp)

        else:
            modification_request = user_input
            print(f"\n[Agent 4] 啟動迭代修正模組...")
            
            # 這裡簡化呼叫，若要完整 CoT 流程應使用 build_fix_code_prompt 並傳入 history
            fix_prompt = build_code_prompt(
                f"請根據以下歷史需求與當前程式碼，進行修正：\n"
                f"--- 初始需求 ---\n{user_need}\n"
                f"--- Agent 1 虛擬碼 ---\n{virtual_code_content}\n"
                f"--- 當前程式碼 ---\n```python\n{current_code}\n```\n"
                f"--- 新增修改需求 (Agent 4 Context) ---\n{modification_request}\n"
            )

            fix_resp = generate_response(fix_prompt)
            new_code = extract_code_block(fix_resp)

            if new_code:
                current_code = new_code
                history.append(f"修改: {modification_request}")
                print("\n=== Agent 4 修正後程式碼 ===\n")
                print(f"```python\n{current_code}\n```")
            else:
                print("[警告] 模型無法生成修正後的程式碼。")

    return current_code

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
    Agent 4: 程式碼解釋與迭代建議模組 (修正模式)
    利用共享記憶 (Memory) 與歷史紀錄，進行程式碼的迭代修正。
    """
    code_prompt_lines = [
        "用繁體中文回答。\n",
        "你扮演 **Agent 4：程式碼解釋與迭代建議模組** 的角色。\n",
        "任務：依據歷史互動紀錄、原始需求與新的修改請求，對程式碼進行重構或修正。\n",
        f"原始需求：\n{user_need}\n",
        f"參考虛擬碼：\n{virtual_code}\n",
        f"Context Memory (歷史紀錄)：\n{' -> '.join(history)}\n",
        f"--- 當前程式碼 (待修正) ---\n"
        f"```python\n{current_code}```\n",
        f"--- !! 新增修改請求 (User Input) !! ---\n",
        f"{modification_request}\n\n",
        "--- 程式碼要求 ---\n",
        "生成的程式碼必須包含一個 `if __name__ == \"__main__\":` 區塊，並能從標準輸入 (stdin) 讀取資料（若適用）。\n",
        "⚠️ **重要**：請僅輸出一個 Python 程式碼區塊 ```python ... ```，絕對不要輸出任何額外文字或解釋。"
    ]
    # ... (後續處理 json_tests 的邏輯保持不變)
    

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
    Agent 3: 測試驗證與結果分析模組
    當測試失敗或程式出錯時，提供分析與漸進式提示。
    """
    prompt = (
        "你扮演 **Agent 3：測試驗證與結果分析模組** 的角色。\n"
        "學生正在嘗試解決一個程式題目，但遇到了困難或錯誤。\n"
        "請根據題目描述、學生的程式碼以及（如果有）錯誤訊息，進行邏輯分析，並提供 **漸進式的提示 (Hint)**。\n"
        "**不要直接給出完整答案或程式碼**，引導他們自己找出解決方案。\n\n"
        "題目描述：\n"
        f"---\n{problem_description}\n---\n\n"
        "學生的程式碼：\n"
        f"```python\n{user_code}\n```\n"
    )

    if error_message:
         prompt += f"\n執行/測試錯誤訊息：\n```\n{error_message}\n```\n\n"

    prompt += (
        "\n請提供 3 個層次的提示：\n"
        "1. **思考方向**：點出題目關鍵或可能忽略的邊界條件。\n"
        "2. **演算法建議**：建議適合的資料結構或演算法策略（如：Hash Map, Two Pointers, DP...），並簡述原因。\n"
        "3. **錯誤分析**（如果適用）：指出目前程式碼中潛在的邏輯錯誤或語法問題。\n\n"
        "請用繁體中文，以鼓勵和引導的語氣回答。"
    )
    return prompt

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