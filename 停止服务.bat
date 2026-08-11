@echo off
chcp 65001 >nul
echo 正在尝试停止本系统占用的 8000 / 5173 端口...

for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":8000 " ^| findstr "LISTENING"') do (
  echo 结束后端 PID %%p
  taskkill /PID %%p /F >nul 2>&1
)
for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":5173 " ^| findstr "LISTENING"') do (
  echo 结束前端 PID %%p
  taskkill /PID %%p /F >nul 2>&1
)

echo 完成。
pause
