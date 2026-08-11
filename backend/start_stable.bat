@echo off
cd /d "%~dp0"
title WaferBackend8000

if not exist ".venv\Scripts\python.exe" (
  echo [ERROR] .venv missing. Run one-click start bat first.
  pause
  exit /b 1
)

echo Backend stable mode (no --reload). Do not close this window.
echo API: http://127.0.0.1:8000/api/health
echo.

:loop
".\.venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --timeout-keep-alive 75
set "EC=%ERRORLEVEL%"
echo.
echo [WARN] Backend exited code=%EC%. Restarting in 3 seconds...
echo        If this keeps happening, copy the error text above.
timeout /t 3 /nobreak >nul
goto loop
