# Builds the distributable: React bundle + PyInstaller onedir exe.
# Run from the repo root:  powershell -File packaging\build.ps1
# Output: backend\dist\AcademyManagement\AcademyManagement.exe

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot

Write-Host "== Building frontend =="
Set-Location (Join-Path $root "frontend")
npm run build
if ($LASTEXITCODE -ne 0) { throw "vite build failed" }

Write-Host "== Building executable =="
Set-Location (Join-Path $root "backend")
& (Join-Path $root ".venv\Scripts\pyinstaller") `
    --noconfirm --noconsole --onedir `
    --name AcademyManagement `
    --add-data "..\frontend\dist;frontend/dist" `
    --add-data "app\adapters\sqlite\migrations\*.sql;app/adapters/sqlite/migrations" `
    desktop.py
if ($LASTEXITCODE -ne 0) { throw "pyinstaller failed" }

Write-Host "== Done: backend\dist\AcademyManagement\AcademyManagement.exe =="
Write-Host "To produce the installer, compile installer\setup.iss with Inno Setup 6."
