# One-command local CRM startup: free port 8000, start backend, then frontend.
# Usage:  powershell -ExecutionPolicy Bypass -File D:\crm\scripts\start-crm.ps1

param([switch]$Reload)

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$BackendScript = Join-Path $PSScriptRoot "start-backend.ps1"
$FrontendRoot = Join-Path $Root "frontend"

Write-Host "==> Starting backend..." -ForegroundColor Cyan
$backendArgs = @("-ExecutionPolicy", "Bypass", "-File", $BackendScript)
if ($Reload) { $backendArgs += "-Reload" }
Start-Process powershell -ArgumentList $backendArgs -WorkingDirectory (Join-Path $Root "backend")

# Wait until /health responds
$ok = $false
for ($i = 0; $i -lt 30; $i++) {
    Start-Sleep -Seconds 1
    try {
        $r = Invoke-WebRequest -Uri "http://127.0.0.1:8000/health" -UseBasicParsing -TimeoutSec 2
        if ($r.StatusCode -eq 200) { $ok = $true; break }
    } catch { }
}
if (-not $ok) {
    Write-Warning "Backend did not answer /health yet. Check the backend window."
} else {
    Write-Host "Backend healthy." -ForegroundColor Green
}

Write-Host "==> Starting frontend (http://127.0.0.1:5173)..." -ForegroundColor Cyan
Start-Process powershell -ArgumentList @(
    "-NoExit", "-ExecutionPolicy", "Bypass",
    "-Command", "cd `"$FrontendRoot`"; npm run dev"
) -WorkingDirectory $FrontendRoot

Write-Host ""
Write-Host "Open: http://127.0.0.1:5173" -ForegroundColor Green
Write-Host "Login: admin@crm.local / Admin123!" -ForegroundColor DarkGray
Write-Host "If login fails again, run:  powershell -File D:\crm\scripts\stop-backend.ps1" -ForegroundColor DarkYellow
Write-Host "Then re-run this script." -ForegroundColor DarkYellow
