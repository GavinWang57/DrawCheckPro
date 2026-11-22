# 產生安裝檔：dist\DrawCheckPro-Setup-<版本>.exe（需要 Inno Setup 6）
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (Get-Process DrawCheckPro -ErrorAction SilentlyContinue) {
  throw "DrawCheckPro 正在執行，請先關閉再封裝。"
}

$iscc = @("$env:ProgramFiles", "${env:ProgramFiles(x86)}", "$env:LOCALAPPDATA\Programs") |
  ForEach-Object { Get-ChildItem $_ -Directory -Filter "Inno Setup *" -ErrorAction SilentlyContinue } |
  Sort-Object Name -Descending |
  ForEach-Object { Join-Path $_.FullName "ISCC.exe" } |
  Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $iscc) {
  throw "找不到 Inno Setup，請先安裝：winget install --id JRSoftware.InnoSetup -e"
}

$version = (Select-String -Path app\main_window.py -Pattern '^VERSION = "(.+)"').Matches[0].Groups[1].Value

# 安裝版用資料夾模式（onedir），啟動時不必每次解壓縮，比單一 exe 快
.\.venv\Scripts\pyinstaller `
  --noconfirm --clean `
  --onedir --windowed `
  --name DrawCheckPro `
  --icon app\resources\app.ico `
  --add-data "app\resources\app_icon.png;app\resources" `
  --exclude-module tkinter `
  --exclude-module pytest `
  --exclude-module PySide6.QtNetwork `
  --exclude-module PySide6.QtQml `
  --exclude-module PySide6.QtQuick `
  --exclude-module PySide6.QtPdf `
  --exclude-module PySide6.QtWebEngineCore `
  main.py
if ($LASTEXITCODE -ne 0) { throw "PyInstaller 失敗" }

& $iscc "/DAppVersion=$version" installer\DrawCheckPro.iss
if ($LASTEXITCODE -ne 0) { throw "Inno Setup 編譯失敗" }

Get-Item "dist\DrawCheckPro-Setup-$version.exe" |
  Select-Object Name, @{n = "MB"; e = { [math]::Round($_.Length / 1MB, 1) } }
