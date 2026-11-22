# 封裝成單一 exe：dist\DrawCheckPro.exe
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

.\.venv\Scripts\pyinstaller `
  --noconfirm --clean `
  --onefile --windowed `
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

Get-Item dist\DrawCheckPro.exe | Select-Object Name, @{n = "MB"; e = { [math]::Round($_.Length / 1MB, 1) } }
