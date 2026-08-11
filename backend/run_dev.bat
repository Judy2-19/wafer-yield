@echo off
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo [错误] 未找到虚拟环境 .venv
  echo 请先运行: 安装依赖.bat
  pause
  exit /b 1
)

REM 仅开发用：热重载，排除 data 目录避免写库触发重启
".venv\Scripts\python.exe" -m uvicorn app.main:app --reload --reload-dir app --host 127.0.0.1 --port 8000
