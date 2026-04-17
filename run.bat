@echo off
title Stock Chart Helper
echo.
echo ==========================================
echo   Stock Chart Helper - Starting...
echo ==========================================
echo.
set BACKEND_PORT=8001
echo [1/2] Backend starting at http://localhost:%BACKEND_PORT%
start Backend cmd /k "cd /d "%~dp0backend" && python -m uvicorn app.main:app --reload --port %BACKEND_PORT%"
timeout /t 3 /nobreak > nul
echo [2/2] Frontend starting at http://localhost:5173
start Frontend cmd /k "cd /d "%~dp0frontend" && npm run dev"
echo.
echo  Open: http://localhost:5173
echo  API docs: http://localhost:%BACKEND_PORT%/docs
echo.
pause
