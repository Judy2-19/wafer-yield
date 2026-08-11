@echo off
cd /d "%~dp0"
title WaferFrontend5173
if defined WAFER_NODE_DIR (
  set "PATH=%WAFER_NODE_DIR%;%PATH%"
)
echo Frontend dev server. Do not close this window.
echo URL: http://localhost:5173/
echo.
call npm run dev
echo.
echo [WARN] Frontend exited. Press any key to close.
pause
