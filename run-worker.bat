@echo off
REM Laptop worker (Windows se WSL use kar rahe ho to run-worker.sh chalao;
REM ye .bat sirf native Windows Python setup ke liye hai)
cd /d %~dp0
if "%CLOUD_URL%"=="" set /p CLOUD_URL=Cloud URL: 
if "%DASHBOARD_PASSWORD%"=="" set /p DASHBOARD_PASSWORD=Dashboard password: 
if exist .venv\Scripts\activate.bat call .venv\Scripts\activate.bat
python worker.py %*
pause
