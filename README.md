# 亞洲大學圖書館系統自動測試

這個專案使用 Chrome 自動檢查館藏查詢、網路書店推薦、我的書房與新書輪播。可以手動執行、傳送 LINE 結果，或在 Windows 設定自動排程。

## 新電腦安裝

適用 Windows 10／11。可將整個專案資料夾複製到隨身碟，再複製到新電腦的任意位置。安裝程式會辨識並重建從舊電腦或舊路徑帶來的 `.venv`，不需手動清理。

1. 在檔案總管雙擊 **`環境設置/開啟安裝精靈.cmd`**；若要直接用命令視窗安裝，可雙擊 **`環境設置/一鍵安裝.cmd`**。
2. 若使用安裝精靈，按 **「一鍵安裝／更新」**；命令視窗版會直接開始。兩種入口都會透過 Windows `winget` 安裝缺少的 Python、Google Chrome 和 Tesseract，再建立專案環境。若 Windows 要求授權，請依畫面操作。
3. 按 **「編輯測試帳號」**，填入圖書館測試帳號與密碼。需要 LINE 回報時，再按 **「編輯 LINE 設定」**，填入 Channel access token 與 User ID。
4. 按 **「開啟檢測視窗」**。第一次可先取消「完成後傳送 LINE 結果」，選擇「館藏查詢」試跑。確認 LINE 設定後，可按「只測 LINE 連線」。

安裝精靈會呼叫 [`環境設置/install_all.ps1`](環境設置/install_all.ps1)，再由 [`setup.ps1`](環境設置/setup.ps1) 建立專案環境。想知道安裝命令與套件清單，可閱讀腳本及 [`requirements.txt`](requirements.txt)。若要用命令列執行相同的一鍵安裝，在專案根目錄執行：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\環境設置\install_all.ps1
```

安裝腳本會為目前電腦與專案位置建立 `.venv`，並在缺少時建立本機設定檔；不會覆寫已存在的帳號與 LINE 設定。首次測試需要連網下載相容的 ChromeDriver。

若安裝後又把專案移到其他磁碟或資料夾，請在新位置重跑「一鍵安裝」。自動排程會記錄執行檔的絕對路徑；移轉電腦或更改資料夾位置後，請在檢測視窗重新按「儲存／更新排程」。

## 日常使用

- **檢測視窗**：雙擊 [`啟動檢測.pyw`](啟動檢測.pyw)，選擇測試項目、LINE 回報及是否顯示瀏覽器，再按「開始檢測」。
- **自動排程**：在檢測視窗設定每日或每週的時間後，按「儲存／更新排程」。換電腦需重新儲存排程；操作說明見 [`排程設置/README.md`](排程設置/README.md)。
- **命令列執行全部測試**：`.\.venv\Scripts\python.exe .\LINE通知\run_and_notify.py`；不傳 LINE 時加 `--no-line`，背景執行時加 `--headless`。LINE 設定與回報方式見 [`LINE通知/README.md`](LINE通知/README.md)。
- **報告**：每次檢測的日誌與 JSON 報告存於 `.local/reports/`。
- **分類號抓取工具**：參閱 [`個人化書單分類號抓取/README.md`](個人化書單分類號抓取/README.md)。

帳號與 LINE 設定只保存在本機的 `config/*.local.json`，請勿公開分享。LINE 群發會傳給官方帳號的所有可接收訊息好友，請在檢測視窗明確勾選後使用。

## 資料夾分級

```text
圖書館系統自動測試/
├─ README.md                   專案入口與使用說明
├─ 啟動檢測.pyw                日常檢測 GUI
├─ requirements.txt            Python 套件清單
├─ 環境設置/                   新電腦安裝入口
│  ├─ 開啟安裝精靈.cmd         雙擊開啟
│  ├─ 一鍵安裝.cmd             直接在命令視窗安裝
│  ├─ installer_gui.ps1        安裝與設定視窗
│  ├─ install_all.ps1          一鍵安裝系統程式及專案環境
│  └─ setup.ps1                實際環境建置腳本
├─ LINE通知/                   測試執行與 LINE 回報
│  ├─ run_and_notify.py        執行各項測試、整理及發送結果
│  └─ README.md                LINE 設定與使用方式
├─ 排程設置/                   Windows 自動排程
│  ├─ schedule_tasks.py        建立、讀取與移除工作排程
│  └─ README.md                排程操作與執行條件
├─ config/                     設定範例與本機設定
│  ├─ 測試帳號.example.json
│  ├─ line.example.json
│  └─ *.local.json             安裝後建立；不納入版本庫
├─ 圖書館/                     網站檢測程式
│  ├─ 環境檢查.py              判斷環境是否屬於目前電腦與位置
│  ├─ 檢測功能/                各項獨立檢測
│  └─ 調用子程式/              登入、驗證碼與網頁共用功能
├─ 個人化書單分類號抓取/     獨立的書單工具及說明
├─ tests/                      程式測試
├─ .venv/                      每台電腦各自建立；不納入版本庫
└─ .local/                     本機報告與排錯資料；不納入版本庫
```

`config/排程.local.json` 也屬本機設定，會在儲存排程後建立。轉移電腦時可安全地轉移必要的 `.local.json`，但排程仍須在新電腦重新建立。
