Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$projectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$venvPath = Join-Path $projectRoot '.venv'
$venvPython = Join-Path $venvPath 'Scripts\python.exe'
$venvMarker = Join-Path $venvPath '.project-install.json'
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
    if ($env:PROJECT_PYTHON -and (Test-Path -LiteralPath $env:PROJECT_PYTHON -PathType Leaf)) {
        & $env:PROJECT_PYTHON -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' 2>$null
        if ($LASTEXITCODE -eq 0) {
            return @{ Name = $env:PROJECT_PYTHON; Args = @() }
        }
    }
    $candidates = @(
        @{ Name = 'py'; Args = @('-3') },
        @{ Name = 'python'; Args = @() }
    )
    foreach ($candidate in $candidates) {
        $command = Get-Command $candidate.Name -ErrorAction SilentlyContinue
        if ($null -eq $command) { continue }
        try {
            $arguments = @($candidate.Args)
            & $command.Source @arguments -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' 2>$null
            if ($LASTEXITCODE -eq 0) {
                return $candidate
            }
        } catch {
            continue
        }
    }
    throw '找不到 Python 3.10 以上版本。請先安裝 Python，重新開啟 PowerShell 後再執行。'
}

function Test-CurrentVenv {
    if (-not (Test-Path -LiteralPath $venvPython -PathType Leaf) -or
        -not (Test-Path -LiteralPath $venvMarker -PathType Leaf)) { return $false }
    try {
        $marker = Get-Content -LiteralPath $venvMarker -Raw -Encoding UTF8 | ConvertFrom-Json
        if ($marker.projectRoot -ne $projectRoot -or
            $marker.machine -ne [Environment]::MachineName) { return $false }
        & $venvPython -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)'
        return $LASTEXITCODE -eq 0
    } catch {
        return $false
    }
}

function Assert-ProjectVenvPath([string]$path) {
    $rootFull = [IO.Path]::GetFullPath($projectRoot).TrimEnd('\')
    $parentFull = [IO.Path]::GetDirectoryName([IO.Path]::GetFullPath($path)).TrimEnd('\')
    if (-not [string]::Equals($rootFull, $parentFull, [StringComparison]::OrdinalIgnoreCase)) {
        throw '虛擬環境路徑不在專案根目錄，已停止移動或清理。'
    }
}

Set-Location -LiteralPath $projectRoot
Write-Host "專案位置：$projectRoot"

$rebuild = -not (Test-CurrentVenv)
$backupPath = $null
if ($rebuild -and (Test-Path -LiteralPath $venvPath)) {
    Assert-ProjectVenvPath $venvPath
    $backupPath = Join-Path $projectRoot ".venv.backup-$PID"
    Assert-ProjectVenvPath $backupPath
    if (Test-Path -LiteralPath $backupPath) { throw "暫存資料夾已存在：$backupPath" }
    Write-Host '偵測到從其他電腦或路徑複製的 .venv，正在重新建立...'
    Move-Item -LiteralPath $venvPath -Destination $backupPath
}

try {
    if ($rebuild) {
        $python = Find-Python
        Write-Host '正在建立專案專用的 Python 環境...'
        $arguments = @($python.Args)
        & $python.Name @arguments -m venv $venvPath
        Assert-LastCommandSucceeded '建立虛擬環境'
    }

    & $venvPython -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)'
    Assert-LastCommandSucceeded '檢查虛擬環境的 Python 版本（需要 3.10 以上）'

    Write-Host '正在安裝專案套件...'
    & $venvPython -m pip install -r $requirements
    Assert-LastCommandSucceeded '安裝套件'

    & $venvPython -c 'import selenium, webdriver_manager, requests, lxml, openpyxl, PIL'
    Assert-LastCommandSucceeded '檢查套件'

    @{ projectRoot = $projectRoot; machine = [Environment]::MachineName } |
        ConvertTo-Json | Set-Content -LiteralPath $venvMarker -Encoding UTF8
} catch {
    if ($backupPath) {
        Assert-ProjectVenvPath $venvPath
        if (Test-Path -LiteralPath $venvPath) { Remove-Item -LiteralPath $venvPath -Recurse -Force }
        Move-Item -LiteralPath $backupPath -Destination $venvPath
        Write-Warning '環境重建失敗；已還原原本的 .venv。'
    }
    throw
}
if ($backupPath) {
    Assert-ProjectVenvPath $backupPath
    Remove-Item -LiteralPath $backupPath -Recurse -Force
}

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

$tesseractPaths = @()
foreach ($basePath in @($env:ProgramFiles, ${env:ProgramFiles(x86)})) {
    if ($basePath) {
        $tesseractPaths += Join-Path $basePath 'Tesseract-OCR\tesseract.exe'
    }
}
if (-not (Get-Command tesseract -ErrorAction SilentlyContinue) -and
    @($tesseractPaths | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf }).Count -eq 0 -and
    -not ($env:TESSERACT_CMD -and (Test-Path -LiteralPath $env:TESSERACT_CMD -PathType Leaf))) {
    Write-Warning '未找到 Tesseract；自動辨識驗證碼需要安裝 Tesseract。可執行 winget install --id UB-Mannheim.TesseractOCR --exact 安裝。'
}

Write-Host '環境安裝完成。可執行：'
Write-Host '.\.venv\Scripts\python.exe -m 圖書館.檢測功能.網路書店推薦'
Write-Host '首次執行時 ChromeDriver 可能需要連網下載。'
