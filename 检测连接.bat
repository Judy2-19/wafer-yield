@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

echo ==================================================
echo   晶圆判定系统 - 连接检测
echo ==================================================
echo.
echo [1/3] 检查安装文件...
if not exist "backend\.venv\Scripts\python.exe" echo [失败] 尚未完成首次安装
if not exist "frontend\dist\index.html" echo [失败] 前端文件缺失
if exist "backend\.venv\Scripts\python.exe" if exist "frontend\dist\index.html" echo [正常] 安装文件完整

echo.
echo [2/3] 检查后台接口...
curl.exe -fsS --max-time 5 http://127.0.0.1:8000/api/health
if errorlevel 1 (echo. & echo [失败] 无法访问后台接口) else (echo. & echo [正常] 后台接口可用)

echo.
echo [3/3] 检查系统页面...
curl.exe -fsS -o NUL -w "HTTP %%{http_code}\n" --max-time 5 http://127.0.0.1:8000/

echo.
if exist "访问地址.txt" type "访问地址.txt"
echo.
echo 远端同事无法访问时，请检查：服务器未休眠、防火墙已开放、双方网络互通。
pause
endlocal
