param(
    [string]$Token,
    [string]$ReadPin,
    [string]$WritePin,
    [switch]$PromptPins,
    [switch]$Fresh,
    [switch]$SeedDemo
)

$ErrorActionPreference = 'Stop'

$root = Resolve-Path (Join-Path $PSScriptRoot '..')
$appDir = Join-Path $root 'app'
$sandboxDir = Join-Path $root 'sandbox\dev-data'

function Resolve-Secret {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Prompt
    )

    $secure = Read-Host -Prompt $Prompt -AsSecureString
    return [Runtime.InteropServices.Marshal]::PtrToStringAuto(
        [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
    )
}

function Configure-SplitPins {
    param(
        [string]$ReadPinValue,
        [string]$WritePinValue,
        [switch]$ForcePrompt
    )

    $hasSplitHashes = $env:READ_PIN_HASH -and $env:WRITE_PIN_HASH
    $wantsSplit = $ReadPinValue -or $WritePinValue -or $ForcePrompt
    if (-not $wantsSplit -and -not $hasSplitHashes) {
        return $false
    }

    $resolvedWrite = $WritePinValue
    if (-not $resolvedWrite -and $ForcePrompt) {
        $resolvedWrite = Resolve-Secret -Prompt 'Enter writer PIN'
        if (-not $resolvedWrite) {
            throw 'Writer PIN cannot be empty when split auth is requested.'
        }
    }

    $resolvedRead = $ReadPinValue
    if ($ForcePrompt -and -not $ReadPinValue) {
        $resolvedRead = Resolve-Secret -Prompt 'Enter read PIN (optional; leave blank to skip)'
    }

    if ($resolvedRead -or $resolvedWrite) {
        $hashArgs = @('scripts/generate_pin_hash.py', '--format', 'json')
        if ($resolvedRead) {
            $hashArgs += @('--read-pin', $resolvedRead)
        }
        if ($resolvedWrite) {
            $hashArgs += @('--write-pin', $resolvedWrite)
        }

        Push-Location $root
        try {
            $rawJson = py @hashArgs
            if (-not $rawJson) {
                throw 'Failed to generate PIN hashes.'
            }
            $hashes = $rawJson | ConvertFrom-Json
        }
        finally {
            Pop-Location
        }

        if ($hashes.READ_PIN_HASH) {
            $env:READ_PIN_HASH = $hashes.READ_PIN_HASH
        }
        if ($hashes.WRITE_PIN_HASH) {
            $env:WRITE_PIN_HASH = $hashes.WRITE_PIN_HASH
        }
    }

    if (-not $env:WRITE_PIN_HASH) {
        throw 'Split auth mode requires WRITE_PIN_HASH.'
    }

    if ($resolvedWrite) {
        # Keep legacy fallback token aligned for local compatibility.
        $env:FUSBALL_PHONE_API_TOKEN = $resolvedWrite
    }

    return $true
}

if (-not (Configure-SplitPins -ReadPinValue $ReadPin -WritePinValue $WritePin -ForcePrompt:$PromptPins)) {
    if ($Token) {
        $env:FUSBALL_PHONE_API_TOKEN = $Token
    } elseif (-not $env:FUSBALL_PHONE_API_TOKEN) {
        $env:FUSBALL_PHONE_API_TOKEN = Resolve-Secret -Prompt 'Enter operator token (legacy mode)'
    }
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
    if ($env:READ_PIN_HASH -and $env:WRITE_PIN_HASH) {
        Write-Host "Auth mode: split PINs (READ_PIN_HASH + WRITE_PIN_HASH configured)"
    } elseif ($env:FUSBALL_PHONE_API_TOKEN) {
        Write-Host "Auth mode: legacy token (FUSBALL_PHONE_API_TOKEN configured)"
    } else {
        Write-Host "Auth mode: no write auth configured (write endpoint returns 503)"
    }
    py phone_api.py --db-dir $sandboxDir
}
finally {
    Pop-Location
}
