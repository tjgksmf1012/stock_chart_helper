@echo off
title Stock Chart Helper
echo.
echo ==========================================
echo   Stock Chart Helper - Starting...
echo ==========================================
echo.
echo [1/2] Backend starting at http://localhost:8000
start Backend cmd /k "cd /d "%~dp0backend" && python -m uvicorn app.main:app --reload --port 8000"
timeout /t 3 /nobreak > nul
echo [2/2] Frontend starting at http://localhost:5173
start Frontend cmd /k "cd /d "%~dp0frontend" && npm run dev"
echo.
echo  Open: http://localhost:5173
echo  API docs: http://localhost:8000/docs
echo.
pause