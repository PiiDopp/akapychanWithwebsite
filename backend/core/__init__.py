# core/__init__.py
# --- 初始化 core 套件 ---
from importlib import import_module

def safe_import(module_name, names):
    try:
        mod = import_module(module_name, package=__package__)
        globals().update({n: getattr(mod, n) for n in names if hasattr(mod, n)})
    except Exception as e:
        print(f"[警告] 匯入 {module_name} 失敗: {e}")

safe_import(".io_utils", ["ask_input", "ThinkingDots"])
safe_import(".model_interface", ["build_code_prompt", "build_test_prompt", "build_explain_prompt","build_virtual_code_prompt", "generate_response"])
safe_import(".code_extract", ["extract_code_block", "extract_json_block", "parse_tests_from_text", "normalize_tests"])
safe_import(".data_structures", ["ListNode", "TreeNode", "auto_convert_input", "auto_convert_output"])
safe_import(".validators", ["validate_python_code", "validate_main_function"])
safe_import(".test_utils", ["generate_tests"])