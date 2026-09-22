# Stop every process listening on the CRM backend port (default 8000).
param([int]$Port = 8000)

$pids = @()
netstat -ano | Select-String ":$Port\s+.*LISTENING" | ForEach-Object {
    $pidText = ($_ -split '\s+')[-1]
    if ($pidText -match '^\d+$') { $pids += [int]$pidText }
}
$pids = @($pids | Sort-Object -Unique)

if ($pids.Count -eq 0) {
    Write-Host "Nothing listening on port $Port." -ForegroundColor Green
} else {
    foreach ($procId in $pids) {
        Write-Host "Stopping PID $procId on port $Port"
        taskkill /F /PID $procId 2>$null | Out-Null
    }
}

Get-Process python -ErrorAction SilentlyContinue | ForEach-Object {
    try {
        $cmd = (Get-CimInstance Win32_Process -Filter "ProcessId=$($_.Id)").CommandLine
        if ($cmd -and ($cmd -match "uvicorn" -or $cmd -match "app\.main:app")) {
            Write-Host "Stopping leftover uvicorn PID $($_.Id)"
            Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue
        }
    } catch { }
}

Start-Sleep -Seconds 1
$left = netstat -ano | Select-String ":$Port\s+.*LISTENING"
if ($left) {
    Write-Host "WARNING: port $Port still has listeners:" -ForegroundColor Red
    $left
} else {
    Write-Host "Port $Port is free." -ForegroundColor Green
}
