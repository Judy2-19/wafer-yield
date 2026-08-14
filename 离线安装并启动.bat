@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
title 晶圆判定系统 - 离线启动
if not exist "runtime\python\python.exe" goto missing
if not exist "runtime\site-packages\fastapi" goto missing
set "PYTHONPATH=%cd%\runtime\site-packages"
set "WAFER_PYTHON=%cd%\runtime\python\python.exe"
call "%cd%\启动系统.bat"
exit /b %errorlevel%
:missing
echo [ERROR] Offline runtime is incomplete. Extract the complete ZIP and retry.
pause
exit /b 1
