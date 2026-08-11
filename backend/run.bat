@echo off
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo [错误] 未找到虚拟环境 .venv
  echo 请先运行: 安装依赖.bat
  pause
  exit /b 1
)

echo 稳定模式启动（无热重载，适合工程师电脑）
echo 开发改代码自动重载请用 run_dev.bat
".venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --timeout-keep-alive 75
