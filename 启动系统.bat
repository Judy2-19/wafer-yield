@echo off
chcp 65001 >nul
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"

set "ROOT=%cd%"
set "BACKEND=%ROOT%\backend"
if not defined WAFER_PYTHON set "WAFER_PYTHON=%BACKEND%\.venv\Scripts\python.exe"
if not defined WAFER_HOST set "WAFER_HOST=0.0.0.0"
if not defined WAFER_PORT set "WAFER_PORT=8000"
set "PYTHON=%WAFER_PYTHON%"
set "RUNTIME=%ROOT%\runtime"
set "PID_FILE=%RUNTIME%\server.pid"

if not exist "%PYTHON%" (
  echo [错误] 尚未安装。请先双击“安装并启动.bat”。
  if not "%WAFER_NO_PAUSE%"=="1" pause
  exit /b 1
)
if not exist "%ROOT%\frontend\dist\index.html" (
  echo [错误] 缺少 frontend\dist\index.html，安装包不完整。
  if not "%WAFER_NO_PAUSE%"=="1" pause
  exit /b 1
)
if not exist "%RUNTIME%" mkdir "%RUNTIME%"

curl.exe -fsS --max-time 2 http://127.0.0.1:%WAFER_PORT%/api/health >nul 2>&1
if not errorlevel 1 goto ready

netstat -ano | findstr ":%WAFER_PORT% " | findstr "LISTENING" >nul 2>&1
if not errorlevel 1 (
  echo [错误] 端口 %WAFER_PORT% 已被其他程序占用，请先关闭占用程序。
  if not "%WAFER_NO_PAUSE%"=="1" pause
  exit /b 1
)

echo 正在后台启动服务...
REM 某些 Windows 环境同时存在 Path/PATH；重设一次可避免 PowerShell Start-Process 冲突。
set "WAFER_RUNTIME_PATH=%PATH%"
set "Path="
set "PATH=%WAFER_RUNTIME_PATH%"
"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -Command "$argsList=@('-m','uvicorn','app.main:app','--host','%WAFER_HOST%','--port','%WAFER_PORT%'); $p=Start-Process -FilePath '%PYTHON%' -ArgumentList $argsList -WorkingDirectory '%BACKEND%' -WindowStyle Hidden -PassThru -RedirectStandardOutput '%RUNTIME%\server.out.log' -RedirectStandardError '%RUNTIME%\server.err.log'; Set-Content -LiteralPath '%PID_FILE%' -Value $p.Id -Encoding ascii"
if errorlevel 1 (
  echo [错误] 服务启动命令执行失败。
  if not "%WAFER_NO_PAUSE%"=="1" pause
  exit /b 1
)

set /a WAIT_COUNT=0
:wait_health
set /a WAIT_COUNT+=1
curl.exe -fsS --max-time 2 http://127.0.0.1:%WAFER_PORT%/api/health >nul 2>&1
if not errorlevel 1 goto ready
if !WAIT_COUNT! GEQ 30 (
  echo [错误] 服务未能在 30 秒内启动。
  echo 请查看 runtime\server.err.log。
  if not "%WAFER_NO_PAUSE%"=="1" pause
  exit /b 1
)
"%SystemRoot%\System32\ping.exe" 127.0.0.1 -n 2 >nul
goto wait_health

:ready
if not exist "%PID_FILE%" for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":%WAFER_PORT% " ^| findstr "LISTENING"') do >"%PID_FILE%" echo %%p
>"%ROOT%\访问地址.txt" echo 本机：http://127.0.0.1:%WAFER_PORT%/
"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -Command "$ips=[Net.Dns]::GetHostAddresses([Net.Dns]::GetHostName()) | Where-Object {$_.AddressFamily -eq [Net.Sockets.AddressFamily]::InterNetwork} | ForEach-Object {$_.IPAddressToString} | Where-Object {$_ -ne '127.0.0.1' -and $_ -notlike '169.254.*'} | Sort-Object -Unique; foreach($ip in $ips){ Add-Content -LiteralPath '%ROOT%\访问地址.txt' -Value ('同事访问：http://' + $ip + ':%WAFER_PORT%/') -Encoding utf8 }"

echo.
echo 系统已启动。
echo 本机地址：http://127.0.0.1:%WAFER_PORT%/
echo 同事访问地址已写入“访问地址.txt”。
echo 首次允许同事访问时，请以管理员身份运行“开放局域网访问.bat”。
if not "%WAFER_NO_BROWSER%"=="1" start "" http://127.0.0.1:%WAFER_PORT%/
echo.
if not "%WAFER_NO_PAUSE%"=="1" pause
exit /b 0
