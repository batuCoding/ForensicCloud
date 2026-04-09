@echo off
setlocal
echo ============================================================
echo  ForensicCloud — Installation
echo ============================================================
echo.

REM ── Backend ─────────────────────────────────────────────────
echo [1/4] Creating Python virtual environment...
cd /d "%~dp0backend"
python -m venv .venv
if errorlevel 1 (echo ERROR: Python not found. Install Python 3.11 from python.org & pause & exit /b 1)

echo [2/4] Installing Python dependencies (this may take a few minutes)...
call .venv\Scripts\activate.bat
pip install --upgrade pip -q
pip install -r requirements.txt
if errorlevel 1 (echo ERROR: pip install failed. Check your internet connection. & pause & exit /b 1)

REM ── Frontend ─────────────────────────────────────────────────
echo [3/4] Installing Node dependencies...
cd /d "%~dp0frontend"
where node >nul 2>&1
if errorlevel 1 (echo ERROR: Node.js not found. Install from nodejs.org & pause & exit /b 1)
npm install
if errorlevel 1 (echo ERROR: npm install failed. & pause & exit /b 1)

echo [4/4] Building frontend...
npm run build
if errorlevel 1 (echo ERROR: Frontend build failed. & pause & exit /b 1)

echo.
echo ============================================================
echo  Installation complete!
echo  Run start.bat to launch ForensicCloud.
echo ============================================================
pause
