#Requires -Version 5.1
<#
.SYNOPSIS
  Assemble l’APK release avec nom versionné TICTAC-LIVE-<version>.apk
#>
[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$Root = $PSScriptRoot
Set-Location -LiteralPath $Root

$versionFile = Join-Path $Root 'VERSION'
if (-not (Test-Path -LiteralPath $versionFile)) {
    Write-Error "VERSION manquant : $versionFile"
}
$version = (Get-Content -LiteralPath $versionFile -TotalCount 1).Trim()
if ($version -notmatch '^\d+\.\d+\.\d+') {
    Write-Error "VERSION invalide : $version"
}

Write-Host "[apk] assembleRelease $version"
if (Test-Path -LiteralPath (Join-Path $Root 'gradlew.bat')) {
    & .\gradlew.bat assembleRelease
} else {
    & .\gradlew assembleRelease
}
if ($LASTEXITCODE -ne 0) { Write-Error 'assembleRelease a échoué' }

$apkDir = Join-Path $Root 'app\build\outputs\apk\release'
$built = Get-ChildItem -LiteralPath $apkDir -Filter '*.apk' -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -notlike '*-unsigned*' } |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1
if (-not $built) {
    Write-Error "APK introuvable dans $apkDir"
}

$outName = "TICTAC-LIVE-$version.apk"
$downloads = Join-Path (Split-Path -Parent $Root) 'downloads'
New-Item -ItemType Directory -Force -Path $downloads | Out-Null
$dest = Join-Path $downloads $outName
Copy-Item -LiteralPath $built.FullName -Destination $dest -Force
Write-Host "[apk] → $dest"

$indexPath = Join-Path $downloads 'index.json'
if (Test-Path -LiteralPath $indexPath) {
    try {
        $idx = Get-Content -LiteralPath $indexPath -Raw -Encoding UTF8 | ConvertFrom-Json
        if ($idx.android) {
            $code = 0
            if ($version -match '^(\d+)\.(\d+)\.(\d+)') {
                $code = ([int]$Matches[1] * 10000) + ([int]$Matches[2] * 100) + [int]$Matches[3]
            }
            $idx.android.version = $version
            $idx.android.versionCode = $code
            $idx.android.filename = $outName
            $idx.android.download = "https://tictachebdo.cd/wp-content/uploads/tictac-live/$outName"
            $idx.android.github_release = "https://github.com/stickrdc-paulin/tictac-live/releases/latest/download/$outName"
            ($idx | ConvertTo-Json -Depth 6) | Set-Content -LiteralPath $indexPath -Encoding UTF8
            Write-Host "[apk] index.json android → $version / $outName"
        }
    } catch {
        Write-Warning "index.json non mis à jour : $_"
    }
}

Write-Host "[apk] OK $outName"
