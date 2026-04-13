param(
    [string]$Token
)

$ErrorActionPreference = 'Stop'

$root = Resolve-Path (Join-Path $PSScriptRoot '..')
$appDir = Join-Path $root 'app'

if ($Token) {
    $env:FUSBALL_PHONE_API_TOKEN = $Token
} elseif (-not $env:FUSBALL_PHONE_API_TOKEN) {
    $secure = Read-Host -Prompt "Enter operator token" -AsSecureString
    $env:FUSBALL_PHONE_API_TOKEN = [Runtime.InteropServices.Marshal]::PtrToStringAuto(
        [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
    )
}

Push-Location $root
try {
    Write-Host "Backing up production data..."
    py scripts/backup_state.py
}
finally {
    Pop-Location
}

Push-Location $appDir
try {
    Write-Host "Starting phone API in PROD mode (app data)..."
    if ($env:FUSBALL_PHONE_API_TOKEN) {
        Write-Host "Operator token: configured"
    } else {
        Write-Host "Operator token: not set (write endpoint returns 503)"
    }
    py phone_api.py
}
finally {
    Pop-Location
}
