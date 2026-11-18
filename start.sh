#!/usr/bin/env bash
# One-command local start: builds the frontend and serves everything on http://localhost:8000
set -e
cd "$(dirname "$0")"
if [ ! -d backend/.venv ]; then
  python3 -m venv backend/.venv
fi
source backend/.venv/bin/activate
pip install -q -r backend/requirements.txt
(cd frontend && npm install --silent && npm run build)
cd backend
echo "InsightFlow AI running at http://localhost:8000  (demo login: demo@insightflow.ai / demo1234)"
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
