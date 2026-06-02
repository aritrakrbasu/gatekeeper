# Stop ngrok tunnel
# Run this script when you're done developing

$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "==================================================" -ForegroundColor Yellow
Write-Host "  Stopping ngrok Tunnel" -ForegroundColor Yellow
Write-Host "==================================================" -ForegroundColor Yellow
Write-Host ""

# Check for existing ngrok processes
$existingNgrokProcesses = Get-Process ngrok -ErrorAction SilentlyContinue
if ($existingNgrokProcesses) {
    Write-Host "[*] Found ngrok process (PID: $($existingNgrokProcesses.Id))" -ForegroundColor Gray
    Write-Host "[*] Stopping ngrok..." -ForegroundColor Yellow
    Stop-Process -Id $existingNgrokProcesses.Id -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 1

    # Verify it's stopped
    $stillRunning = Get-Process ngrok -ErrorAction SilentlyContinue
    if ($stillRunning) {
        Write-Host "[!] Failed to stop ngrok" -ForegroundColor Red
    } else {
        Write-Host "[OK] ngrok stopped successfully" -ForegroundColor Green
    }
} else {
    Write-Host "[i] No ngrok process found running" -ForegroundColor Gray
}

Write-Host ""
Write-Host "[OK] Done!" -ForegroundColor Green
Write-Host ""
