# 亞洲大學圖書館系統自動測試

本專案使用 Python、Selenium 與 Google Chrome，自動檢查亞洲大學圖書館館藏查詢網站的頁面內容與連結。

測試網站：<https://aulib.asia.edu.tw/webpac/search.cfm>

## 測試項目

- `館藏查詢/關鍵字查詢.py`：逐一點擊熱門關鍵字，確認搜尋結果頁能取得第 1、5、10 筆書名，並輸出成功／失敗簡易報告。
- `館藏查詢/新書報報.py`：掃描新書區塊，統計書籍資料並檢查封面圖片是否缺漏或使用預設佔位圖。

## 環境需求

- Windows 10 或 Windows 11
- Python 3.10 以上版本
- Google Chrome
- 可連線至網際網路

ChromeDriver 會由 `webdriver-manager` 自動下載及管理，不需要手動安裝。

## 初次設定

在 PowerShell 進入專案資料夾：

```powershell
cd "C:\Users\你的帳號\Desktop\圖書館系統自動測試"
```

建立並啟用 Python 虛擬環境：

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
```

若 PowerShell 阻止執行啟用指令，可只針對目前視窗調整執行原則後再啟用：

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

更新 pip 並安裝必要套件：

```powershell
python -m pip install --upgrade pip
python -m pip install selenium webdriver-manager
```

## 執行測試

啟用虛擬環境後，在專案根目錄執行下列其中一項。

熱門關鍵字連結測試：

```powershell
python ".\館藏查詢\關鍵字查詢.py"
```

新書封面檢查：

```powershell
python ".\館藏查詢\新書報報.py"
```

程式會開啟 Chrome、等待頁面載入並在終端機輸出測試報告。測試結束後，依畫面提示按 Enter 關閉瀏覽器。

## 專案結構

```text
圖書館系統自動測試/
├─ README.md
├─ 安裝套件/
│  └─ 00.txt
└─ 館藏查詢/
   ├─ 關鍵字查詢.py
   ├─ 新書報報.py
   └─ 查詢.txt
```

## 常見問題

### 找不到 `python` 或 `py`

請從 <https://www.python.org/downloads/> 安裝 Python，並在安裝時勾選 **Add Python to PATH**。

### ChromeDriver 建立失敗

確認 Google Chrome 已安裝、網路可正常連線，然後重新執行程式。首次執行時，`webdriver-manager` 需要下載與 Chrome 相容的驅動程式。

### 網站顯示 `Service Unavailable`

兩支程式都會每隔 30 秒自動重試，最多 10 次。如果仍無法連線，請稍後再執行，並確認測試網站可由瀏覽器正常開啟。

### 想在背景執行 Chrome

目前兩支程式在 `main()` 中都以 `open_page(headless=False)` 啟動瀏覽器。如需背景執行，可將參數改成 `headless=True`。

## 結束虛擬環境

```powershell
deactivate
```
