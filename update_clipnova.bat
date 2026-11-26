@echo off
title ClipNova AI - One-Click GitHub Updater
color 0B
set "REPO_URL=https://github.com/ahsanK225/ClipNova-AI.git"

echo ============================================================
echo   ClipNova AI - Universal GitHub One-Click Updater
echo   (Your .env, API keys, and data/ clips stay 100%% safe)
echo ============================================================
echo.

cd /d "%~dp0"

where git >nul 2>nul
if %errorlevel% neq 0 (
    echo [ERROR] Git is not installed on this PC.
    echo Download Git from: https://git-scm.com/download/win
    pause
    exit /b 1
)

if not exist ".git" (
    echo [INFO] No .git folder found ^(ZIP download detected^). Connecting to GitHub...
    git init
    git remote add origin "%REPO_URL%"
) else (
    git remote set-url origin "%REPO_URL%" 2>nul
)

echo [1/3] Fetching latest updates from GitHub...
git fetch origin main
if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Could not reach GitHub. Check your internet connection.
    pause
    exit /b 1
)

git stash push -m "auto-before-bat-update" >nul 2>nul
git checkout -f -B main origin/main
if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Git update failed. Close ClipNova AI if it is running and try again.
    pause
    exit /b 1
)

echo.
echo [2/3] Checking Python environment and dependencies...
if not exist ".venv\Scripts\python.exe" (
    echo [INFO] Creating virtual environment .venv...
    python -m venv .venv
)
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" -m pip install --upgrade pip --quiet
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt --quiet
) else (
    pip install -r requirements.txt --quiet
)

echo.
echo [3/3] ClipNova AI is up to date!
echo ============================================================
echo   Press any key to launch ClipNova AI now (or close window).
echo ============================================================
pause >nul
if exist "..\run_clipnova.bat" (
    start "" "..\run_clipnova.bat"
) else if exist ".venv\Scripts\python.exe" (
    start "" ".venv\Scripts\python.exe" -m studio.server
)
