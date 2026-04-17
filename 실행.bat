@echo off
chcp 65001 > nul
echo ========================================
echo   Stock Chart Helper - 실행 스크립트
echo ========================================
echo.

echo [1/2] 백엔드 서버 시작 중... (http://localhost:8000)
start "SCH Backend" cmd /k "cd /d %~dp0backend && python -m uvicorn app.main:app --reload --port 8000"

echo 백엔드 시작 대기 중 (3초)...
timeout /t 3 /nobreak > nul

echo [2/2] 프론트엔드 서버 시작 중... (http://localhost:5173)
start "SCH Frontend" cmd /k "cd /d %~dp0frontend && npm run dev"

echo.
echo ========================================
echo  서버가 시작되었습니다!
echo  브라우저에서 열기: http://localhost:5173
echo  API 문서: http://localhost:8000/docs
echo ========================================
echo.
pause
