# ------------------------------------------------------------
# judge_core.py
# 多模式判題核心（可被 API / CLI 匯入使用）
# - STDIN 模式：validate_stdin_code
# - LeetCode 模式：validate_leetcode_code
# - 小工具：載題、推參數、推方法、例子轉測資、資料結構轉換與深度比對
# ------------------------------------------------------------

from __future__ import annotations

import sys, os, json, ast, io, contextlib, tempfile, subprocess, importlib.util, time, inspect, textwrap
from dataclasses import dataclass
from typing import Any, Optional, Iterable, List, Dict, Tuple
from collections import Counter
from pathlib import Path

# ========== 通用工具 ==========

def _display_width(s: str) -> int:
    """估算顯示寬度（CJK 字視為 2，其他視為 1）"""
    width = 0
    for ch in s:
        # Unicode 東亞寬度特性: 全形/寬字元為 2
        if ord(ch) >= 0x1100 and (
            0x1100 <= ord(ch) <= 0x115F or
            0x2E80 <= ord(ch) <= 0xA4CF or
            0xAC00 <= ord(ch) <= 0xD7A3 or
            0xF900 <= ord(ch) <= 0xFAFF or
            0xFE10 <= ord(ch) <= 0xFE6F or
            0xFF00 <= ord(ch) <= 0xFF60 or
            0xFFE0 <= ord(ch) <= 0xFFE6
        ):
            width += 2
        else:
            width += 1
    return width

def _pad_label(label: str, width: int = 8) -> str:
    """補足顯示寬度，讓中英文欄位對齊"""
    pad = max(0, width - _display_width(label))
    return label + (" " * pad)

def normalize(s: str) -> str:
    """逐行 trim、去尾端空行，統一換行符。"""
    s = (s or "").replace("\r\n", "\n").replace("\r", "\n")
    lines = [ln.strip() for ln in s.split("\n")]
    while lines and lines[-1] == "":
        lines.pop()
    return "\n".join(lines)

def parse_expected(text: str):
    """盡量把文字轉成結構：JSON -> literal_eval -> 字串"""
    exp = normalize(text)
    try:
        return json.loads(exp)
    except Exception:
        try:
            return ast.literal_eval(exp)
        except Exception:
            return exp

def kv_pairs_from_input(inp_text: str) -> dict[str, Any]:
    """
    解析 key=value 序列；逗號只在外層有效。
    值的解析順序：JSON -> ast.literal_eval -> 原字串。
    若整段是 JSON 物件（如 {"a":1}）直接回傳。
    """
    s = (inp_text or "").strip()
    if not s:
        return {}
    try:
        as_json = json.loads(s)
        if isinstance(as_json, dict):
            return as_json
    except Exception:
        pass

    parts: list[str] = []
    cur: list[str] = []
    depth_round = depth_square = depth_curly = 0
    in_quote: Optional[str] = None
    esc = False

    def flush_part():
        part = "".join(cur).strip()
        if part:
            parts.append(part)
        cur.clear()

    for ch in s:
        if in_quote:
            cur.append(ch)
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == in_quote:
                in_quote = None
            continue
        if ch in ("'", '"'):
            in_quote = ch
            cur.append(ch)
            continue
        if ch == "(":
            depth_round += 1
        elif ch == ")":
            depth_round = max(0, depth_round - 1)
        elif ch == "[":
            depth_square += 1
        elif ch == "]":
            depth_square = max(0, depth_square - 1)
        elif ch == "{":
            depth_curly += 1
        elif ch == "}":
            depth_curly = max(0, depth_curly - 1)
        if ch == "," and depth_round == depth_square == depth_curly == 0:
            flush_part()
        else:
            cur.append(ch)
    flush_part()

    out: dict[str, Any] = {}
    for part in parts:
        if "=" not in part:
            continue
        name, raw = part.split("=", 1)
        name = name.strip()
        raw = raw.strip()
        try:
            val = json.loads(raw)
        except Exception:
            try:
                val = ast.literal_eval(raw)
            except Exception:
                val = raw
        out[name] = val
    return out

# ========== 從使用者程式碼推斷方法名稱 / 參數名稱 ==========

def infer_method_name_from_code(user_code: str) -> Optional[str]:
    """
    從 class Solution 抓方法名；優先順序：solve > main > run > answer > 其他第一個非 dunder。
    找不到 Solution / 方法則回傳 None（可由外部顯式指定 method）
    """
    try:
        tree = ast.parse(user_code)
    except Exception:
        return None
    preferred = ("solve", "main", "run", "answer")
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == "Solution":
            cand_names: List[str] = []
            for b in node.body:
                if isinstance(b, ast.FunctionDef) and not b.name.startswith("__"):
                    cand_names.append(b.name)
            for p in preferred:
                if p in cand_names:
                    return p
            return cand_names[0] if cand_names else None
    return None

def infer_arg_names_from_examples(examples: List[Dict[str, str]]) -> List[str]:
    """
    嘗試從 examples[].input 推出參數名稱：
    - 若是 key=value 形式，取共同 keys。
    - 若是單一字串/數值/JSON 值，推為 ['s']。
    """
    if not examples:
        return []
    parsed: List[Dict[str, Any]] = []
    for t in examples:
        raw_inp = (t.get("input", "") or "").strip()
        d = kv_pairs_from_input(raw_inp)
        if d:
            parsed.append(d)
            continue
        try:
            val = parse_expected(raw_inp)
        except Exception:
            return []
        parsed.append({"s": val})
    common = set(parsed[0].keys())
    for d in parsed[1:]:
        common &= set(d.keys())
    if not common:
        return []
    ordered = [k for k in parsed[0].keys() if k in common]
    return ordered

# ========== 題目 JSON 載入（用絕對路徑） ==========

def _safe_join(base_dir: str, rel_path: str) -> str:
    """把 data_path（可相對或檔名）轉成 base_dir 內安全路徑。"""
    rel = str(rel_path).lstrip("/\\")
    path = Path(base_dir).resolve() / rel
    path = path.resolve()
    base = Path(base_dir).resolve()
    if base not in path.parents and path != base:
        raise PermissionError(f"不允許存取該路徑：{path}")
    return str(path)

def load_problem_cases(
    data_id: str = "",
    practice_idx: int = 0,
    *,
    data_path: Optional[str] = None,
    allowed_bases: Optional[List[str]] = None,   # 保留參數相容性（未使用）
    lessons_dir_env: Optional[str] = None        # 保留參數相容性（未使用）
) -> Dict[str, Any]:
    """
    固定讀取以下兩個絕對路徑：
    - 單元題目: ../frontend/data
    - LeetCode 題目:../frontend/data/Leetcode
    """
    UNIT_BASE = "../frontend/data"
    LEETCODE_BASE = "../frontend/data/Leetcode"

    candidates: List[str] = []

    # 0) 若 data_path 已是絕對路徑且存在，直接用
    if data_path and os.path.isabs(data_path) and os.path.exists(data_path):
        candidates.append(data_path)

    # 1) 若指定 data_path（相對路徑或檔名），優先從這兩個目錄找
    if data_path and not candidates:
        for base in [UNIT_BASE, LEETCODE_BASE]:
            try:
                cand = _safe_join(base, data_path)
                candidates.append(cand)
            except Exception:
                pass

    # 2) 若沒指定 data_path，就以 data_id 猜檔名
    if data_id:
        guesses = [
            os.path.join(UNIT_BASE, f"{data_id}.json"),
            os.path.join(LEETCODE_BASE, f"{data_id}.json"),
        ]
        candidates.extend(guesses)

    # 搜尋
    path = None
    tried: List[str] = []
    for p in candidates:
        ap = os.path.abspath(p)
        tried.append(ap)
        if os.path.exists(ap):
            path = ap
            break

    if path is None:
        raise FileNotFoundError(f"找不到題目檔案。嘗試過：{', '.join(tried)}")

    # 讀 JSON
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    items = data.get("coding_practice")
    if not isinstance(items, list) or not items:
        raise ValueError("題目 JSON 缺少 coding_practice 陣列或為空")
    if not (0 <= practice_idx < len(items)):
        raise IndexError(f"practice_idx 超出範圍（0~{len(items)-1})")

    item = items[practice_idx]
    title = item.get("title", f"題目 {practice_idx}")
    description = item.get("description", "")

    # examples -> tests
    ex = item.get("examples")
    tests: List[Dict[str, str]] = []
    if isinstance(ex, list):
        for e in ex:
            if isinstance(e, dict):
                inp = e.get("input")
                out = e.get("output")
                if inp is not None or out is not None:
                    tests.append({
                        "input": "" if inp is None else (inp if isinstance(inp, str) else json.dumps(inp, ensure_ascii=False)),
                        "expected": "" if out is None else (out if isinstance(out, str) else json.dumps(out, ensure_ascii=False)),
                    })
    elif isinstance(ex, dict):
        tests.append({
            "input": "" if ex.get("input") is None else (ex.get("input") if isinstance(ex.get("input"), str) else json.dumps(ex.get("input"), ensure_ascii=False)),
            "expected": "" if ex.get("output") is None else (ex.get("output") if isinstance(ex.get("output"), str) else json.dumps(ex.get("output"), ensure_ascii=False)),
        })

    if not tests or any(t.get("expected", "") == "" for t in tests):
        raise ValueError("題目 JSON 缺少 examples.output（標準答案）")

    for t in tests:
        t["input"] = str(t["input"])
        t["expected"] = str(t["expected"])

    return {
        "title": title,
        "description": description,
        "tests": tests,
        "force_mode": data.get("force_mode"),
    }

# ========== 資料結構：ListNode / TreeNode（LeetCode 常用） ==========

class ListNode:
    def __init__(self, val: int = 0, next: 'Optional[ListNode]' = None):
        self.val = val
        self.next = next

class TreeNode:
    def __init__(self, val: int = 0, left: 'Optional[TreeNode]' = None, right: 'Optional[TreeNode]' = None):
        self.val = val
        self.left = left
        self.right = right

def list_to_listnode(a: Iterable[int]) -> Optional[ListNode]:
    head = cur = None
    for x in a:
        node = ListNode(x)
        if head is None:
            head = cur = node
        else:
            cur.next = node
            cur = node
    return head

def listnode_to_list(head: Optional[ListNode]) -> list[int]:
    out = []
    cur = head
    while cur:
        out.append(cur.val)
        cur = cur.next
    return out

def list_to_btree(level: Iterable[Optional[int]]) -> Optional[TreeNode]:
    arr = list(level)
    if not arr or arr[0] is None: return None
    nodes = [TreeNode(v) if v is not None else None for v in arr]
    kid = 1
    for node in nodes:
        if node is not None:
            if kid < len(nodes):
                node.left = nodes[kid]; kid += 1
            if kid < len(nodes):
                node.right = nodes[kid]; kid += 1
    return nodes[0]

def btree_to_list(root: Optional[TreeNode]) -> list[Optional[int]]:
    if not root: return []
    q = [root]
    out: list[Optional[int]] = []
    while q:
        node = q.pop(0)
        if node is None:
            out.append(None)
            continue
        out.append(node.val)
        q.append(node.left)
        q.append(node.right)
    while out and out[-1] is None:
        out.pop()
    return out

# ========== 泛用比較器（支援浮點誤差 / 無序 / 遞迴 / ListNode / TreeNode） ==========

def _almost_equal(a: float, b: float, tol: float = 1e-6) -> bool:
    return abs(a - b) <= tol

def _eq_listnode(a: Optional[ListNode], b: Optional[ListNode]) -> bool:
    return listnode_to_list(a) == listnode_to_list(b)

def _eq_btree(a: Optional[TreeNode], b: Optional[TreeNode]) -> bool:
    return btree_to_list(a) == btree_to_list(b)

def deep_compare(got: Any, exp: Any, *, float_tol: float = 1e-6, unordered: bool = False) -> bool:
    if isinstance(got, ListNode) or isinstance(exp, ListNode):
        return isinstance(got, ListNode) and isinstance(exp, ListNode) and _eq_listnode(got, exp)
    if isinstance(got, TreeNode) or isinstance(exp, TreeNode):
        return isinstance(got, TreeNode) and isinstance(exp, TreeNode) and _eq_btree(got, exp)
    if isinstance(got, float) or isinstance(exp, float):
        try:
            return _almost_equal(float(got), float(exp), float_tol)
        except Exception:
            return False
    if isinstance(got, dict) and isinstance(exp, dict):
        if got.keys() != exp.keys(): return False
        return all(deep_compare(got[k], exp[k], float_tol=float_tol, unordered=unordered) for k in got)
    if isinstance(got, (list, tuple)) and isinstance(exp, (list, tuple)):
        if unordered:
            try:
                return Counter(got) == Counter(exp)
            except TypeError:
                if len(got) != len(exp): return False
                used = [False]*len(exp)
                for x in got:
                    hit = False
                    for i, y in enumerate(exp):
                        if not used[i] and deep_compare(x, y, float_tol=float_tol, unordered=False):
                            used[i] = True; hit = True; break
                    if not hit: return False
                return True
        if len(got) != len(exp): return False
        return all(deep_compare(x, y, float_tol=float_tol, unordered=unordered) for x, y in zip(got, exp))
    if isinstance(got, set) and isinstance(exp, set):
        return got == exp
    return got == exp

# ========== 參數轉換規格（LeetCode 模式） ==========

@dataclass
class BuildSpec:
    """描述每個參數要如何建構：raw | listnode | btree"""
    kind: str = "raw"

def _build_arg(arg: Any, spec: Optional[BuildSpec]) -> Any:
    if spec is None or spec.kind == "raw":
        return arg
    if spec.kind == "listnode":
        return list_to_listnode(arg)
    if spec.kind == "btree":
        return list_to_btree(arg)
    raise ValueError(f"Unknown BuildSpec kind: {spec.kind}")

# ========== 1) STDIN 模式 ==========

def validate_stdin_code(code: str, examples: list[dict], *, timeout_sec: int = 5) -> tuple[bool, str]:
    """
    examples: [{ "input": str, "output": str } 或 { "input": str, "expected": str }, ...]
    逐題把 input 餵給程式，用 stdout 與 expected 比對。
    回傳 (ok, log)
    """
    log = io.StringIO()
    with tempfile.NamedTemporaryFile(delete=False, suffix=".py") as tmp:
        tmp.write(code.encode("utf-8")); tmp.flush(); path = tmp.name
    try:
        for idx, ex in enumerate(examples, 1):
            p = subprocess.run(
                [sys.executable, path],
                input=ex.get("input",""),
                text=True,
                capture_output=True,
                timeout=timeout_sec,
                cwd=os.path.dirname(path)
            )
            if p.returncode != 0:
                print(f"[錯誤] 第 {idx} 筆：程式執行失敗", file=log)
                if p.stderr:
                    print(p.stderr[:400], file=log)
                return False, log.getvalue()
            out = normalize(p.stdout)
            # 允許 'output' 或 'expected'
            exp_raw = ex.get("output", ex.get("expected", ""))
            exp = normalize(exp_raw)
            if out != exp:
                print(f"[錯誤] 第 {idx} 筆：輸出不符", file=log)
                print(f"【Input】\n{ex.get('input','')}", file=log)
                print(f"【Your Output】\n{out}", file=log)
                print(f"【Expected】\n{exp}", file=log)
                return False, log.getvalue()
        print("[成功] 所有 STDIN 測資通過 ✅", file=log)
        return True, log.getvalue()
    except subprocess.TimeoutExpired:
        print("[錯誤] 程式執行逾時", file=log)
        return False, log.getvalue()
    finally:
        try: os.unlink(path)
        except: pass

# ========== 2) LeetCode 模式 ==========

def validate_leetcode_code(
    code: str,
    tests: list[tuple[str, tuple, Any]],
    *,
    class_name: str = "Solution",
    per_arg_build: Optional[list[BuildSpec]] = None,
    expect_kind: Optional[str] = None,
    float_tol: float = 1e-6,
    unordered: bool = False,
    user_need: str = ""
) -> tuple[bool, str]:
    """
    逐筆列印測資結果，不提前中斷。
    回傳 (全部通過與否, log)
    """
    log = io.StringIO()
    tmp_path = None

    def _norm_out(g: Any) -> Any:
        if expect_kind == "listnode" and isinstance(g, ListNode):
            return listnode_to_list(g)
        if expect_kind == "btree" and isinstance(g, TreeNode):
            return btree_to_list(g)
        return g

    passed_count = 0

    try:
        # 寫入使用者程式碼到暫存檔
        with tempfile.NamedTemporaryFile(delete=False, suffix=".py") as tmp:
            tmp.write(code.encode("utf-8"))
            tmp_path = tmp.name

        spec = importlib.util.spec_from_file_location("user_solution", tmp_path)
        module = importlib.util.module_from_spec(spec)
        sys.modules["user_solution"] = module
        spec.loader.exec_module(module)

        Solution = getattr(module, class_name, None)
        if not isinstance(Solution, type):
            print(f"[錯誤] 找不到類別 {class_name}", file=log)
            return False, log.getvalue()
        try:
            ins = Solution()
        except TypeError as e:
            print(f"[錯誤] 無法以零參數建立 {class_name} 實例: {e}", file=log)
            return False, log.getvalue()

        t0 = time.perf_counter()

        for i, (method_name, args, expected) in enumerate(tests, 1):
            if not isinstance(args, tuple):
                args = (args,)

            if per_arg_build:
                built_args = tuple(
                    _build_arg(a, per_arg_build[j] if j < len(per_arg_build) else None)
                    for j, a in enumerate(args)
                )
            else:
                built_args = args

            meth = getattr(ins, method_name, None) or getattr(Solution, method_name, None)
            if meth is None:
                print(f"[錯誤] 測試#{i}: 找不到方法 {method_name}", file=log)
                continue

            try:
                got = meth(*built_args)
                got_n = _norm_out(got)
            except Exception as e:
                print(f"[測試#{i}] ❌ 執行例外: {e}", file=log)
                continue

            ok = deep_compare(got_n, expected, float_tol=float_tol, unordered=unordered)
            if ok:
                passed_count += 1
                print(f"[測試#{i}] ✅ 通過", file=log)
            else:
                print(f"[測試#{i}] ❌ 失敗", file=log)

            print(f"  標準輸入: {method_name}{built_args}", file=log)
            print(f"  標準輸出: {expected!r}", file=log)
            print(f"  你的輸出: {got_n!r}", file=log)
            print("", file=log)

        dt = time.perf_counter() - t0
        print(f"=== 測試完成 ({passed_count}/{len(tests)}) ===", file=log)
        if passed_count == len(tests):
            print(f"[成功] 所有測資通過 ✅（{dt:.4f}s）", file=log)
        else:
            print(f"[警告] 部分測資未通過 ❌（{dt:.4f}s）", file=log)
        if user_need:
            print("[結果] 程式邏輯符合需求 ✅", file=log)

        return passed_count == len(tests), log.getvalue()

    except Exception as e:
        print(f"[驗證錯誤] {e}", file=log)
        return False, log.getvalue()
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass

# ---------- examples -> LeetCode 測資 tuples ----------
def build_leetcode_tests_from_examples(
    method: str,
    examples: list[dict],
    arg_names: Optional[list[str]] = None
) -> list[tuple[str, tuple, Any]]:
    tests: list[tuple[str, tuple, Any]] = []
    for ex in examples:
        raw_inp = (ex.get("input") or "").strip()

        # 參數解析：key=value / JSON array / 單值
        kv = kv_pairs_from_input(raw_inp)
        if kv:
            args = tuple(kv[name] for name in (arg_names or kv.keys()))
        else:
            try:
                maybe = json.loads(raw_inp)
            except Exception:
                maybe = None
            if isinstance(maybe, list):
                args = tuple(maybe)
            else:
                args = (parse_expected(raw_inp),)

        # ✅ 同時支援 output / expected
        expected_raw = ex.get("output", ex.get("expected", ""))
        expected = parse_expected(expected_raw)

        tests.append((method, args, expected))
    return tests