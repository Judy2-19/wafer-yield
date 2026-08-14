@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

set "PID_FILE=%cd%\runtime\server.pid"
if not exist "%PID_FILE%" goto no_pid
set /p SERVER_PID=<"%PID_FILE%"
if not defined SERVER_PID goto no_pid

"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -Command "$p=Get-Process -Id %SERVER_PID% -ErrorAction SilentlyContinue; if($p){ Stop-Process -Id %SERVER_PID% -Force; exit 0 } else { exit 2 }"
if errorlevel 2 (
  echo 服务进程已经不存在。
) else if errorlevel 1 (
  echo [错误] 无法停止服务 PID %SERVER_PID%。
) else (
  echo 系统服务已停止。
)
del /q "%PID_FILE%" >nul 2>&1
if not "%WAFER_NO_PAUSE%"=="1" pause
exit /b 0

:no_pid
echo 未找到本安装包启动的服务进程。
echo 如端口 8000 仍被占用，请联系管理员确认后处理。
if not "%WAFER_NO_PAUSE%"=="1" pause
exit /b 0
