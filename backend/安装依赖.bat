@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"
chcp 65001 >nul

echo === 晶圆台良品率 - 后端依赖安装 ===

set "UV_BIN=%USERPROFILE%\.local\bin"
set "PATH=%UV_BIN%;%LocalAppData%\Programs\uv;%PATH%"

where uv >nul 2>&1
if errorlevel 1 (
  echo 未检测到 uv，正在安装...
  powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://astral.sh/uv/install.ps1 | iex"
  set "PATH=%UV_BIN%;%LocalAppData%\Programs\uv;%PATH%"
)
where uv >nul 2>&1
if errorlevel 1 (
  echo [错误] 需要 uv。请安装后重试: https://docs.astral.sh/uv/
  pause
  exit /b 1
)

echo 安装 Python 3.12 ...
uv python install 3.12
if errorlevel 1 (
  echo [错误] Python 安装失败
  pause
  exit /b 1
)

set "NEED_VENV=1"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" -c "import sys; print(sys.version)" >nul 2>&1
  if not errorlevel 1 set "NEED_VENV=0"
)

if "!NEED_VENV!"=="1" (
  echo 创建虚拟环境 .venv ...
  if exist ".venv" rmdir /s /q ".venv" 2>nul
  uv venv .venv --python 3.12
  if errorlevel 1 (
    echo [错误] uv venv 失败
    pause
    exit /b 1
  )
)

echo 安装依赖 ...
set "UV_PROJECT_ENVIRONMENT=%cd%\.venv"
uv pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
if errorlevel 1 uv pip install -r requirements.txt
if errorlevel 1 (
  ".venv\Scripts\python.exe" -m ensurepip --upgrade >nul 2>&1
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
)
if errorlevel 1 (
  echo [错误] 依赖安装失败
  pause
  exit /b 1
)

echo.
echo 安装完成。双击 run.bat 或上级目录「一键启动.bat」即可运行。
pause
endlocal
