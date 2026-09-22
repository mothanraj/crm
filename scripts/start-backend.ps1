# Start the CRM backend on port 8000 — always kills stale listeners first.
# Usage (from anywhere):
#   powershell -ExecutionPolicy Bypass -File D:\crm\scripts\start-backend.ps1
#   powershell -ExecutionPolicy Bypass -File D:\crm\scripts\start-backend.ps1 -Reload

param(
    [switch]$Reload,
    [int]$Port = 8000
)

$ErrorActionPreference = "Stop"
$BackendRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\backend")).Path
$Python = Join-Path $BackendRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $Python)) {
    Write-Error "Python venv not found at $Python. Create it first: cd backend; python -m venv .venv; .\.venv\Scripts\pip install -r requirements.txt"
}

function Get-PortPids([int]$p) {
    $pids = @()
    netstat -ano | Select-String ":$p\s+.*LISTENING" | ForEach-Object {
        $pidText = ($_ -split '\s+')[-1]
        if ($pidText -match '^\d+$') { $pids += [int]$pidText }
    }
    return @($pids | Sort-Object -Unique)
}

Write-Host "Cleaning port $Port ..." -ForegroundColor Yellow
$before = Get-PortPids $Port
foreach ($procId in $before) {
    Write-Host "  killing PID $procId"
    taskkill /F /PID $procId 2>$null | Out-Null
}
Start-Sleep -Seconds 1

# Extra pass for stubborn Python workers left by --reload
Get-Process python -ErrorAction SilentlyContinue | ForEach-Object {
    try {
        $cmd = (Get-CimInstance Win32_Process -Filter "ProcessId=$($_.Id)").CommandLine
        if ($cmd -and ($cmd -match "uvicorn" -or $cmd -match "app\.main:app")) {
            Write-Host "  killing leftover uvicorn PID $($_.Id)"
            Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue
        }
    } catch { }
}
Start-Sleep -Seconds 1

$left = Get-PortPids $Port
if ($left.Count -gt 0) {
    Write-Error "Port $Port still in use by PIDs: $($left -join ', '). Close those apps and retry."
}

Set-Location $BackendRoot
$args = @("-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "$Port")
if ($Reload) {
    $args += "--reload"
    Write-Host "Starting backend WITH --reload on http://127.0.0.1:$Port" -ForegroundColor Cyan
    Write-Host "Tip: for stable login, omit -Reload (default)." -ForegroundColor DarkYellow
} else {
    Write-Host "Starting backend (stable, no reload) on http://127.0.0.1:$Port" -ForegroundColor Green
}

Write-Host "Health check after start: http://127.0.0.1:$Port/health" -ForegroundColor DarkGray
Write-Host "Leave this window open while using the CRM." -ForegroundColor DarkGray
& $Python @args
