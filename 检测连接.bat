@echo off
setlocal
cd /d "%~dp0"
set "CURL=%SystemRoot%\System32\curl.exe"
set "PATH=%SystemRoot%\System32;%PATH%"

echo ============================================
echo   Backend connection check
echo ============================================
echo.

if not exist "mock\eav_rows.json" (
  echo [FAIL] mock\eav_rows.json missing
  echo        Copy the whole "mock" folder next to backend/frontend
) else (
  echo [OK] mock\eav_rows.json exists
)

echo.
echo Testing http://127.0.0.1:8000/api/health ...
if exist "%CURL%" (
  "%CURL%" -sS --max-time 5 http://127.0.0.1:8000/api/health
  echo.
  if errorlevel 1 (
    echo [FAIL] Cannot reach backend on port 8000
    echo        Make sure "Wafer-Backend-8000" window is running
  ) else (
    echo [OK] health OK
  )
) else (
  echo [WARN] curl.exe not found, open browser:
  echo        http://127.0.0.1:8000/api/health
)

echo.
echo Testing http://127.0.0.1:8000/api/wafers ...
if exist "%CURL%" (
  "%CURL%" -sS --max-time 10 http://127.0.0.1:8000/api/wafers
  echo.
)

echo.
echo Testing frontend http://localhost:5173/ ...
if exist "%CURL%" (
  "%CURL%" -sS -o NUL -w "HTTP %%{http_code}\n" --max-time 5 http://localhost:5173/
)

echo.
echo If health OK but page empty: click "重连后端" or open
echo   http://127.0.0.1:8000/docs
echo.
pause
endlocal
