param(
    [string]$Token,
    [switch]$Fresh,
    [switch]$SeedDemo
)

$ErrorActionPreference = 'Stop'

$root = Resolve-Path (Join-Path $PSScriptRoot '..')
$appDir = Join-Path $root 'app'
$sandboxDir = Join-Path $root 'sandbox\dev-data'

if ($Token) {
    $env:FUSBALL_PHONE_API_TOKEN = $Token
} elseif (-not $env:FUSBALL_PHONE_API_TOKEN) {
    $secure = Read-Host -Prompt "Enter operator token" -AsSecureString
    $env:FUSBALL_PHONE_API_TOKEN = [Runtime.InteropServices.Marshal]::PtrToStringAuto(
        [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
    )
}

$refreshArgs = @('scripts/refresh_dev_sandbox.py')
if ($Fresh) { $refreshArgs += '--fresh' }
if ($SeedDemo) { $refreshArgs += '--seed-demo' }

Push-Location $root
try {
    if ($Fresh -or $SeedDemo) {
        Write-Host "Refreshing DEV sandbox data in: $sandboxDir"
        py @refreshArgs
    } else {
        Write-Host "Using existing DEV sandbox data in: $sandboxDir"
        # Check for any playerdb artifact (single-file on Python 3.14, .dir/.dat/.bak on older)
        $sandboxExists = (Get-ChildItem -Path $sandboxDir -Filter 'playerdb*' -ErrorAction SilentlyContinue | Measure-Object).Count -gt 0
        if (-not $sandboxExists) {
            Write-Host "No sandbox found — seeding demo players only..."
            py scripts/refresh_dev_sandbox.py --only-seed
        }
    }
}
finally {
    Pop-Location
}

Push-Location $appDir
try {
    Write-Host "Starting phone API in DEV mode (sandbox data)..."
    if ($env:FUSBALL_PHONE_API_TOKEN) {
        Write-Host "Operator token: configured"
    } else {
        Write-Host "Operator token: not set (write endpoint returns 503)"
    }
    py phone_api.py --db-dir $sandboxDir
}
finally {
    Pop-Location
}
