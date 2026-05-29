# Development Tunnel Starter
# Automatically starts localtunnel and updates GATEKEEPER_WEBHOOK_URL in .env

$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "==================================================" -ForegroundColor Cyan
Write-Host "  Gatekeeper Dev Tunnel with LocalTunnel" -ForegroundColor Cyan
Write-Host "==================================================" -ForegroundColor Cyan
Write-Host ""

# Check if .env exists
if (-not (Test-Path .env)) {
    Write-Host "[!] .env file not found!" -ForegroundColor Yellow
    Write-Host "[i] Copying from .env.example..." -ForegroundColor Gray
    Copy-Item .env.example .env
}

# Create temp file for localtunnel output
$ltOutputFile = "lt-output.txt"
if (Test-Path $ltOutputFile) { Remove-Item $ltOutputFile }

Write-Host "[*] Starting localtunnel on port 8000..." -ForegroundColor Cyan

# Start localtunnel in background using npm exec
$ltProcess = Start-Process -FilePath "cmd" -ArgumentList "/c","npm","exec","localtunnel","--","--port","8000","--log","false" -PassThru -RedirectStandardOutput $ltOutputFile -NoNewWindow -ErrorAction SilentlyContinue

if (-not $ltProcess) {
    Write-Host "[X] Failed to start localtunnel!" -ForegroundColor Red
    Write-Host "[i] Make sure you have Node.js and npx installed." -ForegroundColor Yellow
    exit 1
}

# Wait for localtunnel to initialize and get URL
Write-Host "[*] Waiting for tunnel URL..." -ForegroundColor Gray
$publicUrl = $null
$maxAttempts = 15
$attempt = 0

while ($attempt -lt $maxAttempts -and -not $publicUrl) {
    Start-Sleep -Milliseconds 500
    $attempt++

    if (Test-Path $ltOutputFile) {
        $content = Get-Content $ltOutputFile -Raw -ErrorAction SilentlyContinue
        if ($content -match 'your url is: (?<url>https?://[^\s\r\n]+)') {
            $publicUrl = $matches['url'].Trim()
        }
    }

    Write-Host "." -NoNewline -ForegroundColor Gray
}

Write-Host ""

if (-not $publicUrl) {
    Write-Host "[X] Failed to get localtunnel URL!" -ForegroundColor Red
    Write-Host "[i] Output from localtunnel:" -ForegroundColor Yellow
    if (Test-Path $ltOutputFile) {
        Get-Content $ltOutputFile | Write-Host
    }
    Stop-Process -Id $ltProcess.Id -ErrorAction SilentlyContinue
    exit 1
}

$webhookUrl = "$publicUrl/webhooks/gitlab"

Write-Host "[OK] Local tunnel established!" -ForegroundColor Green
Write-Host "    Public URL: $publicUrl" -ForegroundColor White
Write-Host "    Webhook URL: $webhookUrl" -ForegroundColor Cyan
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

# Display next steps
Write-Host "==================================================" -ForegroundColor Green
Write-Host "  Tunnel is running! Now start your FastAPI app:" -ForegroundColor Green
Write-Host "==================================================" -ForegroundColor Green
Write-Host ""
Write-Host "    uvicorn main:app --reload --host 0.0.0.0 --port 8000" -ForegroundColor White
Write-Host ""
Write-Host "  Or use the dev script:" -ForegroundColor Green
Write-Host "    npm run dev:api" -ForegroundColor White
Write-Host ""
Write-Host "==================================================" -ForegroundColor Green
Write-Host ""

# Keep the script running so localtunnel stays alive
Write-Host "[i] Press Ctrl+C to stop the tunnel" -ForegroundColor Yellow
Write-Host ""

try {
    # Wait for the localtunnel process
    $ltProcess.WaitForExit()
}
finally {
    # Cleanup
    Write-Host "`n[*] Stopping tunnel..." -ForegroundColor Yellow
    if (Test-Path $ltOutputFile) { Remove-Item $ltOutputFile }
}
