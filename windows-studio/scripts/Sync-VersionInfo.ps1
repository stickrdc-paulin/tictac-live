#Requires -Version 5.1
<#
.SYNOPSIS
  Aligne version_info.txt (PyInstaller) sur le fichier VERSION.
#>
[CmdletBinding()]
param(
    [string]$Root = (Split-Path -Parent $PSScriptRoot)
)

$ErrorActionPreference = 'Stop'
$versionPath = Join-Path $Root 'VERSION'
if (-not (Test-Path -LiteralPath $versionPath)) {
    Write-Error "VERSION manquant : $versionPath"
}

$version = (Get-Content -LiteralPath $versionPath -Raw).Trim().Split("`n")[0].Trim()
if ($version -notmatch '^(\d+)\.(\d+)\.(\d+)(?:\.(\d+))?$') {
    Write-Error "VERSION invalide (attendu x.y.z) : $version"
}
$major = [int]$Matches[1]
$minor = [int]$Matches[2]
$patch = [int]$Matches[3]
$build = if ($Matches[4]) { [int]$Matches[4] } else { 0 }

$out = Join-Path $Root 'version_info.txt'
$content = @"
# UTF-8
#
# Métadonnées Windows (Properties → Détails) pour TICTAC-Studio-Regie.exe.
# Généré depuis windows-studio/VERSION ($version) — ne pas éditer à la main ;
# relancer Sync-VersionInfo.ps1 ou Build-Release.ps1.
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=($major, $minor, $patch, $build),
    prodvers=($major, $minor, $patch, $build),
    mask=0x3F,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo(
      [
        StringTable(
          '040C04B0',
          [
            StringStruct('CompanyName', 'STICK RDC SARLU'),
            StringStruct('FileDescription', 'TICTAC Studio Regie — régie audio TIC-TAC Hebdo'),
            StringStruct('FileVersion', '$version'),
            StringStruct('InternalName', 'TICTAC-Studio-Regie'),
            StringStruct('LegalCopyright', 'Copyright (C) STICK RDC SARLU'),
            StringStruct('OriginalFilename', 'TICTAC-Studio-Regie.exe'),
            StringStruct('ProductName', 'TICTAC Studio Regie'),
            StringStruct('ProductVersion', '$version'),
          ]
        )
      ]
    ),
    VarFileInfo([VarStruct('Translation', [1036, 1200])])
  ]
)
"@

$utf8NoBom = New-Object System.Text.UTF8Encoding $false
[System.IO.File]::WriteAllText($out, $content.TrimStart() + "`r`n", $utf8NoBom)
Write-Host "[version] version_info.txt → $version"
return $version
