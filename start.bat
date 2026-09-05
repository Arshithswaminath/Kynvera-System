@echo off
echo ========================================
echo Starting Injaaz App - Development Server
echo ========================================
echo.
if not exist "venv\Scripts\python.exe" (
  echo Virtual environment not found. Run setup.ps1 first.
  exit /b 1
)
echo Initializing database...
venv\Scripts\python.exe scripts\init_db.py
echo.
echo Starting Flask server (see PORT in .env, default http://localhost:5004)
echo Press Ctrl+C to stop
echo.
venv\Scripts\python.exe Injaaz.py
