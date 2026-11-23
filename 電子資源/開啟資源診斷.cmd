@echo off
setlocal
set "PYTHONW=%~dp0..\.venv\Scripts\pythonw.exe"
if not exist "%PYTHONW%" (
    echo [ERROR] 請先執行環境設置中的安裝精靈，建立 .venv。
    pause
    exit /b 1
)
"%PYTHONW%" "%~dp0資源診斷視窗.pyw"
