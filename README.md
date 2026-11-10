# 亞洲大學圖書館系統自動測試

本專案使用 Python、Selenium 與 Google Chrome，自動檢查亞洲大學圖書館館藏查詢網站的頁面內容與連結。

測試網站：<https://aulib.asia.edu.tw/webpac/search.cfm>

## 目前進度（2026-11-03）

- 已完成：可在 Windows 用 `setup.ps1` 建立專案專用環境；「館藏查詢」四項測試均可用無人值守模式執行；`run_and_notify.py` 一次執行四項並分三則 LINE 回報。
- 已驗證：本機安裝與套件檢查、自動化單元測試均通過；2026-11-03 已實跑四項館藏查詢測試並發送三則 LINE 回報。當次網路書店推薦通過，其餘三項因網站資料有缺少分類號或預設封面而未通過。
- 異常處理：驗證碼改用本機 Tesseract 辨識；三種放大倍率至少兩次一致才送出，失敗時最多更換 5 張圖片。無人值守模式不會卡在人工輸入。
- 排程管理：視窗可設定每日或每週的多個時段，並建立或移除 Windows 工作排程；實際排程需在目標電腦選好時間後儲存。換到另一台電腦仍需個別安裝與驗證。

## 測試項目

`圖書館/檢測功能/` 放可單獨執行的檢測及排錯程式；`圖書館/調用子程式/` 放登入、驗證碼與網頁載入等共用模組，供檢測程式匯入。單獨執行檢測時，請在專案根目錄使用下方的 `python -m` 指令。

- `圖書館/檢測功能/館藏查詢.py`：中文、英文各從 10 個常見詞抽 1 個搜尋，略過電子資源等非印刷品，點開各自第 1、5、10 筆「書目-語言資料,印刷品:單行本」；六筆都能開啟書目詳情頁就算成功，不讀取分類號。
- `圖書館/檢測功能/網路書店推薦.py`：登入後，中英文各抽 1 個詞搜尋網路書店，點開各自第 1、5、10 筆書目；六筆的「推薦」按鈕都載入才算成功。只檢查，不點推薦、不送出資料。
- `圖書館/檢測功能/我的書房.py`：使用測試帳號登入，點擊「我的書房」，確認進入 `shelf_user.cfm` 且仍顯示登入狀態。
- `圖書館/調用子程式/帳號登入.py`：獨立的測試帳號登入模組，只有需要登入的測試才會匯入；一般查詢不會讀取帳號設定。
- `圖書館/檢測功能/驗證碼認證.py`：單獨排查登入驗證碼，保存各次圖片、模型辨識與網站驗證結果；不執行館藏或推薦測試。
- `圖書館/檢測功能/新書輪播.py`：檢查新書封面；若顯示預設圖，會查書目詳情頁的三民書店圖片或連結。三民沒有提供書封來源視為正常；有來源卻缺圖才算失敗。
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

安裝程式會檢查 Python 版本、在專案內建立 `.venv`、依 [`requirements.txt`](requirements.txt) 安裝全部測試與書單工具所需套件，並確認套件可匯入。若缺少 `config/測試帳號.local.json` 或 `config/line.local.json`，它會從範例建立空白設定；若已存在，絕不覆寫。它不會代填帳密或 LINE 金鑰，也不會建立排程。Tesseract 是獨立的 Windows 程式，可用 `winget install --id UB-Mannheim.TesseractOCR --exact` 安裝；安裝程式會檢查是否可用。

安裝後直接用專案內的 Python 執行測試，不需啟用虛擬環境：

```powershell
.\.venv\Scripts\python.exe -m 圖書館.檢測功能.網路書店推薦
```

初次執行時，`webdriver-manager` 會下載與 Chrome 相容的 ChromeDriver，因此仍需網路。若在新電腦找不到 Python 或 Chrome，請先安裝它們並重新開啟 PowerShell，再執行 `setup.ps1`。複製檔案時若不小心包含舊電腦的 `.venv`，請先移走該資料夾後再安裝。

若只想手動安裝套件，可用下列等效指令：

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## 執行測試

### 雙擊開啟檢測視窗

完成前述 `setup.ps1` 安裝後，在檔案總管雙擊 [`啟動檢測.pyw`](啟動檢測.pyw)。視窗中可選「全部」或任一項館藏查詢測試，並勾選是否傳送 LINE 結果、是否群發給所有官方帳號好友、是否顯示瀏覽器操作；按「開始檢測」即可在視窗內查看即時進度。也可按「只測 LINE 連線」發送一則連線測試訊息，不執行網站檢測；若勾選群發，這則測試訊息也會傳給所有好友。「停止檢測」會結束正在執行的測試，「開啟報告資料夾」可查看本機日誌與逐筆 JSON 報告。

視窗預設執行時會顯示 Chrome，完成後發送三則 LINE 結果。首次在新電腦使用前，仍須在本機設定測試帳號與 LINE 憑證，並安裝 Tesseract。若雙擊 `.pyw` 沒有開啟視窗，請確認 Windows 已將 `.pyw` 檔案關聯至 Python（`pythonw.exe`）。

### 在視窗設定自動排程

在「自動排程」區選擇「每日」或「每週」，輸入一個或多個 24 小時制時間，例如 `09:00, 18:30`。每週排程再勾選執行星期；勾選多個星期和多個時間時，每個選定的星期都會在每個選定的時間執行。先在視窗上方選擇檢測項目、LINE 回報與瀏覽器顯示方式，然後按「儲存／更新排程」。之後修改任何選項，都要再按一次儲存才會更新工作排程器。「移除排程」會刪除本專案建立的工作。排程不會自動發送「只測 LINE 連線」訊息。

排程使用電腦的本地時間；請確認 Windows 時區是台北。電腦需開機且設定排程的使用者已登入，測試才會執行。若前一次檢測尚未結束，新一次不會重疊執行；錯過的排程會在工作排程器可用時補跑。排程設定儲存在本機 `config/排程.local.json`，工作名稱是 `AU Library Automated Test`。可在 Windows 工作排程器查看執行記錄；測試報告仍保存在 `.local/reports/`。Windows 若拒絕建立工作，視窗會顯示錯誤訊息。

### Windows CMD 常用指令

開啟 **命令提示字元（CMD）**，先進入專案資料夾。複製到其他電腦時，將路徑改為新電腦的實際位置：

```cmd
cd /d "C:\Users\reso9\Desktop\圖書館系統自動測試"
```

首次安裝或換電腦時執行一次：

```cmd
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\setup.ps1"
```

執行全部四項測試，並將摘要、未通過明細、通過明細分三則傳到個人 LINE：

```cmd
.\.venv\Scripts\python.exe .\run_and_notify.py
```

執行時預設會顯示 Chrome；需要背景執行時加上 `--headless`：

```cmd
.\.venv\Scripts\python.exe .\run_and_notify.py --headless
```

若只想執行其中一項並收到該項的三則 LINE 回報，可加 `--only`：

```cmd
.\.venv\Scripts\python.exe .\run_and_notify.py --only "館藏查詢"
.\.venv\Scripts\python.exe .\run_and_notify.py --only "網路書店推薦"
.\.venv\Scripts\python.exe .\run_and_notify.py --only "我的書房"
.\.venv\Scripts\python.exe .\run_and_notify.py --only "新書輪播"
```

只測 LINE 發送，不執行網站測試：

```cmd
.\.venv\Scripts\python.exe .\run_and_notify.py --send-test
```

執行全部四項測試，但不發送 LINE：

```cmd
.\.venv\Scripts\python.exe .\run_and_notify.py --no-line
```

單獨執行各項測試（顯示 Chrome）：

```cmd
.\.venv\Scripts\python.exe -m 圖書館.檢測功能.館藏查詢
.\.venv\Scripts\python.exe -m 圖書館.檢測功能.網路書店推薦 --captcha-mode tesseract --non-interactive
.\.venv\Scripts\python.exe -m 圖書館.檢測功能.我的書房 --captcha-mode tesseract --non-interactive
.\.venv\Scripts\python.exe -m 圖書館.檢測功能.新書輪播
```

執行全部測試時，每個測試的進度會即時顯示在終端機，並同步保存到 `.local\reports`；逐筆網址也保存在該資料夾的 JSON 報告。上述指令不需要先啟用虛擬環境。

若只要檢查程式本身的單元測試，可執行下列指令；這不會啟動瀏覽器或發送 LINE：

```cmd
.\.venv\Scripts\python.exe ".\tests\test_run_and_notify.py"
```

### 分項說明

在專案根目錄執行下列其中一項，不需啟用虛擬環境。

中英文隨機查詢測試：

```powershell
.\.venv\Scripts\python.exe -m 圖書館.檢測功能.館藏查詢
```

加上 `--seed 123` 可重現相同的抽詞結果；加上 `--headless` 可在背景執行 Chrome。

### 網路書店推薦測試

如果尚未建立帳號設定檔，可由範例複製；以下指令不會覆寫現有設定：

```powershell
if (-not (Test-Path ".\config\測試帳號.local.json")) {
    Copy-Item ".\config\測試帳號.example.json" ".\config\測試帳號.local.json"
}
```

在 `config/測試帳號.local.json` 填入 `username` 和 `password`。範例檔的 `captcha.mode` 是 `tesseract`，自動辨識完全在本機進行，不需要 API 金鑰。既有設定若仍寫著 `gemini`，執行時會自動改走 Tesseract。接著直接執行 Python 檔：

```powershell
.\.venv\Scripts\python.exe -m 圖書館.檢測功能.網路書店推薦
```

程式依本機設定的 `captcha.mode` 選擇驗證碼模式；也可用 `--captcha-mode manual` 或 `--captcha-mode tesseract` 暫時覆寫。手動模式會將圖片存至 `.local/captcha.png`，並在終端機等待輸入。帳密以明文保存在本機 JSON，請勿分享；`*.local.json` 與 `.local/` 已排除於 Git，不會上傳。

自動辨識使用本機 Tesseract。若要在背景開啟 Chrome，可加參數：

```powershell
.\.venv\Scripts\python.exe -m 圖書館.檢測功能.網路書店推薦 --captcha-mode tesseract --headless
```

驗證碼圖片不會傳給外部辨識服務。程式會以 Tesseract 對同一張圖片放大三次辨識；至少兩次取得相同英數結果才送出，否則換圖重試，最多使用 5 張。網站判定驗證碼錯誤，或未確認登入成功且未指出帳密問題時，也會換圖重試。程式會等待圖片載入且尺寸非零後才截圖。第 5 張仍無法辨識時，互動模式會將圖片存至 `.local/captcha.png` 並等待手動輸入；無人值守模式直接回報失敗。手動模式不會自動重試。

中文與英文各有 10 個常見詞，和館藏查詢共用詞庫。可加 `--seed 123` 固定抽詞、`--timeout 240` 延長查詢等待秒數（預設 180）。結果不足 10 筆或任何推薦按鈕未載入，都會列為失敗；結束時輸出包含書名的簡易報告並自動關閉瀏覽器，成功回傳 0、失敗回傳 1。

### 我的書房登入檢測

使用同一份測試帳號設定，登入後點擊頁面上的「我的書房」連結，確認書房頁與「登出」狀態。可單獨執行：

```powershell
.\.venv\Scripts\python.exe -m 圖書館.檢測功能.我的書房 --captcha-mode tesseract --non-interactive
```

### 驗證碼排錯

只測帳號登入與驗證碼，不執行其他檢測，也不發 LINE：

```powershell
.\.venv\Scripts\python.exe -m 圖書館.檢測功能.驗證碼認證 --captcha-mode tesseract
```

每次執行會在 `.local/captcha_debug/` 建立資料夾，保存每張驗證碼圖片及 `驗證碼報告.json`。報告列出 Tesseract 的三次辨識結果、網站是否接受，以及失敗原因；不保存帳號或密碼。需人工核對時可用 `--captcha-mode manual`；Tesseract 五次辨識失敗後若要改由人工輸入，加入 `--allow-manual-fallback`。排錯資料包含驗證碼圖片及辨識結果，分享前請自行檢查。

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

預設只傳給設定的 User ID。要把結果傳給當時所有可接收訊息的官方帳號好友，在指令後加 `--broadcast`；此模式只需要 Channel access token，不需要 User ID：

```cmd
.\.venv\Scripts\python.exe .\run_and_notify.py --broadcast
```

若要先只測群發，使用 `--send-test --broadcast`；這會真的向所有好友發送一則測試訊息。正式檢測則一次群發摘要、未通過明細、通過明細三則。群發會使用官方帳號訊息額度，已封鎖帳號的好友收不到。群發後無法收回訊息，請先確認報告內容適合所有好友閱讀。[LINE 群發說明](https://developers.line.biz/en/docs/messaging-api/sending-messages/)

收到 LINE 測試訊息後，再確認 `config/測試帳號.local.json` 的帳密已填妥，且 Tesseract 已安裝，再執行完整測試並回報：

```powershell
.\.venv\Scripts\python.exe .\run_and_notify.py
```

這會依序執行館藏查詢、網路書店推薦、我的書房及新書輪播四項測試，預設顯示 Chrome 且不等待鍵盤輸入；加 `--headless` 才會在背景執行。「帳號登入.py」是網路書店推薦與我的書房共用的登入模組，不是獨立測試。每個需要登入的項目會各自登入並處理驗證碼，最多嘗試 5 張。LINE 一次收到三則純文字、無表情符號的回報：第一則為四項通過／失敗摘要，第二則為未通過的資料、原因與書名，第三則為通過的資料與書名。四項檢測與 LINE 明細都不讀取或顯示分類號。LINE 不附網址；逐筆網址只保存在本機 JSON 報告。新書輪播測試通過的書目在第三則合併為通過筆數，未通過的書目仍逐筆列出。完整日誌及 JSON 報告留在本機 `.local/reports/`。若其餘明細超過 LINE 單則 5000 字上限，訊息會註明省略筆數，完整內容仍在本機報告。若只想測網站、不發 LINE，可加 `--no-line`。程式結束碼：`0` 表示四項通過且訊息發送成功，`1` 表示有測試失敗但結果已回報，`2` 表示 LINE 設定或發送失敗。

單項失敗不會中止後續檢測；四項結束後才產生完整報告。LINE 設定或發送失敗時，本機完整報告仍會保留。預設時間上限依序為 4、8、8、3 分鐘（登入項目若調高 `--timeout`，上限會跟著增加），可用 `--max-runtime` 覆寫每項上限。逾時時會停止該項的瀏覽器程序，再繼續下一項。為避免對網站連續重試，頁面連線逾時只重載一次。

### 新書輪播測試

新書輪播檢查：

```powershell
.\.venv\Scripts\python.exe -m 圖書館.檢測功能.新書輪播
```

程式會開啟 Chrome、等待頁面載入並在終端機輸出測試報告。若輪播書封沒有圖片或顯示預設圖，會再查該書的館藏詳情頁：沒有三民書店的書封圖片或連結，代表三民未提供來源，視為正常；有三民來源卻未顯示封面，或無法確認來源，則列為異常。完整 JSON 報告會記錄每筆的 `cover_status`。手動模式結束後依畫面提示按 Enter 關閉；加 `--headless` 則不等待輸入。

## 專案結構

```text
圖書館系統自動測試/
├─ README.md
├─ setup.ps1
├─ requirements.txt
├─ run_and_notify.py
├─ 啟動檢測.pyw
├─ tests/
│  └─ test_run_and_notify.py
├─ config/
│  ├─ 測試帳號.example.json
│  ├─ 測試帳號.local.json（僅本機，不上傳）
│  ├─ line.example.json
│  └─ line.local.json（僅本機，不上傳）
├─ 安裝套件/
│  └─ set.txt（舊版簡易安裝指令）
├─ 圖書館/
│  ├─ 檢測功能/
│  │  ├─ 館藏查詢.py
│  │  ├─ 網路書店推薦.py
│  │  ├─ 我的書房.py
│  │  ├─ 新書輪播.py
│  │  └─ 驗證碼認證.py（獨立排錯）
│  └─ 調用子程式/
│     ├─ 帳號登入.py
│     ├─ 本機驗證碼.py
│     ├─ 查詢共用.py
│     └─ 網頁載入.py
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

新書輪播遇到 `Service Unavailable` 時，最多嘗試 3 次，每次間隔 10 秒。若仍無法連線，會回報失敗並繼續產生完整檢測報告。網路書店的驗證碼辨識最多嘗試 5 張。

### 網站連線逾時

若網站載入時發生連線逾時，程式會等待 3 秒後重載一次（含首次載入共 2 次）。仍無法連線時，視窗及 LINE 會回報「圖書館網站連線逾時」。請用一般瀏覽器開啟 <https://aulib.asia.edu.tw/webpac/search.cfm>；若瀏覽器也無法開啟，可稍後再試，或以其他網路確認目前網路到大學網站的連線狀況。

### Tesseract 驗證碼辨識不一致

三次放大辨識若未能兩次確認相同英數結果，程式會換圖，最多嘗試 5 張。若持續無法辨識，互動模式可依 `.local/captcha.png` 手動輸入，或在下次執行時加上 `--captcha-mode manual`；無人值守模式則會結束並回報失敗。

### 想在背景執行 Chrome

「館藏查詢」四個可執行測試皆可加 `--headless`。

## 執行與排程提醒

自動排程會使用專案內的 `.venv\Scripts\python.exe`。`run_and_notify.py` 的本機無人值守測試與個人 LINE 收訊已驗證；直接執行 `網路書店推薦.py` 仍保留人工輸入驗證碼的功能。
