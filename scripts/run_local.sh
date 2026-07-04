#!/usr/bin/env bash
# 로컬 데스크톱 모드 실행 — Render/Vercel 없이 이 컴퓨터에서만 돌린다.
# Postgres/Redis 서버가 필요 없다 (SQLite + 메모리 캐시로 대체).
#
# 사용법:
#   ./scripts/run_local.sh
#
# 처음 실행이면 backend venv/의존성 설치, frontend npm install, .env 생성까지
# 자동으로 해준다. 이후 실행부터는 서버 두 개만 띄우고 브라우저를 연다.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
FRONTEND_DIR="$ROOT_DIR/frontend"
BACKEND_PORT="${BACKEND_PORT:-8001}"
FRONTEND_PORT="${FRONTEND_PORT:-5173}"

echo "=== Stock Chart Helper — 로컬 데스크톱 모드 ==="

# ── 1) backend 준비 ──────────────────────────────────────────────
cd "$BACKEND_DIR"
if [ ! -d .venv ]; then
  echo "[backend] 가상환경 생성 중..."
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
if [ ! -f .venv/.deps_installed ] || [ requirements.txt -nt .venv/.deps_installed ]; then
  echo "[backend] 의존성 설치 중... (처음 한 번만, 몇 분 걸릴 수 있음)"
  pip install -q -r requirements.txt
  touch .venv/.deps_installed
fi
if [ ! -f .env ]; then
  echo "[backend] .env 없음 — .env.local.example로 생성 (SQLite, 스케줄러 꺼짐)"
  cp .env.local.example .env
elif grep -qE '^DATABASE_URL=postgresql' .env; then
  echo ""
  echo "[경고] backend/.env 가 Postgres 서버를 쓰도록 설정되어 있습니다."
  echo "       (로컬 데스크톱 모드는 SQLite를 씁니다 — Postgres 서버가 없으면"
  echo "        API 요청이 전부 실패하고 브라우저에는 CORS 오류로만 보입니다.)"
  echo "       SQLite로 바꾸려면: backend/.env 를 지우고 다시 실행하거나,"
  echo "       backend/.env.local.example 을 참고해 DATABASE_URL/REDIS_URL 값을 고치세요."
  echo ""
fi

# ── 2) frontend 준비 ─────────────────────────────────────────────
cd "$FRONTEND_DIR"
if [ ! -d node_modules ]; then
  echo "[frontend] npm install 중... (처음 한 번만)"
  npm install --silent
fi

# ── 3) 서버 두 개 실행 ────────────────────────────────────────────
cleanup() {
  echo ""
  echo "종료 중..."
  [ -n "${BACKEND_PID:-}" ] && kill "$BACKEND_PID" 2>/dev/null || true
  [ -n "${FRONTEND_PID:-}" ] && kill "$FRONTEND_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

cd "$BACKEND_DIR"
echo "[1/2] Backend 시작 중... (http://localhost:$BACKEND_PORT)"
# shellcheck disable=SC1091
source .venv/bin/activate
python -m uvicorn app.main:app --port "$BACKEND_PORT" &
BACKEND_PID=$!

cd "$FRONTEND_DIR"
echo "[2/2] Frontend 시작 중... (http://localhost:$FRONTEND_PORT)"
npm run dev -- --port "$FRONTEND_PORT" &
FRONTEND_PID=$!

# ── 4) 준비될 때까지 대기 후 브라우저 열기 ───────────────────────
wait_for_url() {
  local url="$1" label="$2" tries=0
  until curl -s -o /dev/null "$url" 2>/dev/null; do
    tries=$((tries + 1))
    if [ "$tries" -ge 60 ]; then
      echo "  - $label 준비 확인 실패 (계속 진행은 함, 창을 직접 확인하세요)"
      return 1
    fi
    sleep 1
  done
  echo "  - $label 준비 완료"
}

wait_for_url "http://127.0.0.1:$BACKEND_PORT/health" "Backend" || true
wait_for_url "http://127.0.0.1:$FRONTEND_PORT" "Frontend" || true

URL="http://localhost:$FRONTEND_PORT"
echo ""
echo "Backend:  http://localhost:$BACKEND_PORT"
echo "Frontend: $URL"
echo "브라우저를 여는 중... (Ctrl+C로 종료)"

if command -v open >/dev/null 2>&1; then
  open "$URL"        # macOS
elif command -v xdg-open >/dev/null 2>&1; then
  xdg-open "$URL"     # Linux
fi

wait
