# verify_cser_code.py
import tempfile
import subprocess
import os
import re
from textwrap import dedent
from typing import Optional, List

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# ====== 你原本的設定 ======
COMMON_IMPORTS = [
    "from typing import List, Dict, Tuple, Optional, Any"
]

# ====== 可調參數 ======
EXEC_TIMEOUT_SEC = 10
MAX_CAPTURE_BYTES = 50_000  # 避免輸出過長拖垮回應


# ====== util ======
def _maybe_prepend_common_imports(code: str, enable: bool = True) -> str:
    if not enable:
        return code
    imports_to_add: List[str] = []
    for imp in COMMON_IMPORTS:
        # 用 re 精準判斷這行是否已存在
        if not re.search(rf"(?m)^{re.escape(imp)}\s*$", code):
            imports_to_add.append(imp)
    if imports_to_add:
        return "\n".join(imports_to_add) + "\n\n" + code
    return code


def _truncate(s: str, limit: int = MAX_CAPTURE_BYTES) -> str:
    s = s or ""
    if len(s) <= limit:
        return s
    return s[:limit] + f"\n\n...[輸出過長，已截斷 {len(s) - limit} bytes]"


# ====== FastAPI 初始化 ======
app = FastAPI(title="User Code Verify API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],          # 上線建議改白名單
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ====== 請求/回應模型 ======
class VerifyRequest(BaseModel):
    code: str = Field(..., description="使用者的 Python 程式碼")
    auto_common_imports: bool = Field(
        True, description="是否自動補上常用匯入（預設 True）"
    )

class VerifyResponse(BaseModel):
    ok: bool
    returncode: int
    stdout: str
    stderr: str
    message: Optional[str] = ""


# ====== 路由 ======
@app.post("/verify", response_model=VerifyResponse)
def verify(req: VerifyRequest):
    code = (req.code or "").strip()
    if not code:
        raise HTTPException(status_code=400, detail="缺少 code")

    code = dedent(code)
    code = _maybe_prepend_common_imports(code, enable=req.auto_common_imports)

    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8") as tmp:
            tmp.write(code)
            tmp_path = tmp.name

        # 不提供 stdin（若使用者調用 input()，會丟 EOFError；這是預期行為）
        run = subprocess.run(
            ["python3", tmp_path],
            capture_output=True,
            text=True,
            timeout=EXEC_TIMEOUT_SEC,
        )

        stdout = _truncate(run.stdout)
        stderr = _truncate(run.stderr)

        return VerifyResponse(
            ok=(run.returncode == 0),
            returncode=run.returncode,
            stdout=stdout,
            stderr=stderr,
            message=("" if run.returncode == 0 else "程式碼執行失敗"),
        )

    except subprocess.TimeoutExpired:
        return VerifyResponse(
            ok=False,
            returncode=124,
            stdout="",
            stderr=f"執行逾時（>{EXEC_TIMEOUT_SEC}s）。請檢查是否有無限迴圈或等待輸入。",
            message="timeout",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"驗證程式碼時發生例外：{e}")
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass


@app.get("/")
def root():
    return {"status": "ok"}
