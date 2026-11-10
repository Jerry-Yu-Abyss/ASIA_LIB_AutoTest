# LINE 通知

安裝環境後，開啟專案根目錄的 `啟動檢測.pyw`。勾選「完成後傳送 LINE 結果」即可在檢測後傳送摘要與明細；按「只測 LINE 連線」可先發送一則測試訊息，不會執行網站測試。

第一次使用時，在 `config/line.local.json` 填入 `channel_access_token` 與 `user_id`。安裝精靈提供「編輯 LINE 設定」按鈕。預設只傳給設定的 User ID；勾選群發才會傳給官方帳號所有可接收訊息的好友，並使用訊息額度。帳密與 token 請勿公開分享。本機設定檔不納入版本庫。

命令列可在專案根目錄執行：

```powershell
.\.venv\Scripts\python.exe .\LINE通知\run_and_notify.py --send-test
.\.venv\Scripts\python.exe .\LINE通知\run_and_notify.py
.\.venv\Scripts\python.exe .\LINE通知\run_and_notify.py --no-line
```

三個指令分別為測試 LINE 連線、執行全部檢測並傳送結果、只檢測不傳 LINE。完整日誌與逐筆 JSON 報告保存在 `.local/reports/`。LINE 發送程式與訊息格式實作見 [`run_and_notify.py`](run_and_notify.py)。
