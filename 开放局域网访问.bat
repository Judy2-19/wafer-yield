@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

net session >nul 2>&1
if errorlevel 1 (
  echo 正在请求管理员权限，请在 Windows 提示中选择“是”...
  powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
  exit /b
)

netsh advfirewall firewall delete rule name="晶圆判定系统 TCP 8000" >nul 2>&1
netsh advfirewall firewall add rule name="晶圆判定系统 TCP 8000" dir=in action=allow protocol=TCP localport=8000 profile=domain,private
if errorlevel 1 (
  echo [错误] 防火墙规则添加失败。
) else (
  echo [完成] 已允许域网络和专用网络访问 TCP 8000。
  echo 请勿把本系统直接暴露到公网。
)
pause
endlocal
