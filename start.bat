@echo off
echo ========================================
echo Starting Amaan App - Development Server
echo ========================================
echo.
echo Initializing database...
python scripts\init_db.py
echo.
echo Starting Flask server on http://localhost:5002
echo Press Ctrl+C to stop
echo.
python Amaan.py
