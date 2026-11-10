@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0install_all.ps1"
if errorlevel 1 (
    echo Installation failed. Review the error above.
    pause
    exit /b 1
)
echo Installation completed.
pause
