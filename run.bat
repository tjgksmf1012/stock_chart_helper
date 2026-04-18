@echo off
setlocal
title Stock Chart Helper

echo.
echo ==========================================
echo   Stock Chart Helper - Starting...
echo ==========================================
echo.

set BACKEND_PORT=8001
set FRONTEND_PORT=5173
set ROOT_DIR=%~dp0

echo [1/3] Backend starting at http://localhost:%BACKEND_PORT%
start "Backend" cmd /k "cd /d "%ROOT_DIR%backend" && python -m uvicorn app.main:app --reload --port %BACKEND_PORT%"

echo [2/3] Frontend starting at http://localhost:%FRONTEND_PORT%
start "Frontend" cmd /k "cd /d "%ROOT_DIR%frontend" && npm run dev"

echo [3/3] Waiting for dev servers...
call :wait_for_url "http://127.0.0.1:%BACKEND_PORT%/docs" 60 "Backend"
if errorlevel 1 goto :startup_failed

call :wait_for_url "http://127.0.0.1:%FRONTEND_PORT%" 60 "Frontend"
if errorlevel 1 goto :startup_failed

echo.
echo  Backend ready:  http://localhost:%BACKEND_PORT%
echo  Frontend ready: http://localhost:%FRONTEND_PORT%
echo  Opening browser in a fresh tab...
start "" "http://localhost:%FRONTEND_PORT%"
echo.
pause
exit /b 0

:wait_for_url
set TARGET_URL=%~1
set /a MAX_TRIES=%~2
set TARGET_LABEL=%~3
set /a TRY_COUNT=0

:wait_loop
set /a TRY_COUNT+=1
powershell -NoProfile -Command "try { $r = Invoke-WebRequest -Uri '%TARGET_URL%' -UseBasicParsing -TimeoutSec 2; if ($r.StatusCode -ge 200 -and $r.StatusCode -lt 500) { exit 0 } else { exit 1 } } catch { exit 1 }"
if not errorlevel 1 (
  echo   - %TARGET_LABEL% is ready.
  exit /b 0
)

if %TRY_COUNT% GEQ %MAX_TRIES% (
  echo   - %TARGET_LABEL% did not become ready in time.
  exit /b 1
)

timeout /t 1 /nobreak > nul
goto :wait_loop

:startup_failed
echo.
echo One of the dev servers did not start cleanly.
echo Check the opened Backend and Frontend terminal windows for the real error.
echo.
pause
exit /b 1
