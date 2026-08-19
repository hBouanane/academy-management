# Fabrique ce qui part chez le client, a partir de backend\dist.
#
#   powershell -File packaging\installer.ps1
#
# Deux sorties possibles, dans dist-installer\ :
#   - AcademyManagement-Setup-<version>.exe  si Inno Setup 6 est installe
#     (installation propre : raccourcis, desinstalleur, Programmes et
#      fonctionnalites) ;
#   - AcademyManagement-<version>.zip sinon -- le client decompresse et
#     lance l executable. Ca marche, mais sans raccourci ni desinstalleur.
#
# Pour avoir le vrai installeur :  choco install innosetup -y
# (dans une invite PowerShell lancee EN ADMINISTRATEUR)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot

function Fail($why) {
    Write-Host ""
    Write-Host "== ECHEC : $why ==" -ForegroundColor Red
    exit 1
}

trap { Fail $_.Exception.Message }

$built = Join-Path $root "backend\dist\AcademyManagement"
if (-not (Test-Path (Join-Path $built "AcademyManagement.exe"))) {
    Fail "rien a empaqueter : lancez d abord packaging\build.ps1"
}

# La version vit dans setup.iss : un seul endroit ou la changer.
$iss = Join-Path $root "installer\setup.iss"
$version = (Select-String -Path $iss -Pattern '#define AppVersion "([^"]+)"').Matches[0].Groups[1].Value
$out = Join-Path $root "dist-installer"
New-Item -ItemType Directory -Force $out | Out-Null

$iscc = @(
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    "$env:ProgramFiles\Inno Setup 6\ISCC.exe"
) | Where-Object { Test-Path $_ } | Select-Object -First 1

if ($iscc) {
    Write-Host "== Inno Setup trouve : compilation de l installeur =="
    & $iscc $iss
    if ($LASTEXITCODE -ne 0) { Fail "la compilation de l installeur a echoue" }
    $produced = Join-Path $out "AcademyManagement-Setup-$version.exe"
} else {
    Write-Host "== Inno Setup absent : archive ZIP a la place ==" -ForegroundColor Yellow
    Write-Host "   (pour un vrai installeur : choco install innosetup -y, en administrateur)"
    $produced = Join-Path $out "AcademyManagement-$version.zip"
    if (Test-Path $produced) { Remove-Item $produced }
    Compress-Archive -Path $built -DestinationPath $produced
}

if (-not (Test-Path $produced)) { Fail "aucun fichier n a ete produit" }
$size = [math]::Round((Get-Item $produced).Length / 1MB, 1)

Write-Host ""
Write-Host "== A ENVOYER AU CLIENT ==" -ForegroundColor Green
Write-Host "   $produced  ($size Mo)"
