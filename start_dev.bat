@echo off
echo ============================================================
echo  ForensicCloud — Development Mode (backend + Vite HMR)
echo ============================================================

REM Start backend in one window
start "ForensicCloud Backend" cmd /k "cd /d "%~dp0backend" && call .venv\Scripts\activate.bat && python main.py"

REM Start frontend Vite dev server in another
start "ForensicCloud Frontend" cmd /k "cd /d "%~dp0frontend" && npm run dev"

echo.
echo  Backend:  http://localhost:8000/api/docs
echo  Frontend: http://localhost:5173
echo.
timeout /t 3 /nobreak > nul
start http://localhost:5173
