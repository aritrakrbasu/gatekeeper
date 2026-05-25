@echo off
REM Quick Start Script for Gatekeeper with GitNexus (Windows)

echo ================================
echo Gatekeeper + GitNexus Quick Start
echo ================================
echo.

REM Check if GitNexus is installed
echo 1. Checking GitNexus installation...
where gitnexus >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    echo    [OK] GitNexus is installed
    gitnexus --version
) else (
    echo    [X] GitNexus not found
    echo    Installing GitNexus...
    call npm install -g gitnexus
)

echo.
echo 2. Starting repository setup...
echo    You'll be prompted to add repositories
echo.

REM Run the repository setup
python setup_repos.py

echo.
echo 3. To enable GitNexus analysis, run:
echo    python setup_repos.py index
echo.
echo 4. Then start Gatekeeper:
echo    python main.py
echo.
echo ================================
echo Quick Start Complete!
echo ================================
pause
