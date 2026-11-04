@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo [FrameFlow] Creating local Python environment...
  py -3 -m venv .venv
  if errorlevel 1 goto :error
  .venv\Scripts\python.exe -m pip install -r requirements.txt
  if errorlevel 1 goto :error
)
if not exist ".env" (
  copy ".env.example" ".env" >nul
  echo [FrameFlow] Optional .env created. You can configure all models in the web page.
)
start "FrameFlow" http://127.0.0.1:8000
.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
goto :eof
:error
echo [FrameFlow] Setup failed. See README.md for installation instructions.
pause
exit /b 1
