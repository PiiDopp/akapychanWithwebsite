# explain_user_code.py
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from typing import Optional

from core.model_interface import build_explain_prompt, generate_response

def explain_user_code(user_code: str = "", user_need: str = "") -> str:
    if not (user_code or "").strip():
        return "請提供要解釋的 Python 程式碼。"
    prompt = build_explain_prompt(user_need or "", user_code)
    resp = generate_response(prompt)
    return resp or "[提示] 模型未回傳內容。"

app = FastAPI(title="Python 程式碼解釋 API", version="1.0.0")

class ExplainRequest(BaseModel):
    code: str = Field(..., description="要解釋的 Python 程式碼")
    need: Optional[str] = Field("", description="解釋背景或需求（可留空）")

class ExplainResponse(BaseModel):
    ok: bool
    explanation: str

@app.post("/explain", response_model=ExplainResponse)
def explain(req: ExplainRequest):
    try:
        explanation = explain_user_code(req.code, req.need)
        return ExplainResponse(ok=True, explanation=explanation)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"解釋失敗：{e}")

@app.get("/")
def root():
    return {"status": "ok"}
