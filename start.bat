@echo off
setlocal
echo ============================================================
echo  ForensicCloud — Starting
echo ============================================================
cd /d "%~dp0backend"

if not exist ".venv\Scripts\activate.bat" (
  echo ERROR: Virtual environment not found. Run install.bat first.
  pause
  exit /b 1
)

call .venv\Scripts\activate.bat
echo  Opening http://localhost:8000 ...
python main.py
pause
