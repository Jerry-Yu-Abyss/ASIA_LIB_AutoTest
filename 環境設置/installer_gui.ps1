Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
[System.Windows.Forms.Application]::EnableVisualStyles()

$projectRoot = Split-Path -Parent $PSScriptRoot
$installScript = Join-Path $PSScriptRoot 'install_all.ps1'
$venvPython = Join-Path $projectRoot '.venv\Scripts\python.exe'
$venvMarker = Join-Path $projectRoot '.venv\.project-install.json'
$accountConfig = Join-Path $projectRoot 'config\測試帳號.local.json'
$lineConfig = Join-Path $projectRoot 'config\line.local.json'
$currentJob = $null

function New-Button([string]$caption, [int]$x, [int]$y, [int]$width, $action) {
    $button = New-Object System.Windows.Forms.Button
    $button.Text = $caption
    $button.SetBounds($x, $y, $width, 34)
    $button.Add_Click($action)
    $form.Controls.Add($button)
    return $button
}

function Append-Log([string]$message) {
    $log.AppendText("$message`r`n")
    $log.SelectionStart = $log.TextLength
    $log.ScrollToCaret()
}

function Has-Python {
    foreach ($candidate in @(@('py', '-3'), @('python'))) {
        if (-not (Get-Command $candidate[0] -ErrorAction SilentlyContinue)) { continue }
        try {
            $arguments = @()
            if ($candidate.Count -gt 1) { $arguments += $candidate[1] }
            & $candidate[0] @arguments -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' 2>$null
            if ($LASTEXITCODE -eq 0) { return $true }
        } catch { }
    }
    return $false
}

function Has-Chrome {
    foreach ($base in @($env:ProgramFiles, ${env:ProgramFiles(x86)}, $env:LOCALAPPDATA)) {
        if ($base -and (Test-Path -LiteralPath (Join-Path $base 'Google\Chrome\Application\chrome.exe'))) { return $true }
    }
    return $false
}

function Has-Tesseract {
    if (Get-Command tesseract -ErrorAction SilentlyContinue) { return $true }
    if ($env:TESSERACT_CMD -and (Test-Path -LiteralPath $env:TESSERACT_CMD)) { return $true }
    foreach ($base in @($env:ProgramFiles, ${env:ProgramFiles(x86)})) {
        if ($base -and (Test-Path -LiteralPath (Join-Path $base 'Tesseract-OCR\tesseract.exe'))) { return $true }
    }
    return $false
}

function Has-CurrentEnvironment {
    if (-not (Test-Path -LiteralPath $venvPython -PathType Leaf) -or
        -not (Test-Path -LiteralPath $venvMarker -PathType Leaf)) { return $false }
    try {
        $marker = Get-Content -LiteralPath $venvMarker -Raw -Encoding UTF8 | ConvertFrom-Json
        return $marker.projectRoot -eq $projectRoot -and $marker.machine -eq [Environment]::MachineName
    } catch { return $false }
}

function Refresh-Status {
    $pythonStatus = if ((Has-Python) -or (Has-CurrentEnvironment)) { '已找到' } else { '未找到（需 Python 3.10 以上）' }
    $chromeStatus = if (Has-Chrome) { '已找到' } else { '未找到' }
    $tesseractStatus = if (Has-Tesseract) { '已找到' } else { '未找到（登入驗證碼需要）' }
    $environmentStatus = if (Has-CurrentEnvironment) { '可在此電腦使用' } else { '尚未建立／需要重建' }
    $status.Text = "Python：$pythonStatus`r`nChrome：$chromeStatus`r`nTesseract：$tesseractStatus`r`n專案環境：$environmentStatus"
    $accountButton.Enabled = Test-Path -LiteralPath $accountConfig
    $lineButton.Enabled = Test-Path -LiteralPath $lineConfig
    $testButton.Enabled = Has-CurrentEnvironment
}

$form = New-Object System.Windows.Forms.Form
$form.Text = '圖書館自動測試｜環境設置'
$form.StartPosition = 'CenterScreen'
$form.ClientSize = New-Object System.Drawing.Size(700, 560)
$form.MinimumSize = New-Object System.Drawing.Size(700, 560)
$form.Font = New-Object System.Drawing.Font('Microsoft JhengHei UI', 10)

$title = New-Object System.Windows.Forms.Label
$title.Text = '新電腦安裝精靈'
$title.Font = New-Object System.Drawing.Font('Microsoft JhengHei UI', 16, [System.Drawing.FontStyle]::Bold)
$title.SetBounds(20, 16, 650, 38)
$form.Controls.Add($title)

$hint = New-Object System.Windows.Forms.Label
$hint.Text = '按「一鍵安裝」會自動安裝缺少的 Python、Chrome、Tesseract 與專案套件。完成後填入本機帳號及 LINE 設定。'
$hint.SetBounds(20, 59, 655, 45)
$form.Controls.Add($hint)

$status = New-Object System.Windows.Forms.Label
$status.SetBounds(20, 110, 650, 100)
$form.Controls.Add($status)

$refreshButton = New-Button '重新檢查' 20 215 105 { Refresh-Status }

$installButton = New-Button '一鍵安裝／更新' 20 263 190 {
    if ($null -ne $script:currentJob) { return }
    $script:installButton.Enabled = $false
    Append-Log '開始一鍵安裝；需要系統授權時請依 Windows 提示操作…'
    try {
        $script:currentJob = Start-Job -ScriptBlock {
            param($scriptPath)
            [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
            $env:PYTHONIOENCODING = 'utf-8'
            & $scriptPath *>&1 | ForEach-Object { $_.ToString() }
        } -ArgumentList $script:installScript
        $script:timer.Start()
    } catch {
        $script:installButton.Enabled = $true
        Append-Log ('無法啟動安裝：' + $_.Exception.Message)
    }
}

$accountButton = New-Button '編輯測試帳號' 220 263 145 { Start-Process notepad.exe -ArgumentList ('"' + $script:accountConfig + '"') }
$lineButton = New-Button '編輯 LINE 設定' 375 263 145 { Start-Process notepad.exe -ArgumentList ('"' + $script:lineConfig + '"') }
$testButton = New-Button '開啟檢測視窗' 530 263 145 {
    Start-Process -FilePath (Join-Path $script:projectRoot '.venv\Scripts\pythonw.exe') -ArgumentList ('"' + (Join-Path $script:projectRoot '啟動檢測.pyw') + '"') -WorkingDirectory $script:projectRoot
}

$log = New-Object System.Windows.Forms.TextBox
$log.Multiline = $true
$log.ReadOnly = $true
$log.ScrollBars = 'Vertical'
$log.Font = New-Object System.Drawing.Font('Consolas', 9)
$log.SetBounds(20, 315, 655, 220)
$form.Controls.Add($log)

$timer = New-Object System.Windows.Forms.Timer
$timer.Interval = 300
$timer.Add_Tick({
    if ($null -eq $script:currentJob) { return }
    foreach ($entry in @(Receive-Job -Job $script:currentJob -ErrorAction SilentlyContinue)) {
        if ($null -ne $entry) { Append-Log ([string]$entry) }
    }
    if ($script:currentJob.State -in @('Completed', 'Failed', 'Stopped')) {
        $finished = $script:currentJob
        $script:timer.Stop()
        $script:currentJob = $null
        $script:installButton.Enabled = $true
        if ($finished.State -eq 'Completed') {
            Append-Log '安裝完成。請編輯本機設定，再開啟檢測視窗。'
        } else {
            Append-Log ('安裝失敗：' + [string]$finished.ChildJobs[0].JobStateInfo.Reason)
        }
        Remove-Job -Job $finished -Force
        Refresh-Status
    }
})

$form.Add_FormClosing({
    $script:timer.Stop()
    if ($null -ne $script:currentJob) {
        Stop-Job -Job $script:currentJob
        Remove-Job -Job $script:currentJob -Force
    }
})

Refresh-Status
[void]$form.ShowDialog()
