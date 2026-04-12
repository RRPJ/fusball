param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('start', 'stop', 'restart', 'status', 'watchdog')]
    [string]$Action,
    [string]$Token,
    [switch]$PromptToken
)

$ErrorActionPreference = 'Stop'

$root = Resolve-Path (Join-Path $PSScriptRoot '..')
$appDir = Join-Path $root 'app'
$runtimeDir = Join-Path $root 'runtime'
$logDir = Join-Path $runtimeDir 'logs'
$apiPidFile = Join-Path $runtimeDir 'phone_api.pid'
$watchdogPidFile = Join-Path $runtimeDir 'phone_api_watchdog.pid'
$watchdogStopFile = Join-Path $runtimeDir 'phone_api_watchdog.stop'
$outLogFile = Join-Path $logDir 'phone_api.out.log'
$errLogFile = Join-Path $logDir 'phone_api.err.log'
$watchdogOutLogFile = Join-Path $logDir 'phone_api_watchdog.out.log'
$watchdogErrLogFile = Join-Path $logDir 'phone_api_watchdog.err.log'
$tailscaleAppPath = 'C:\Program Files\Tailscale\tailscale-ipn.exe'

$healthCheckIntervalSeconds = 5
$maxUnhealthyChecks = 3

function Get-TailscaleService {
    return Get-Service -Name 'Tailscale' -ErrorAction SilentlyContinue
}

function Get-TailscaleAppProcess {
    return Get-Process -Name 'tailscale-ipn' -ErrorAction SilentlyContinue
}

function Ensure-RuntimePaths {
    if (-not (Test-Path $runtimeDir)) {
        New-Item -Path $runtimeDir -ItemType Directory | Out-Null
    }
    if (-not (Test-Path $logDir)) {
        New-Item -Path $logDir -ItemType Directory | Out-Null
    }
}

function Get-TrackedProcess {
    param(
        [Parameter(Mandatory = $true)]
        [string]$PidPath
    )

    if (-not (Test-Path $PidPath)) {
        return $null
    }

    $pidText = (Get-Content $PidPath -Raw).Trim()
    if (-not $pidText) {
        Remove-Item $PidPath -Force -ErrorAction SilentlyContinue
        return $null
    }

    $pidValue = 0
    if (-not [int]::TryParse($pidText, [ref]$pidValue)) {
        Remove-Item $PidPath -Force -ErrorAction SilentlyContinue
        return $null
    }

    $proc = Get-Process -Id $pidValue -ErrorAction SilentlyContinue
    if (-not $proc) {
        Remove-Item $PidPath -Force -ErrorAction SilentlyContinue
        return $null
    }

    return $proc
}

function Test-Health {
    try {
        $response = Invoke-RestMethod -Uri 'http://127.0.0.1:8080/health' -TimeoutSec 2
        return ($response -and $response.status -eq 'ok')
    }
    catch {
        return $false
    }
}

function Show-TailscaleStatus {
    $tailscaleService = Get-TailscaleService
    if (-not $tailscaleService) {
        Write-Host 'Tailscale service status: not installed'
        Write-Host 'Tailscale app status: unknown'
        return $false
    }

    $tailscaleApp = Get-TailscaleAppProcess
    $tailscaleAppText = if ($tailscaleApp) { 'running' } else { 'not running' }

    Write-Host "Tailscale service status: $($tailscaleService.Status)"
    Write-Host "Tailscale app status: $tailscaleAppText"
    return ($tailscaleService.Status -eq 'Running')
}

function Ensure-TailscaleRunning {
    $tailscaleService = Get-TailscaleService
    if (-not $tailscaleService) {
        Write-Host 'Tailscale service not found. Continuing without automatic Tailscale startup.'
        return
    }

    if ($tailscaleService.Status -eq 'Running') {
        Write-Host 'Tailscale service already running.'
        return
    }

    Write-Host 'Starting Tailscale service...'
    try {
        Start-Service -Name 'Tailscale' -ErrorAction Stop
        Start-Sleep -Milliseconds 500
        $tailscaleService = Get-TailscaleService
        if ($tailscaleService -and $tailscaleService.Status -eq 'Running') {
            Write-Host 'Tailscale service started.'
            return
        }

        Write-Host 'Tailscale service did not reach Running state yet.'
    }
    catch {
        Write-Host "Could not start Tailscale service automatically: $($_.Exception.Message)"
    }
}

function Ensure-TailscaleAppRunning {
    $tailscaleApp = Get-TailscaleAppProcess
    if ($tailscaleApp) {
        Write-Host 'Tailscale app already running.'
        return
    }

    if (-not (Test-Path $tailscaleAppPath)) {
        Write-Host 'Tailscale app executable not found. Continuing without opening the app.'
        return
    }

    Write-Host 'Opening Tailscale app...'
    try {
        Start-Process -FilePath $tailscaleAppPath
    }
    catch {
        Write-Host "Could not open Tailscale app automatically: $($_.Exception.Message)"
    }
}

function Stop-TailscaleApp {
    $tailscaleApps = @(Get-TailscaleAppProcess)
    if (-not $tailscaleApps -or $tailscaleApps.Count -eq 0) {
        Write-Host 'Tailscale app is not running.'
        return
    }

    foreach ($tailscaleApp in $tailscaleApps) {
        Write-Host "Closing Tailscale app (PID $($tailscaleApp.Id))..."
        Stop-Process -Id $tailscaleApp.Id -Force -ErrorAction SilentlyContinue
    }
}

function Resolve-Token {
    if ($Token) {
        $env:FUSBALL_PHONE_API_TOKEN = $Token
        return
    }

    if ($PromptToken -or -not $env:FUSBALL_PHONE_API_TOKEN) {
        $secure = Read-Host -Prompt 'Enter operator token' -AsSecureString
        $resolvedToken = [Runtime.InteropServices.Marshal]::PtrToStringAuto(
            [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
        )
        if (-not $resolvedToken) {
            throw 'Operator token cannot be empty.'
        }
        $env:FUSBALL_PHONE_API_TOKEN = $resolvedToken
    }
}

function Start-ApiProcess {
    Write-Host 'Starting phone API in PROD mode (manual service)...'
    $proc = Start-Process -FilePath 'py' -ArgumentList 'phone_api.py' -WorkingDirectory $appDir -WindowStyle Hidden -RedirectStandardOutput $outLogFile -RedirectStandardError $errLogFile -PassThru
    Set-Content -Path $apiPidFile -Value $proc.Id
    return $proc
}

function Stop-ApiProcess {
    $existingApi = Get-TrackedProcess -PidPath $apiPidFile
    if (-not $existingApi) {
        Remove-Item $apiPidFile -Force -ErrorAction SilentlyContinue
        return
    }

    Stop-Process -Id $existingApi.Id -Force -ErrorAction SilentlyContinue
    Start-Sleep -Milliseconds 300
    Remove-Item $apiPidFile -Force -ErrorAction SilentlyContinue
}

function Start-Watchdog {
    Ensure-RuntimePaths
    Remove-Item $watchdogStopFile -Force -ErrorAction SilentlyContinue

    $watchdogArgs = @(
        '-NoProfile',
        '-ExecutionPolicy',
        'Bypass',
        '-File',
        (Join-Path $PSScriptRoot 'phone_stack_control.ps1'),
        'watchdog'
    )

    $watchdogProc = Start-Process -FilePath 'PowerShell' -ArgumentList $watchdogArgs -WorkingDirectory $root -WindowStyle Hidden -RedirectStandardOutput $watchdogOutLogFile -RedirectStandardError $watchdogErrLogFile -PassThru
    Set-Content -Path $watchdogPidFile -Value $watchdogProc.Id
    return $watchdogProc
}

function Start-PhoneApi {
    $existingWatchdog = Get-TrackedProcess -PidPath $watchdogPidFile
    if ($existingWatchdog) {
        Write-Host "Phone API service is already running under watchdog supervision (PID $($existingWatchdog.Id))."
        Show-Status
        return
    }

    Resolve-Token

    Ensure-RuntimePaths
    Ensure-TailscaleRunning
    Ensure-TailscaleAppRunning

    Push-Location $root
    try {
        Write-Host 'Backing up production data...'
        py scripts/backup_state.py
    }
    finally {
        Pop-Location
    }

    $watchdogProc = Start-Watchdog
    Start-Sleep -Milliseconds 500
    Write-Host "Phone API service watchdog started (PID $($watchdogProc.Id))."
    Write-Host "The watchdog keeps the phone API service running and restarts it after repeated health failures."
    Write-Host "Stdout log: $outLogFile"
    Write-Host "Stderr log: $errLogFile"
    Write-Host "Watchdog stdout log: $watchdogOutLogFile"
    Write-Host "Watchdog stderr log: $watchdogErrLogFile"
}

function Stop-PhoneApi {
    Ensure-RuntimePaths

    $existingWatchdog = Get-TrackedProcess -PidPath $watchdogPidFile
    if ($existingWatchdog) {
        Write-Host "Stopping watchdog (PID $($existingWatchdog.Id))..."
        Set-Content -Path $watchdogStopFile -Value 'stop'
        Stop-Process -Id $existingWatchdog.Id -Force -ErrorAction SilentlyContinue
        Remove-Item $watchdogPidFile -Force -ErrorAction SilentlyContinue
        Remove-Item $watchdogStopFile -Force -ErrorAction SilentlyContinue
    }

    $existingApi = Get-TrackedProcess -PidPath $apiPidFile
    if ($existingApi) {
        Write-Host "Stopping phone API (PID $($existingApi.Id))..."
    }
    Stop-ApiProcess
    Stop-TailscaleApp
    Write-Host 'Phone API service stopped.'
}

function Show-Status {
    Show-TailscaleStatus | Out-Null

    $existingWatchdog = Get-TrackedProcess -PidPath $watchdogPidFile
    $watchdogText = if ($existingWatchdog) { "running (PID $($existingWatchdog.Id))" } else { 'stopped' }
    Write-Host "Watchdog status: $watchdogText"

    $existingApi = Get-TrackedProcess -PidPath $apiPidFile
    if (-not $existingApi) {
        Write-Host 'Phone API status: stopped'
        Write-Host "Stdout log: $outLogFile"
        Write-Host "Stderr log: $errLogFile"
        Write-Host "Watchdog stdout log: $watchdogOutLogFile"
        Write-Host "Watchdog stderr log: $watchdogErrLogFile"
        return
    }

    $healthy = Test-Health
    $healthText = if ($healthy) { 'OK' } else { 'NOT READY' }
    Write-Host "Phone API status: running (PID $($existingApi.Id))"
    Write-Host "Health: $healthText"
    Write-Host "Stdout log: $outLogFile"
    Write-Host "Stderr log: $errLogFile"
    Write-Host "Watchdog stdout log: $watchdogOutLogFile"
    Write-Host "Watchdog stderr log: $watchdogErrLogFile"
}

function Run-Watchdog {
    Ensure-RuntimePaths
    Set-Content -Path $watchdogPidFile -Value $PID
    Write-Host "Watchdog loop active (PID $PID)."

    $unhealthyCount = 0

    while ($true) {
        if (Test-Path $watchdogStopFile) {
            Remove-Item $watchdogStopFile -Force -ErrorAction SilentlyContinue
            break
        }

        $apiProcess = Get-TrackedProcess -PidPath $apiPidFile
        if (-not $apiProcess) {
            try {
                $startedApi = Start-ApiProcess
                Write-Host "API started by watchdog (PID $($startedApi.Id))."
                $unhealthyCount = 0
            }
            catch {
                Write-Host "Watchdog start failed: $($_.Exception.Message)"
            }
            Start-Sleep -Seconds $healthCheckIntervalSeconds
            continue
        }

        if (Test-Health) {
            $unhealthyCount = 0
        }
        else {
            $unhealthyCount += 1
            Write-Host "Health check failed ($unhealthyCount/$maxUnhealthyChecks)."
            if ($unhealthyCount -ge $maxUnhealthyChecks) {
                Write-Host 'API unhealthy repeatedly; restarting API process.'
                Stop-ApiProcess
                try {
                    $startedApi = Start-ApiProcess
                    Write-Host "API restarted by watchdog (PID $($startedApi.Id))."
                }
                catch {
                    Write-Host "Watchdog restart failed: $($_.Exception.Message)"
                }
                $unhealthyCount = 0
            }
        }

        Start-Sleep -Seconds $healthCheckIntervalSeconds
    }

    Remove-Item $watchdogPidFile -Force -ErrorAction SilentlyContinue
    Write-Host 'Watchdog loop stopped.'
}

switch ($Action) {
    'start' { Start-PhoneApi }
    'stop' { Stop-PhoneApi }
    'restart' {
        Stop-PhoneApi
        Start-PhoneApi
    }
    'status' { Show-Status }
    'watchdog' { Run-Watchdog }
}
