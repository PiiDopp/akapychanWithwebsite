# explain_error.py
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
import subprocess, tempfile, os
from typing import Optional
from core.model_interface import generate_response 

app = FastAPI(title="Code Error Explainer API", version="1.0.0")

class ExplainRequest(BaseModel):
    code: str = Field(..., description="使用者要執行/檢查的 Python 程式碼")
    auto_fix: bool = Field(False, description="是否同時請模型生成修正版程式")

class ExplainResponse(BaseModel):
    ok: bool
    stdout: str = ""
    stderr: str = ""
    explanation: Optional[str] = None
    fixed: Optional[str] = None

def explain_code_error(user_code: str, auto_fix: bool = False) -> ExplainResponse:
    """
    嘗試執行使用者程式碼：
    - 若執行成功，回傳成功訊息。
    - 若失敗，將錯誤訊息送給模型：
        1. 解釋錯誤原因（用繁體中文）
        2. 提出修正建議
        3. 給出一個可能正確的範例程式碼
    """
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8") as tmp:
            tmp.write(user_code)
            tmp_path = tmp.name

        run = subprocess.run(
            ["python3", tmp_path],
            input="",
            capture_output=True,
            text=True,
            timeout=500
        )

        if run.returncode == 0:
            return "[成功] 程式碼可以正常執行 ✅"

        # 執行失敗 → 請模型解釋
        error_msg = run.stderr or ""
        explain_prompt = (
            "你是一個 Python 助教，請幫助使用者理解錯誤。\n"
            "請用繁體中文：\n"
            "1. 解釋錯誤原因\n"
            "2. 給出修正方向（不需立即提供完整程式）\n"
            "3. 用簡單易懂的語言回答\n"
            "\n=== 使用者程式碼 ===\n"
            "```python\n" + user_code + "\n```\n"
            "\n=== 錯誤訊息 ===\n"
            "```\n" + error_msg + "\n```\n"
        )
        explanation = generate_response(explain_prompt)

        fixed_code = None
        if auto_fix:
            fix_prompt = (
                "根據以下程式與錯誤訊息，嘗試提供修正版。\n"
                "請用繁體中文簡述修正重點，並附上完整正確程式碼（放在 ```python 區塊內）。\n"
                "\n=== 使用者程式碼 ===\n"
                "```python\n" + user_code + "```\n"
                "\n=== 錯誤訊息 ===\n"
                "```\n" + error_msg + "\n```\n"
            )
            fixed_code = generate_response(fix_prompt)

        return ExplainResponse(
            ok=False,
            stdout=run.stdout or "",
            stderr=error_msg,
            explanation=explanation,
            fixed=fixed_code
        )

    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=408, detail="執行逾時（> 10 秒）")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"內部錯誤：{e}")
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try: os.remove(tmp_path)
            except: pass

@app.post("/explain", response_model=ExplainResponse)
def explain(req: ExplainRequest):
    # FastAPI 對同步 def 會自動丟到 threadpool，適合你目前的 blocking subprocess.run
    return explain_code_error(req.code, auto_fix=req.auto_fix)
