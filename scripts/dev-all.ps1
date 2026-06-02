# All-in-One Development Starter
# Starts localtunnel AND FastAPI server together

$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "==================================================" -ForegroundColor Cyan
Write-Host "  Gatekeeper Dev Environment (All-in-One)" -ForegroundColor Cyan
Write-Host "==================================================" -ForegroundColor Cyan
Write-Host ""

# Check if .env exists
if (-not (Test-Path .env)) {
    Write-Host "[!] .env file not found!" -ForegroundColor Yellow
    Write-Host "[i] Copying from .env.example..." -ForegroundColor Gray
    Copy-Item .env.example .env
}

# Clean up any existing localtunnel processes from previous runs
Write-Host "[*] Checking for existing localtunnel processes..." -ForegroundColor Gray
$existingLtProcesses = Get-Process node -ErrorAction SilentlyContinue | Where-Object {
    $cmdLine = (Get-WmiObject Win32_Process -Filter "ProcessId=$($_.Id)" -ErrorAction SilentlyContinue).CommandLine
    $cmdLine -and ($cmdLine -match 'localtunnel' -or $cmdLine -match 'lt\.js' -or $cmdLine -match '--port 8000')
}

if ($existingLtProcesses) {
    Write-Host "[i] Found $($existingLtProcesses.Count) stale localtunnel process(es), terminating..." -ForegroundColor Yellow
    foreach ($proc in $existingLtProcesses) {
        Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
    }
    Start-Sleep -Milliseconds 500  # Give processes time to terminate
}

# Create temp file for localtunnel output
$ltOutputFile = "lt-output.txt"

# Try to remove the output file with retries if it's locked
if (Test-Path $ltOutputFile) {
    $maxRetries = 3
    $retry = 0
    $removed = $false

    while (-not $removed -and $retry -lt $maxRetries) {
        try {
            Remove-Item $ltOutputFile -Force -ErrorAction Stop
            $removed = $true
        } catch {
            $retry++
            if ($retry -lt $maxRetries) {
                Write-Host "[i] File locked, retrying... ($retry/$maxRetries)" -ForegroundColor Yellow
                Start-Sleep -Milliseconds 500
            } else {
                Write-Host "[!] Could not remove $ltOutputFile, will try to overwrite it" -ForegroundColor Yellow
            }
        }
    }
}

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
$maxAttempts = 40  # Increased from 15 to 40 (20 seconds total for slow connections)
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

    # Show progress every 5 attempts
    if ($attempt % 5 -eq 0) {
        Write-Host "." -NoNewline -ForegroundColor Gray
    }
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

# Check if uvicorn is available
Write-Host "[*] Checking for uvicorn..." -ForegroundColor Gray
try {
    $uvicornCheck = Get-Command uvicorn -ErrorAction Stop
    Write-Host "[OK] uvicorn found" -ForegroundColor Green
} catch {
    Write-Host "[X] uvicorn not found!" -ForegroundColor Red
    Write-Host "[i] Install with: pip install uvicorn" -ForegroundColor Yellow
    Stop-Process -Id $ltProcess.Id -ErrorAction SilentlyContinue
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
    Write-Host "`n[*] Stopping tunnel..." -ForegroundColor Yellow
    Stop-Process -Id $ltProcess.Id -ErrorAction SilentlyContinue
    if (Test-Path $ltOutputFile) { Remove-Item $ltOutputFile }
    Write-Host "[OK] Development environment stopped" -ForegroundColor Green
}
