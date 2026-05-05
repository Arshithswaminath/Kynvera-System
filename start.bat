@echo off
echo ========================================
echo Starting Injaaz App - Development Server
echo ========================================
echo.
echo Initializing database...
python scripts\init_db.py
echo.
echo Starting Flask server on http://localhost:5000
echo Press Ctrl+C to stop
echo.
python Injaaz.py
