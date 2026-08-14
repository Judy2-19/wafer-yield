@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Wafer Yield System - Start
set "LOG=%cd%\startup-diagnostic.txt"
>"%LOG%" echo STARTUP_BEGIN
>>"%LOG%" echo DIRECTORY=%cd%
echo ================================================
echo   Wafer Yield System - One Click Start
echo ================================================
echo [1/3] CHECKING_PACKAGE

if not exist "runtime\python\python.exe" goto missing_runtime
if not exist "runtime\site-packages\fastapi" goto missing_runtime
if not exist "backend\app\main.py" goto missing_files
if not exist "frontend\dist\index.html" goto missing_files

set "PYTHONPATH=%cd%\runtime\site-packages"
set "WAFER_PYTHON=%cd%\runtime\python\python.exe"
echo [2/3] CHECKING_OFFLINE_PYTHON
"%WAFER_PYTHON%" -c "import fastapi, uvicorn; print('RUNTIME_OK')" >>"%LOG%" 2>&1
if errorlevel 1 goto runtime_failed

set "WAFER_NO_PAUSE=1"
echo [3/3] STARTING_SERVER
call "%cd%\启动系统.bat"
set "START_RESULT=%ERRORLEVEL%"
>>"%LOG%" echo START_RESULT=%START_RESULT%
if not "%START_RESULT%"=="0" goto start_failed

echo.
echo System started. This window can now be closed.
echo Diagnostic log: %LOG%
goto finish

:missing_runtime
>>"%LOG%" echo MISSING_RUNTIME
echo.
echo ERROR: Offline runtime is missing.
echo Extract the COMPLETE ZIP to a normal folder, then run this file again.
goto failed

:missing_files
>>"%LOG%" echo MISSING_SYSTEM_FILES
echo.
echo ERROR: System files are incomplete.
echo Extract the COMPLETE ZIP to a normal folder, then run this file again.
goto failed

:runtime_failed
>>"%LOG%" echo RUNTIME_IMPORT_FAILED
echo.
echo ERROR: Python runtime was blocked or damaged.
echo Check antivirus quarantine, then send startup-diagnostic.txt to support.
goto failed

:start_failed
>>"%LOG%" echo SERVER_START_FAILED
echo.
echo ERROR: Server failed to start.
if exist "runtime\server.err.log" type "runtime\server.err.log"
echo Send startup-diagnostic.txt and runtime\server.err.log to support.
goto failed

:failed
echo Diagnostic log: %LOG%

:finish
echo.
pause
exit /b %START_RESULT%
