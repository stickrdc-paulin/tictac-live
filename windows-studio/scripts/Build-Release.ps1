#Requires -Version 5.1
<#
.SYNOPSIS
  Build PyInstaller + installateur Inno Setup + signature Authenticode optionnelle.

.DESCRIPTION
  1. Synchronise version_info.txt depuis VERSION
  2. Build TICTAC-Studio-Regie.exe (métadonnées FileVersion / ProductVersion)
  3. Signe l'exe si TICTAC_CODE_SIGN_* est défini
  4. Compile l'installateur Inno Setup (version visible sur l'écran d'accueil)
  5. Signe le Setup si possible

  Prérequis Windows :
    - Python 3 + pip (requirements.txt)
    - PyInstaller
    - Inno Setup 6 (ISCC.exe) pour le Setup — sinon seul l'exe est produit
    - Windows SDK (signtool) uniquement si signature demandée
#>
[CmdletBinding()]
param(
    [switch]$SkipInstaller,
    [switch]$SkipSign
)

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $Root

$version = & (Join-Path $PSScriptRoot 'Sync-VersionInfo.ps1') -Root $Root
Write-Host "[build] TICTAC Studio Regie $version"

Write-Host '[build] pip install…'
python -m pip install -r requirements.txt -q
if ($LASTEXITCODE -ne 0) { Write-Error 'pip install a échoué' }

Write-Host '[build] PyInstaller…'
python -m PyInstaller --noconfirm TICTAC-Studio-Regie.spec
if ($LASTEXITCODE -ne 0) { Write-Error 'PyInstaller a échoué' }

$exe = Join-Path $Root 'dist\TICTAC-Studio-Regie.exe'
if (-not (Test-Path -LiteralPath $exe)) {
    Write-Error "Exe introuvable : $exe"
}
Copy-Item -LiteralPath $exe -Destination (Join-Path $Root 'TICTAC-Studio-Regie.exe') -Force

if (-not $SkipSign) {
    & (Join-Path $PSScriptRoot 'Sign-Authenticode.ps1') $exe
}

if ($SkipInstaller) {
    Write-Host "[build] Terminé (exe seul) : $exe"
    exit 0
}

function Find-ISCC {
    if ($env:TICTAC_ISCC -and (Test-Path -LiteralPath $env:TICTAC_ISCC)) {
        return $env:TICTAC_ISCC
    }
    $cmd = Get-Command ISCC.exe -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    $candidates = @(
        "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
        "${env:ProgramFiles}\Inno Setup 6\ISCC.exe"
    )
    foreach ($c in $candidates) {
        if (Test-Path -LiteralPath $c) { return $c }
    }
    return $null
}

$iscc = Find-ISCC
if (-not $iscc) {
    Write-Warning 'Inno Setup 6 (ISCC.exe) introuvable — installateur non produit. Installez https://jrsoftware.org/isinfo.php ou définissez TICTAC_ISCC.'
    Write-Host "[build] Terminé (exe) : $exe"
    exit 0
}

$outDir = Join-Path $Root 'dist\installer'
New-Item -ItemType Directory -Force -Path $outDir | Out-Null
$iss = Join-Path $Root 'installer\TICTAC-Studio-Regie.iss'

Write-Host "[build] Inno Setup → version $version"
& $iscc "/DMyAppVersion=$version" $iss
if ($LASTEXITCODE -ne 0) { Write-Error 'ISCC a échoué' }

$setup = Join-Path $outDir "TICTAC-Studio-Regie-Setup-$version.exe"
if (-not (Test-Path -LiteralPath $setup)) {
    Write-Error "Setup introuvable : $setup"
}

if (-not $SkipSign) {
    & (Join-Path $PSScriptRoot 'Sign-Authenticode.ps1') $setup
}

Write-Host "[build] OK"
Write-Host "  App     : $exe"
Write-Host "  Setup   : $setup"
Write-Host "  Version : $version (visible sur l'accueil Inno + propriétés des fichiers)"
