param([switch]$DryRun)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$setupScript = Join-Path $PSScriptRoot 'setup.ps1'

function Find-PythonExecutable {
    $candidates = @(
        @{ Name = 'py'; Args = @('-3.13') },
        @{ Name = 'py'; Args = @('-3') },
        @{ Name = 'python'; Args = @() }
    )
    foreach ($base in @($env:LOCALAPPDATA, $env:ProgramFiles, ${env:ProgramFiles(x86)})) {
        if (-not $base) { continue }
        foreach ($version in @('Python313', 'Python312', 'Python311', 'Python310')) {
            $candidates += @{ Name = (Join-Path $base "Programs\Python\$version\python.exe"); Args = @() }
            $candidates += @{ Name = (Join-Path $base "Python$($version.Substring(6))\python.exe"); Args = @() }
        }
    }
    foreach ($candidate in $candidates) {
        if (-not (Get-Command $candidate.Name -ErrorAction SilentlyContinue)) { continue }
        try {
            $arguments = @($candidate.Args)
            $result = & $candidate.Name @arguments -c 'import sys; print(sys.executable) if sys.version_info >= (3, 10) else sys.exit(1)' 2>$null
            if ($LASTEXITCODE -eq 0 -and $result -and (Test-Path -LiteralPath $result -PathType Leaf)) {
                return [string]$result
            }
        } catch { }
    }
    return $null
}

function Find-Chrome {
    foreach ($base in @($env:ProgramFiles, ${env:ProgramFiles(x86)}, $env:LOCALAPPDATA)) {
        if ($base -and (Test-Path -LiteralPath (Join-Path $base 'Google\Chrome\Application\chrome.exe'))) { return $true }
    }
    return $false
}

function Find-Tesseract {
    if (Get-Command tesseract -ErrorAction SilentlyContinue) { return $true }
    if ($env:TESSERACT_CMD -and (Test-Path -LiteralPath $env:TESSERACT_CMD -PathType Leaf)) { return $true }
    foreach ($base in @($env:ProgramFiles, ${env:ProgramFiles(x86)})) {
        if ($base -and (Test-Path -LiteralPath (Join-Path $base 'Tesseract-OCR\tesseract.exe'))) { return $true }
    }
    return $false
}

function Install-Package([string]$name, [string]$id) {
    Write-Output "正在安裝 $name（$id）..."
    if ($DryRun) { return }
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
        throw "安裝 $name 需要 winget。請先從 Microsoft Store 安裝或更新 App Installer，再重新執行一鍵安裝。"
    }
    & winget install --id $id --exact --source winget --accept-source-agreements --accept-package-agreements --disable-interactivity
    if ($LASTEXITCODE -ne 0) { throw "$name 安裝失敗（winget 結束碼 $LASTEXITCODE）。" }
}

$python = Find-PythonExecutable
if (-not $python) {
    Install-Package 'Python' 'Python.Python.3.13'
    if (-not $DryRun) { $python = Find-PythonExecutable }
}
if (-not $python -and -not $DryRun) { throw '已執行 Python 安裝，但找不到 Python 3.10 以上。請檢查安裝結果後重試。' }

if (-not (Find-Chrome)) {
    Install-Package 'Google Chrome' 'Google.Chrome'
    if (-not $DryRun -and -not (Find-Chrome)) { throw '已執行 Chrome 安裝，但找不到 Chrome。請檢查安裝結果後重試。' }
}

if (-not (Find-Tesseract)) {
    Install-Package 'Tesseract' 'UB-Mannheim.TesseractOCR'
    if (-not $DryRun -and -not (Find-Tesseract)) { throw '已執行 Tesseract 安裝，但找不到 Tesseract。請檢查安裝結果後重試。' }
}

if ($DryRun) {
    Write-Output '預覽完成；未執行安裝。'
    return
}

$env:PROJECT_PYTHON = $python
Write-Output '正在建立或更新專案 Python 環境...'
& $setupScript
Write-Output '一鍵安裝完成。'
