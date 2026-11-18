@echo off
REM One-command local start for Windows: http://localhost:8000
cd /d %~dp0
if not exist backend\.venv python -m venv backend\.venv
call backend\.venv\Scripts\activate.bat
pip install -q -r backend\requirements.txt
cd frontend
call npm install --silent
call npm run build
cd ..\backend
echo InsightFlow AI running at http://localhost:8000  (demo login: demo@insightflow.ai / demo1234)
uvicorn app.main:app --host 0.0.0.0 --port 8000
