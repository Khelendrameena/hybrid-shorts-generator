@echo off
REM Start backend (FastAPI :8000) + frontend (Next.js :3000) + Ollama if needed.
setlocal
cd /d %~dp0
set USE_TF=0
where ollama >nul 2>nul && (
  curl -s http://localhost:11434/api/tags >nul 2>nul || start "Ollama" /min ollama serve
)
call .venv\Scripts\activate.bat
start "Shorts-Backend" /min python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
cd frontend
start "Shorts-Frontend" /min npm run dev
cd ..
echo Waiting for services ...
timeout /t 6 >nul
start http://localhost:3000
echo.
echo  App:      http://localhost:3000
echo  API docs: http://localhost:8000/docs
echo  Close the Shorts-Backend / Shorts-Frontend windows to stop.
pause
