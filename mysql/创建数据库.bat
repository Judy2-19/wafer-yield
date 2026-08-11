@echo off
chcp 65001 >nul
cd /d %~dp0

set "MYSQL=C:\Program Files\MySQL\MySQL Server 8.4\bin\mysql.exe"
if not exist "%MYSQL%" (
  echo 未找到 mysql.exe，请确认已安装 MySQL Server 8.4
  pause
  exit /b 1
)

echo === 创建 mg_nano 数据库与表 ===
echo 将连接本机 127.0.0.1:3306，用户 root
set /p MYSQL_PWD=请输入 MySQL root 密码: 

"%MYSQL%" -h 127.0.0.1 -P 3306 -u root -p%MYSQL_PWD% < init_mg_nano.sql
if errorlevel 1 (
  echo.
  echo 执行失败。请核对密码，或用 MySQL Workbench 打开 init_mg_nano.sql 执行。
  set MYSQL_PWD=
  pause
  exit /b 1
)

echo.
echo 成功。已创建 mg_nano.summaryhead / summarydetail（对齐 head.csv / detail.csv）。
echo 本程序只处理 WaveLength=1311 的明细。
echo.
echo 请回到网页「数据连接」：
echo   主机 127.0.0.1  端口 3306  数据库 mg_nano  用户 root
echo   关闭 Mock → 测试连接 → 保存并加载
set MYSQL_PWD=
pause
