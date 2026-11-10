@echo off
REM ============================================================
REM  Hybrid AI YouTube Shorts Generator - Windows setup
REM  Targets: Windows 11, RTX 3050 4GB, 16GB RAM
REM ============================================================
setlocal
cd /d %~dp0
echo [1/6] Checking Python 3.10+ ...
python --version 2>nul | findstr /R "3\.1[0-9] 3\.[2-9][0-9]" >nul
if errorlevel 1 (
  echo   Python 3.10+ not found. Install from https://www.python.org/downloads/ and re-run.
  pause & exit /b 1
)
echo [2/6] Checking FFmpeg ...
where ffmpeg >nul 2>nul || (
  echo   FFmpeg not found. Install:  winget install Gyan.FFmpeg
  echo   Then close and reopen this window and run setup.bat again.
  pause & exit /b 1
)
echo [3/6] Creating virtual environment ...
if not exist .venv ( python -m venv .venv )
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
echo [4/6] Installing Python packages (this includes PyTorch for Laya - a few minutes) ...
pip install -r requirements.txt
if errorlevel 1 ( echo   pip install failed - see errors above. & pause & exit /b 1 )
echo [5/6] Checking Ollama ...
where ollama >nul 2>nul || (
  echo   Ollama not found. Install from https://ollama.com/download then re-run setup.bat
  pause & exit /b 1
)
echo   Pulling Ollama model qwen3:4b (~2.5 GB, one time) ...
ollama pull qwen3:4b
echo [6/6] Installing frontend ...
cd frontend
if not exist node_modules ( call npm install )
cd ..
if not exist .env ( copy .env.example .env >nul )
echo.
echo ============================================================
echo  SETUP COMPLETE.  Start the app with:  run.bat
echo  First run downloads two local models automatically:
echo    - Laya multilingual (~1.3 GB, Hugging Face cache)
echo    - Faster-Whisper "small" (~0.5 GB)
echo ============================================================
pause
