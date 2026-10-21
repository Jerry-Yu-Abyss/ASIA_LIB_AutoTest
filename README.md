# 亞洲大學圖書館系統自動測試

本專案使用 Python、Selenium 與 Google Chrome，自動檢查亞洲大學圖書館館藏查詢網站的頁面內容與連結。

測試網站：<https://aulib.asia.edu.tw/webpac/search.cfm>

## 目前進度（2026-10-21，尚未完成）

- 已完成：可在 Windows 用 `setup.ps1` 建立專案專用環境；網路書店推薦測試可用無人值守模式執行；`run_and_notify.py` 已備妥 LINE 訊息發送與本機日誌功能。
- 已驗證：本機安裝成功、套件檢查通過、5 項自動化單元測試通過；缺少 LINE 憑證時會安全停止，不會誤發訊息。
- 尚未完成：尚未取得並填入 LINE Channel access token 與個人 User ID，因此**尚未實際送出 LINE 訊息或確認手機收到**；也尚未以 LINE 回報方式完成一次真實網站測試。
- 排程狀態：預定每週一台灣時間 09:00，但**尚未建立或啟用排程**。請先完成下方「本機 LINE 回報測試」的兩階段驗證，再設定排程。

## 測試項目

- `館藏查詢/關鍵字查詢.py`：點擊每個熱門關鍵字，再點開第 1、5、10 筆書目；三筆都取得「索書號(卷期)」中的分類號才算成功。找不到分類號時顯示「查無館藏」。
- `館藏查詢/中英查詢.py`：中文、英文各從 10 個常見詞抽 1 個搜尋，再點開各自第 1、5、10 筆書目；六筆都取得分類號才算成功。
- `館藏查詢/網路書店推薦.py`：登入後，中英文各抽 1 個詞搜尋網路書店，點開各自第 1、5、10 筆書目；六筆的「推薦」按鈕都載入才算成功。只檢查，不點推薦、不送出資料。
- `館藏查詢/帳號登入.py`：獨立的測試帳號登入模組，只有需要登入的測試才會匯入；一般查詢不會讀取帳號設定。
- `館藏查詢/新書報報.py`：檢查新書是否都有封面。沒有缺圖或預設圖片就是成功。
- `個人化書單分類號抓取/抓取分類號.py`：抓取個人化書單各書目的「索書號(卷期)」分類號，填入依日期命名的 Excel。用法見[專用說明](個人化書單分類號抓取/README.md)。

## 環境需求

- Windows 10 或 Windows 11
- Python 3.10 以上版本
- Google Chrome
- 可連線至網際網路

ChromeDriver 會由 `webdriver-manager` 自動下載及管理，不需要手動安裝。

## 複製到另一台 Windows 電腦後安裝

先安裝 Python 3.10 以上與 Google Chrome，並確認新電腦可連網。若新電腦有 Windows `winget`，可先在 PowerShell 執行：

```powershell
winget install --id Python.Python.3.13 --exact --source winget
winget install --id Google.Chrome --exact --source winget
```

安裝 Python 後重新開啟 PowerShell；若沒有 `winget`，可從 [Python 官網](https://www.python.org/downloads/)與 [Chrome 官網](https://www.google.com/chrome/)安裝。把整個專案資料夾複製過去即可；**不要沿用舊電腦的 `.venv` 資料夾**，每台電腦都應重新建立環境。若有複製本機帳密設定檔，請使用安全方式傳輸；也可以在新電腦重新填寫。

在新電腦開啟 PowerShell，進入複製後的專案資料夾（路徑可自行更改）：

```powershell
cd "C:\Users\你的帳號\Desktop\圖書館系統自動測試"
```

執行一次安裝指令：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\setup.ps1
```

安裝程式會檢查 Python 版本、在專案內建立 `.venv`、依 [`requirements.txt`](requirements.txt) 安裝全部測試與書單工具所需套件，並確認套件可匯入。若缺少 `config/測試帳號.local.json` 或 `config/line.local.json`，它會從範例建立空白設定；若已存在，絕不覆寫。它不會代填帳密、Gemini 或 LINE 金鑰，也不會建立排程。

安裝後直接用專案內的 Python 執行測試，不需啟用虛擬環境：

```powershell
.\.venv\Scripts\python.exe ".\館藏查詢\網路書店推薦.py"
```

初次執行時，`webdriver-manager` 會下載與 Chrome 相容的 ChromeDriver，因此仍需網路。若在新電腦找不到 Python 或 Chrome，請先安裝它們並重新開啟 PowerShell，再執行 `setup.ps1`。複製檔案時若不小心包含舊電腦的 `.venv`，請先移走該資料夾後再安裝。

若只想手動安裝套件，可用下列等效指令：

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## 執行測試

在專案根目錄執行下列其中一項，不需啟用虛擬環境。

熱門關鍵字分類號測試：

```powershell
.\.venv\Scripts\python.exe ".\館藏查詢\關鍵字查詢.py"
```

中英文隨機查詢測試：

```powershell
.\.venv\Scripts\python.exe ".\館藏查詢\中英查詢.py"
```

加上 `--seed 123` 可重現相同的抽詞結果；加上 `--headless` 可在背景執行 Chrome。

### 網路書店推薦測試

如果尚未建立帳號設定檔，可由範例複製；以下指令不會覆寫現有設定：

```powershell
if (-not (Test-Path ".\config\測試帳號.local.json")) {
    Copy-Item ".\config\測試帳號.example.json" ".\config\測試帳號.local.json"
}
```

在 `config/測試帳號.local.json` 填入 `username` 和 `password`。範例檔的 `captcha.mode` 是 `manual`；若要自動辨識，改成 `gemini`，並填入自己的 `gemini_api_key` 與可用的 `gemini_model`（例如本專案測試過的 `gemini-3.5-flash-lite`）。金鑰也可改用環境變數 `GEMINI_API_KEY` 提供。接著直接執行 Python 檔：

```powershell
.\.venv\Scripts\python.exe ".\館藏查詢\網路書店推薦.py"
```

程式依本機設定的 `captcha.mode` 選擇驗證碼模式；也可用 `--captcha-mode manual` 或 `--captcha-mode gemini` 暫時覆寫。手動模式會將圖片存至 `.local/captcha.png`，並在終端機等待輸入。帳密以明文保存在本機 JSON，請勿分享；`*.local.json` 與 `.local/` 已排除於 Git，不會上傳。

自動辨識採用[參考文章](https://www.dcard.tw/@myidis__/post/259963369)的 Gemini 圖片辨識方式。若只想在這次執行改用 Gemini，或要在背景開啟 Chrome，可加參數：

```powershell
.\.venv\Scripts\python.exe ".\館藏查詢\網路書店推薦.py" --captcha-mode gemini --headless
```

只會將驗證碼圖片傳給 Google Gemini，不傳帳密。程式會比對兩個模型對同一張圖片的結果；若辨識失敗（例如 HTTP 503）、結果不同，或網站判定驗證碼錯誤，便更換驗證碼再試，最多使用 5 張。第 5 張仍無法辨識時，會將圖片存至 `.local/captcha.png` 並等待手動輸入；若網站拒絕第 5 張，程式會結束並顯示錯誤。手動模式不會自動重試。`captcha.gemini_model` 留空時使用 `gemini-flash-latest`；API 呼叫可能產生費用。

中文與英文各有 10 個常見詞，和中英查詢共用詞庫。可加 `--seed 123` 固定抽詞、`--timeout 240` 延長查詢等待秒數（預設 180）。結果不足 10 筆或任何推薦按鈕未載入，都會列為失敗；結束時輸出包含書名的簡易報告並自動關閉瀏覽器，成功回傳 0、失敗回傳 1。

### 本機 LINE 回報測試

先依 [LINE 官方指南](https://developers.line.biz/en/docs/messaging-api/getting-started/)建立官方帳號，並啟用 Messaging API。用自己的 LINE 將該官方帳號加為好友；可掃描 [Messaging API 頁的 QR code](https://developers.line.biz/en/docs/messaging-api/building-bot/)。在 LINE Developers Console 的頻道「Messaging API」頁取得 Channel access token；在「Basic settings」頁取得自己的 User ID（以 `U` 開頭）。若看不到 User ID，先確認 Business ID 已連結你的 LINE 帳號。[官方 User ID 說明](https://developers.line.biz/en/docs/messaging-api/getting-user-ids/)

安裝時已建立 `config/line.local.json`；用記事本開啟後，在本機填入 token 與 User ID：

```powershell
notepad .\config\line.local.json
```

此檔已排除於 Git；**不要將 token 貼到聊天或提交到版本庫**。也可改以環境變數 `LINE_CHANNEL_ACCESS_TOKEN`、`LINE_USER_ID` 提供，環境變數優先於 JSON。設定後，先只測 LINE 發送，不會啟動瀏覽器：

```powershell
.\.venv\Scripts\python.exe .\run_and_notify.py --send-test
```

收到 LINE 測試訊息後，再確認 `config/測試帳號.local.json` 的帳密、`captcha.mode` 與 Gemini API Key 已填妥，執行完整測試並回報：

```powershell
.\.venv\Scripts\python.exe .\run_and_notify.py
```

這會以無人值守模式開啟背景 Chrome，最多嘗試 5 張驗證碼；辨識仍失敗時會結束並發送失敗摘要，不會卡在人工輸入。LINE 只收到通過／失敗與查詢通過數；詳細紀錄只保存在本機 `.local/reports/`，不會傳送帳密或完整日誌。若暫時只想測網站、不發 LINE，可加 `--no-line`。程式結束碼：`0` 表示網站測試通過且訊息發送成功，`1` 表示網站測試失敗但結果已回報，`2` 表示 LINE 設定或發送失敗。

### 新書封面測試

新書封面檢查：

```powershell
.\.venv\Scripts\python.exe ".\館藏查詢\新書報報.py"
```

程式會開啟 Chrome、等待頁面載入並在終端機輸出測試報告。測試結束後，依畫面提示按 Enter 關閉瀏覽器。

## 專案結構

```text
圖書館系統自動測試/
├─ README.md
├─ setup.ps1
├─ requirements.txt
├─ run_and_notify.py
├─ tests/
│  └─ test_run_and_notify.py
├─ config/
│  ├─ 測試帳號.example.json
│  ├─ 測試帳號.local.json（僅本機，不上傳）
│  ├─ line.example.json
│  └─ line.local.json（僅本機，不上傳）
├─ 安裝套件/
│  └─ set.txt（舊版簡易安裝指令）
├─ 館藏查詢/
│  ├─ 關鍵字查詢.py
│  ├─ 中英查詢.py
│  ├─ 帳號登入.py
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

館藏查詢首頁連線會每隔 30 秒自動重試，最多 10 次。如果仍無法連線，請稍後再執行，並確認測試網站可由瀏覽器正常開啟。網路書店的驗證碼辨識最多嘗試 5 張；其他登入錯誤與搜尋不會自動重試。

### Gemini 回傳 HTTP 503 或驗證碼辨識不一致

程式會自動更換驗證碼，最多嘗試 5 張。若服務持續無法辨識，請依 `.local/captcha.png` 手動輸入；也可以在下次執行時加上 `--captcha-mode manual`。HTTP 503 表示服務暫時無法回應，不能單憑此錯誤判定金鑰無效。

### 想在背景執行 Chrome

中英查詢及網路書店推薦可加上 `--headless`。其他程式可將 `main()` 中的 `open_page(headless=False)` 改為 `headless=True`。

## 執行與排程提醒

自動排程時也要指定 `.venv\Scripts\python.exe`，不要使用其他電腦上的 Python 路徑。`run_and_notify.py` 已備妥無人值守測試與 LINE 回報程式，但**實際送達尚未驗證，也未建立任何排程**；直接執行 `網路書店推薦.py` 仍保留人工輸入驗證碼的功能。
