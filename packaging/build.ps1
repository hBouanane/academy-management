# Builds the distributable: React bundle + PyInstaller onedir exe.
# Run from the repo root:  powershell -File packaging\build.ps1
# Output: backend\dist\AcademyManagement\AcademyManagement.exe
#
# Un echec doit se voir. Le script sort en 1 ET l annonce en toutes
# lettres : une sortie tuyautee (| tail) rend le code du DERNIER maillon,
# pas celui de PowerShell -- un echec passerait alors pour un succes, et
# on croirait avoir livre une version qu on n a jamais construite.

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$startedAt = Get-Date

function Fail($why) {
    Write-Host ""
    Write-Host "== ECHEC : $why ==" -ForegroundColor Red
    Write-Host "== AUCUNE version n a ete produite. ==" -ForegroundColor Red
    exit 1
}

trap { Fail $_.Exception.Message }

Write-Host "== Building frontend =="
Set-Location (Join-Path $root "frontend")
npm run build
if ($LASTEXITCODE -ne 0) { Fail "la construction du frontend a echoue" }

Write-Host "== Building executable =="
Set-Location (Join-Path $root "backend")
# La cle de depannage de l'editeur, si elle existe. Sans elle, la version
# livree n'a pas de porte de depannage -- le bon defaut : on n'embarque
# pas un passe-partout sans l'avoir voulu.
$vendorKey = Join-Path $root "packaging\vendor_key.txt"
$extra = @()
if (Test-Path $vendorKey) {
    Write-Host "   (cle de depannage editeur incluse)"
    $extra += "--add-data"
    $extra += "${vendorKey};."
} else {
    Write-Host "   (pas de cle de depannage : porte editeur absente)"
}
# L icone voyage DANS l exe : le bureau, le menu et la barre des taches
# la prennent tous les trois sans qu on ait rien d autre a poser.
$icone = Join-Path $root "packaging\academy.ico"
if (-not (Test-Path $icone)) {
    & (Join-Path $root ".venv\Scripts\python.exe") (Join-Path $root "packaging\make_icon.py")
}
& (Join-Path $root ".venv\Scripts\pyinstaller") `
    --noconfirm --noconsole --onedir `
    --name AcademyManagement `
    --icon "$icone" `
    --add-data "..\frontend\dist;frontend/dist" `
    --add-data "app\adapters\sqlite\migrations\*.sql;app/adapters/sqlite/migrations" `
    @extra `
    desktop.py
if ($LASTEXITCODE -ne 0) { Fail "pyinstaller a echoue (l application est-elle encore ouverte ?)" }

# PyInstaller peut sortir en 0 sans avoir rien reecrit -- on verifie donc
# que le produit existe VRAIMENT et vient de cette execution.
$exe = Join-Path $root "backend\dist\AcademyManagement\AcademyManagement.exe"
if (-not (Test-Path $exe)) { Fail "l executable est introuvable" }
$internal = Join-Path $root "backend\dist\AcademyManagement\_internal"
if ((Get-Item $internal).LastWriteTime -lt $startedAt) {
    Fail "la version n a pas ete reecrite (fichiers verrouilles ?)"
}

Write-Host ""
Write-Host "== OK : $exe ==" -ForegroundColor Green
Write-Host "Pour l installeur : powershell -File packaging\installer.ps1"
