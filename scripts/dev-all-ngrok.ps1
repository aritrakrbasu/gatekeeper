# All-in-One Development Starter with ngrok (More Stable)
# Starts ngrok tunnel AND FastAPI server together

$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "==================================================" -ForegroundColor Cyan
Write-Host "  Gatekeeper Dev Environment (ngrok)" -ForegroundColor Cyan
Write-Host "==================================================" -ForegroundColor Cyan
Write-Host ""

# Check if ngrok is available
Write-Host "[*] Checking for ngrok..." -ForegroundColor Gray
try {
    $ngrokCheck = Get-Command ngrok -ErrorAction Stop
    Write-Host "[OK] ngrok found" -ForegroundColor Green
} catch {
    Write-Host "[!] ngrok not found!" -ForegroundColor Yellow
    Write-Host "[i] Install ngrok from: https://ngrok.com/download" -ForegroundColor Yellow
    exit 1
}

# Check if .env exists
if (-not (Test-Path .env)) {
    Write-Host "[!] .env file not found!" -ForegroundColor Yellow
    Write-Host "[i] Copying from .env.example..." -ForegroundColor Gray
    Copy-Item .env.example .env
}

# Clean up any existing ngrok processes
Write-Host "[*] Checking for existing ngrok processes..." -ForegroundColor Gray
$existingNgrokProcesses = Get-Process ngrok -ErrorAction SilentlyContinue
if ($existingNgrokProcesses) {
    Write-Host "[i] Terminating existing ngrok process..." -ForegroundColor Yellow
    Stop-Process -Id $existingNgrokProcesses.Id -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 1
}

Write-Host "[*] Starting ngrok tunnel on port 8000..." -ForegroundColor Cyan

# Start ngrok in background
$ngrokProcess = Start-Process -FilePath "ngrok" -ArgumentList "http","8000","--log=stdout" -PassThru -NoNewWindow -ErrorAction SilentlyContinue

if (-not $ngrokProcess) {
    Write-Host "[X] Failed to start ngrok!" -ForegroundColor Red
    exit 1
}

# Wait for ngrok to start
Start-Sleep -Seconds 2

# Get the public URL from ngrok API
Write-Host "[*] Getting tunnel URL from ngrok..." -ForegroundColor Gray
$maxAttempts = 10
$attempt = 0
$publicUrl = $null

while ($attempt -lt $maxAttempts -and -not $publicUrl) {
    Start-Sleep -Milliseconds 500
    $attempt++

    try {
        $response = Invoke-RestMethod -Uri "http://127.0.0.1:4040/api/tunnels" -ErrorAction SilentlyContinue
        if ($response -and $response.tunnels -and $response.tunnels.Count -gt 0) {
            $publicUrl = $response.tunnels[0].public_url
        }
    } catch {
        # Retry on error
    }
}

if (-not $publicUrl) {
    Write-Host "[X] Failed to get ngrok URL!" -ForegroundColor Red
    Stop-Process -Id $ngrokProcess.Id -ErrorAction SilentlyContinue
    exit 1
}

$webhookUrl = "$publicUrl/webhooks/gitlab"

Write-Host "[OK] ngrok tunnel established!" -ForegroundColor Green
Write-Host "    Public URL: $publicUrl" -ForegroundColor White
Write-Host "    Webhook URL: $webhookUrl" -ForegroundColor Cyan
Write-Host "    ngrok Dashboard: http://127.0.0.1:4040" -ForegroundColor Gray
Write-Host ""

# Update .env file
Write-Host "[*] Updating .env file with webhook URL..." -ForegroundColor Gray

$envContent = Get-Content .env -ErrorAction SilentlyContinue
if ($envContent) {
    $updatedContent = $envContent | ForEach-Object {
        if ($_ -match '^GATEKEEPER_WEBHOOK_URL=') {
            "GATEKEEPER_WEBHOOK_URL=$webhookUrl"
        } else {
            $_
        }
    }
    $updatedContent | Set-Content .env
} else {
    "GATEKEEPER_WEBHOOK_URL=$webhookUrl" | Add-Content .env
}

Write-Host "[OK] .env updated!" -ForegroundColor Green
Write-Host ""

# Check if uvicorn is available
Write-Host "[*] Checking for uvicorn..." -ForegroundColor Gray
try {
    $uvicornCheck = Get-Command uvicorn -ErrorAction Stop
    Write-Host "[OK] uvicorn found" -ForegroundColor Green
} catch {
    Write-Host "[X] uvicorn not found!" -ForegroundColor Red
    Write-Host "[i] Install with: pip install uvicorn" -ForegroundColor Yellow
    Stop-Process -Id $ngrokProcess.Id -ErrorAction SilentlyContinue
    exit 1
}

# Display startup message
Write-Host ""
Write-Host "==================================================" -ForegroundColor Green
Write-Host "     Starting Gatekeeper API Server" -ForegroundColor Green
Write-Host "==================================================" -ForegroundColor Green
Write-Host ""
Write-Host "  API: http://localhost:8000" -ForegroundColor Cyan
Write-Host "  Docs: http://localhost:8000/docs" -ForegroundColor Cyan
Write-Host "  Webhook: $webhookUrl" -ForegroundColor Cyan
Write-Host ""
Write-Host "  ngrok Dashboard: http://127.0.0.1:4040" -ForegroundColor Gray
Write-Host "  Press Ctrl+C to stop both tunnel and server" -ForegroundColor Yellow
Write-Host ""
Write-Host "==================================================" -ForegroundColor Green
Write-Host ""

# Start uvicorn (this will block)
try {
    uvicorn main:app --reload --host 0.0.0.0 --port 8000
}
finally {
    # Cleanup when uvicorn stops
    Write-Host "`n[*] Stopping ngrok tunnel..." -ForegroundColor Yellow
    Stop-Process -Id $ngrokProcess.Id -ErrorAction SilentlyContinue
    Write-Host "[OK] Development environment stopped" -ForegroundColor Green
}
