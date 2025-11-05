# akapychan

## 建立虛擬環境
```bash
python3 -m venv <虛擬環境名稱>
# 範例：
python3 -m venv myenv
```

```bash
virtualenv <folder_name>
# 範例：
virtualenv myenv
```


## 啟動虛擬環境
```bash
source <虛擬環境名稱>/bin/activate
# 範例：
source myenv/bin/activate
```


## 退出虛擬環境
```bash
deactivate
```

## 執行程式
```bash
python3 main.py
```

## 安裝套件
```bash
pip install -r requirements.txt
```

## 執行後端
```bash
python -m uvicorn main:app --reload
uvicorn main:app --reload
```
```bash
npm install
npm run dev
```