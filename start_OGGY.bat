@echo off
cd /d "%~dp0"

start "" cmd /c "timeout /t 2 /nobreak >nul & start http://127.0.0.1:5050"

python app.py

pause
