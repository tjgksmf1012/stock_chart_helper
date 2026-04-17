#!/usr/bin/env bash
# Quick local dev setup (without Docker)
set -e

echo "=== Stock Chart Helper — Local Setup ==="

# Backend
echo "[1/3] Setting up backend..."
cd backend
python -m venv .venv
source .venv/Scripts/activate 2>/dev/null || source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
echo "  Backend dependencies installed."
cd ..

# Frontend
echo "[2/3] Setting up frontend..."
cd frontend
npm install
echo "  Frontend dependencies installed."
cd ..

echo "[3/3] Done!"
echo ""
echo "To start development:"
echo "  Backend:  cd backend && uvicorn app.main:app --reload"
echo "  Frontend: cd frontend && npm run dev"
echo ""
echo "Or use Docker: docker compose up"
