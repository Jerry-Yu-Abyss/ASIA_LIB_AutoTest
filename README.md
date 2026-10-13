# 亞洲大學圖書館系統自動測試

本專案使用 Python、Selenium 與 Google Chrome，自動檢查亞洲大學圖書館館藏查詢網站的頁面內容與連結。

測試網站：<https://aulib.asia.edu.tw/webpac/search.cfm>

## 測試項目

- `館藏查詢/關鍵字查詢.py`：點擊每個熱門關鍵字，再點開第 1、5、10 筆書目；三筆都取得「索書號(卷期)」中的分類號才算成功。找不到分類號時顯示「查無館藏」。
- `館藏查詢/中英查詢.py`：中文、英文各從 10 個常見詞抽 1 個搜尋，再點開各自第 1、5、10 筆書目；六筆都取得分類號才算成功。
- `館藏查詢/網路書店推薦.py`：登入後，中英文各抽 1 個詞搜尋網路書店，點開各自第 1、5、10 筆書目；六筆的「推薦」按鈕都載入才算成功。只檢查，不點推薦、不送出資料。
- `館藏查詢/新書報報.py`：檢查新書是否都有封面。沒有缺圖或預設圖片就是成功。
- `個人化書單分類號抓取/抓取分類號.py`：抓取個人化書單各書目的「索書號(卷期)」分類號，填入依日期命名的 Excel。用法見[專用說明](個人化書單分類號抓取/README.md)。

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

熱門關鍵字分類號測試：

```powershell
python ".\館藏查詢\關鍵字查詢.py"
```

中英文隨機查詢測試：

```powershell
python ".\館藏查詢\中英查詢.py"
```

加上 `--seed 123` 可重現相同的抽詞結果；加上 `--headless` 可在背景執行 Chrome。

### 網路書店推薦測試

將 `config/測試帳號.example.json` 複製為 `config/測試帳號.local.json`，填入測試帳號與密碼，再執行：

```powershell
python ".\館藏查詢\網路書店推薦.py"
```

預設手動輸入登入驗證碼，可看瀏覽器或 `.local/captcha.png` 圖片。帳密以明文保存在本機 JSON，請勿分享；`*.local.json` 與 `.local/` 已排除於 Git，不會上傳。

自動辨識採用[參考文章](https://www.dcard.tw/@myidis__/post/259963369)的 Gemini 圖片辨識方式。需要自己的 Gemini API Key，填入本機 JSON 的 `captcha.gemini_api_key` 或環境變數 `GEMINI_API_KEY`，再執行：

```powershell
python ".\館藏查詢\網路書店推薦.py" --captcha-mode gemini --headless
```

只會將驗證碼圖片傳給 Google Gemini，不傳帳密。`captcha.gemini_model` 留空時使用 `gemini-flash-latest`；辨識可能失敗或產生 API 費用，登入失敗時不自動重試。沒有 API Key 可繼續使用手動模式。

中文與英文各有 10 個常見詞，和中英查詢共用詞庫。可加 `--seed 123` 固定抽詞、`--timeout 240` 延長查詢等待秒數（預設 180）。結果不足 10 筆或任何推薦按鈕未載入，都會列為失敗；結束時輸出包含書名的簡易報告並自動關閉瀏覽器，成功回傳 0、失敗回傳 1。

### 新書封面測試

新書封面檢查：

```powershell
python ".\館藏查詢\新書報報.py"
```

程式會開啟 Chrome、等待頁面載入並在終端機輸出測試報告。測試結束後，依畫面提示按 Enter 關閉瀏覽器。

## 專案結構

```text
圖書館系統自動測試/
├─ README.md
├─ config/
│  ├─ 測試帳號.example.json
│  └─ 測試帳號.local.json（僅本機，不上傳）
├─ 安裝套件/
│  └─ set.txt
├─ 館藏查詢/
│  ├─ 關鍵字查詢.py
│  ├─ 中英查詢.py
│  ├─ 網路書店推薦.py
│  └─ 新書報報.py
└─ 個人化書單分類號抓取/
   ├─ README.md
   ├─ 抓取分類號.py
   ├─ 待處理/
   └─ 完成/
```

## 常見問題

### 找不到 `python` 或 `py`

請從 <https://www.python.org/downloads/> 安裝 Python，並在安裝時勾選 **Add Python to PATH**。

### ChromeDriver 建立失敗

確認 Google Chrome 已安裝、網路可正常連線，然後重新執行程式。首次執行時，`webdriver-manager` 需要下載與 Chrome 相容的驅動程式。

### 網站顯示 `Service Unavailable`

館藏查詢首頁連線會每隔 30 秒自動重試，最多 10 次。如果仍無法連線，請稍後再執行，並確認測試網站可由瀏覽器正常開啟。網路書店登入與搜尋不會自動重試。

### 想在背景執行 Chrome

中英查詢及網路書店推薦可加上 `--headless`。其他程式可將 `main()` 中的 `open_page(headless=False)` 改為 `headless=True`。

## 結束虛擬環境

```powershell
deactivate
```
