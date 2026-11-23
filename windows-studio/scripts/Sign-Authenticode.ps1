#Requires -Version 5.1
<#
.SYNOPSIS
  Signe un ou plusieurs fichiers PE avec Authenticode (signtool).

.DESCRIPTION
  Ne fait rien (exit 0) si aucun certificat n'est configuré — le build non signé
  reste possible. Voir docs/studio-signing.md et .env.example.

  Variables d'environnement :
    TICTAC_CODE_SIGN_PFX          Chemin vers le .pfx / .p12
    TICTAC_CODE_SIGN_PFX_BASE64   Contenu PFX encodé base64 (CI) — écrit un fichier temp
    TICTAC_CODE_SIGN_PASSWORD     Mot de passe du PFX (si protégé)
    TICTAC_CODE_SIGN_THUMBPRINT   Empreinte cert dans le magasin Windows (alternative au PFX)
    TICTAC_CODE_SIGN_TIMESTAMP_URL  Horodatage RFC3161 (défaut DigiCert)
    TICTAC_CODE_SIGN_TOOL         Chemin explicite vers signtool.exe (optionnel)
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true, ValueFromRemainingArguments = $true)]
    [string[]]$Files
)

$ErrorActionPreference = 'Stop'

function Find-SignTool {
    if ($env:TICTAC_CODE_SIGN_TOOL -and (Test-Path -LiteralPath $env:TICTAC_CODE_SIGN_TOOL)) {
        return $env:TICTAC_CODE_SIGN_TOOL
    }
    $cmd = Get-Command signtool.exe -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }

    $roots = @(
        "${env:ProgramFiles(x86)}\Windows Kits\10\bin",
        "${env:ProgramFiles}\Windows Kits\10\bin"
    )
    foreach ($root in $roots) {
        if (-not (Test-Path -LiteralPath $root)) { continue }
        $found = Get-ChildItem -Path $root -Recurse -Filter signtool.exe -ErrorAction SilentlyContinue |
            Sort-Object FullName -Descending |
            Select-Object -First 1
        if ($found) { return $found.FullName }
    }
    return $null
}

function Test-SigningConfigured {
    return [bool](
        $env:TICTAC_CODE_SIGN_PFX -or
        $env:TICTAC_CODE_SIGN_PFX_BASE64 -or
        $env:TICTAC_CODE_SIGN_THUMBPRINT
    )
}

if (-not (Test-SigningConfigured)) {
    Write-Host '[sign] Aucune variable TICTAC_CODE_SIGN_* — signature ignorée (build non signé).'
    exit 0
}

$signtool = Find-SignTool
if (-not $signtool) {
    Write-Error 'signtool.exe introuvable. Installez Windows SDK ou définissez TICTAC_CODE_SIGN_TOOL.'
}

$timestamp = if ($env:TICTAC_CODE_SIGN_TIMESTAMP_URL) {
    $env:TICTAC_CODE_SIGN_TIMESTAMP_URL
} else {
    'http://timestamp.digicert.com'
}

$tempPfx = $null
try {
    $signArgs = @('sign', '/fd', 'SHA256', '/td', 'SHA256', '/tr', $timestamp)

    if ($env:TICTAC_CODE_SIGN_THUMBPRINT) {
        $signArgs += @('/sha1', $env:TICTAC_CODE_SIGN_THUMBPRINT)
    }
    else {
        $pfxPath = $env:TICTAC_CODE_SIGN_PFX
        if ($env:TICTAC_CODE_SIGN_PFX_BASE64) {
            $tempPfx = Join-Path ([System.IO.Path]::GetTempPath()) ("tictac-codesign-{0}.pfx" -f [guid]::NewGuid().ToString('N'))
            [IO.File]::WriteAllBytes($tempPfx, [Convert]::FromBase64String($env:TICTAC_CODE_SIGN_PFX_BASE64))
            $pfxPath = $tempPfx
        }
        if (-not $pfxPath -or -not (Test-Path -LiteralPath $pfxPath)) {
            Write-Error "PFX introuvable : $pfxPath"
        }
        $signArgs += @('/f', $pfxPath)
        if ($env:TICTAC_CODE_SIGN_PASSWORD) {
            $signArgs += @('/p', $env:TICTAC_CODE_SIGN_PASSWORD)
        }
    }

    foreach ($file in $Files) {
        if (-not (Test-Path -LiteralPath $file)) {
            Write-Error "Fichier à signer introuvable : $file"
        }
        Write-Host "[sign] $file"
        & $signtool @signArgs $file
        if ($LASTEXITCODE -ne 0) {
            Write-Error "signtool a échoué ($LASTEXITCODE) pour $file"
        }
        & $signtool verify /pa /v $file
        if ($LASTEXITCODE -ne 0) {
            Write-Error "Vérification Authenticode échouée pour $file"
        }
    }
}
finally {
    if ($tempPfx -and (Test-Path -LiteralPath $tempPfx)) {
        Remove-Item -LiteralPath $tempPfx -Force -ErrorAction SilentlyContinue
    }
}

Write-Host '[sign] OK'
