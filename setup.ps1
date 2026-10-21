Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$venvPath = Join-Path $projectRoot '.venv'
$venvPython = Join-Path $venvPath 'Scripts\python.exe'
$requirements = Join-Path $projectRoot 'requirements.txt'
$exampleConfig = Join-Path $projectRoot 'config\測試帳號.example.json'
$localConfig = Join-Path $projectRoot 'config\測試帳號.local.json'
$lineExample = Join-Path $projectRoot 'config\line.example.json'
$lineConfig = Join-Path $projectRoot 'config\line.local.json'

function Assert-LastCommandSucceeded([string]$description) {
    if ($LASTEXITCODE -ne 0) {
        throw "$description 失敗（結束碼 $LASTEXITCODE）。"
    }
}

function Find-Python {
    $candidates = @(
        @{ Name = 'py'; Args = @('-3') },
        @{ Name = 'python'; Args = @() }
    )
    foreach ($candidate in $candidates) {
        $command = Get-Command $candidate.Name -ErrorAction SilentlyContinue
        if ($null -eq $command) { continue }
        try {
            & $command.Source @($candidate.Args) -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' 2>$null
            if ($LASTEXITCODE -eq 0) {
                return $candidate
            }
        } catch {
            continue
        }
    }
    throw '找不到 Python 3.10 以上版本。請先安裝 Python，重新開啟 PowerShell 後再執行。'
}

Set-Location -LiteralPath $projectRoot
Write-Host "專案位置：$projectRoot"

if (-not (Test-Path -LiteralPath $venvPython -PathType Leaf)) {
    if (Test-Path -LiteralPath $venvPath) {
        throw '已存在 .venv，但找不到其中的 Python。請先自行移走損壞的 .venv，再重新執行。'
    }
    $python = Find-Python
    Write-Host '正在建立專案專用的 Python 環境...'
    & $python.Name @($python.Args) -m venv $venvPath
    Assert-LastCommandSucceeded '建立虛擬環境'
}

& $venvPython -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)'
Assert-LastCommandSucceeded '檢查虛擬環境的 Python 版本（需要 3.10 以上）'

Write-Host '正在安裝專案套件...'
& $venvPython -m pip install -r $requirements
Assert-LastCommandSucceeded '安裝套件'

& $venvPython -c 'import selenium, webdriver_manager, requests, lxml, openpyxl'
Assert-LastCommandSucceeded '檢查套件'

if (-not (Test-Path -LiteralPath $localConfig -PathType Leaf)) {
    Copy-Item -LiteralPath $exampleConfig -Destination $localConfig
    Write-Host '已建立空白帳號設定：config\測試帳號.local.json；請自行填入資料。'
} else {
    Write-Host '保留既有帳號設定：config\測試帳號.local.json（未覆寫）。'
}

if (-not (Test-Path -LiteralPath $lineConfig -PathType Leaf)) {
    Copy-Item -LiteralPath $lineExample -Destination $lineConfig
    Write-Host '已建立空白 LINE 設定：config\line.local.json；請自行填入 token 與 User ID。'
} else {
    Write-Host '保留既有 LINE 設定：config\line.local.json（未覆寫）。'
}

$chromePaths = @()
foreach ($basePath in @($env:ProgramFiles, ${env:ProgramFiles(x86)}, $env:LOCALAPPDATA)) {
    if ($basePath) {
        $chromePaths += Join-Path $basePath 'Google\Chrome\Application\chrome.exe'
    }
}
if (@($chromePaths | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf }).Count -eq 0) {
    Write-Warning '未在常見位置找到 Google Chrome；執行網頁測試前請確認已安裝 Chrome。'
}

Write-Host '環境安裝完成。可執行：'
Write-Host '.\.venv\Scripts\python.exe ".\館藏查詢\網路書店推薦.py"'
Write-Host '首次執行時 ChromeDriver 可能需要連網下載。'
