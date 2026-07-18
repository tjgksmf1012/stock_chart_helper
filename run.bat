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

if not exist "%ROOT_DIR%backend\.env" (
  echo No backend\.env found - using local desktop mode defaults ^(SQLite, no Postgres/Redis needed^).
  copy "%ROOT_DIR%backend\.env.local.example" "%ROOT_DIR%backend\.env" >nul
) else (
  findstr /R /C:"^DATABASE_URL=postgresql" "%ROOT_DIR%backend\.env" >nul 2>&1
  if not errorlevel 1 (
    echo.
    echo [WARNING] backend\.env is configured for a Postgres server.
    echo           Local desktop mode uses SQLite - if no Postgres server is running,
    echo           API requests will fail and only show up as CORS errors in the browser.
    echo           To switch to SQLite: delete backend\.env and re-run, or edit
    echo           DATABASE_URL/REDIS_URL following backend\.env.local.example.
    echo.
  )
)

if not exist "%ROOT_DIR%backend\.venv\Scripts\python.exe" (
  echo.
  echo [ERROR] backend\.venv 가상환경을 찾을 수 없습니다. backend 폴더에서 먼저 실행하세요:
  echo           python -m venv .venv
  echo           .venv\Scripts\pip install -r requirements.txt
  echo.
  pause
  exit /b 1
)

rem venv 폴더는 있어도, 만들 때 쓴 Python이 삭제됐거나 프로젝트 폴더를 옮겼으면
rem python.exe가 "No Python at ..." 오류로 실행 자체가 안 된다 - 미리 감지해서 안내.
"%ROOT_DIR%backend\.venv\Scripts\python.exe" -c "import sys" >nul 2>&1
if errorlevel 1 (
  echo.
  echo [ERROR] backend\.venv 가상환경이 깨져 있습니다.
  echo         ^(만들 때 사용한 Python이 삭제됐거나, 프로젝트 폴더를 이동한 경우^)
  echo         backend 폴더에서 venv를 다시 만들어 주세요:
  echo           rmdir /s /q .venv
  echo           python -m venv .venv
  echo           .venv\Scripts\pip install -r requirements.txt
  echo.
  pause
  exit /b 1
)

echo [1/3] Backend starting at http://localhost:%BACKEND_PORT%
rem --reload-exclude "data/*" 는 쓰면 안 된다: uvicorn CLI(click)가 Windows에서
rem 와일드카드를 파일 목록으로 확장해 "unexpected extra arguments"로 죽는다.
rem 감시 대상을 소스 폴더(app)로 한정하면 data/ 변경도 자연히 무시된다.
start "Backend" cmd /k "cd /d "%ROOT_DIR%backend" && .venv\Scripts\python.exe -m uvicorn app.main:app --reload --reload-dir app --port %BACKEND_PORT%"

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
