import os
import json
from typing import List, Dict, Any

def load_all_json_from_dir(root_dir: str = "../frontend/data/Leetcode") -> List[Dict[str, Any]]:
    """
    遞迴地從指定目錄載入所有 JSON 檔案的內容。

    Args:
        root_dir: 包含 JSON 資料集的根目錄。

    Returns:
        一個包含所有 JSON 內容字典的列表。
    """
    all_data = []
    # 確保路徑存在
    if not os.path.exists(root_dir):
        # 這裡不報錯，僅輸出警告，讓程式碼可以繼續執行。
        print(f"警告：資料目錄 '{root_dir}' 不存在，無法載入 RAG 資料。")
        return []

    # 遞迴遍歷資料夾
    for dirpath, dirnames, filenames in os.walk(root_dir):
        for filename in filenames:
            if filename.endswith(".json"):
                file_path = os.path.join(dirpath, filename)
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = json.load(f)
                        # 為了 RAG 方便識別，在內容中加入來源檔案名
                        if isinstance(content, dict):
                            content['source_file'] = file_path
                        all_data.append(content)
                except Exception as e:
                    print(f"錯誤：無法載入 JSON 檔案 {file_path}: {e}")
    return all_data

def format_data_for_rag(data: List[Dict[str, Any]]) -> str:
    """
    將載入的 JSON 資料格式化為模型可以理解的 RAG 上下文。
    為了避免 Prompt 過長，這裡只取部分關鍵資訊。
    """
    formatted_chunks = []
    
    # 限制只取前 10 個檔案的資料，避免 Prompt 超長
    for item in data[:10]:
        source = item.get('source_file', 'Unknown')
        title = item.get('title', 'No Title')
        
        # 嘗試從 'test_cases' 中取出測資，或其他關鍵數據
        test_cases = item.get('test_cases', 'No test cases provided.')
        
        # 建立一個簡潔的上下文片段
        chunk = (
            f"--- Context Source: {source} (Title: {title}) ---\n"
            f"關鍵數據: {json.dumps(test_cases, ensure_ascii=False, indent=2) if test_cases != 'No test cases provided.' else json.dumps(item, ensure_ascii=False, indent=2)[:500] + '...'}\n"
        )
        formatted_chunks.append(chunk)

    return "\n\n".join(formatted_chunks)

if __name__ == '__main__':
    print("--- 執行 data_loader.py 測試載入 ---")
    data = load_all_json_from_dir() 
    print(f"成功載入 {len(data)} 個檔案。")
    if data:
        rag_context = format_data_for_rag(data)
        print("\n--- RAG 格式化上下文範例 (前 500 字) ---\n")
        print(rag_context[:500] + "...")