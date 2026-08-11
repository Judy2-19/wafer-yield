@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"

title Wafer Yield One Click Start
echo ============================================
echo   Wafer Yield - Install and Start
echo ============================================
echo.

set "ROOT=%cd%"
set "BACKEND=%ROOT%\backend"
set "FRONTEND=%ROOT%\frontend"
set "TOOLS_NODE=%ROOT%\tools\node"
set "MOCK_JSON=%ROOT%\mock\eav_rows.json"
set "PF86=%ProgramFiles(x86)%"

if not exist "%MOCK_JSON%" (
  echo [ERROR] Missing mock\eav_rows.json
  echo         Copy folder mock next to backend and frontend, then rerun.
  pause
  exit /b 1
)
echo [0/5] mock data OK

set "UV_BIN=%USERPROFILE%\.local\bin"
set "PATH=%SystemRoot%\System32;%SystemRoot%;%SystemRoot%\System32\Wbem;%UV_BIN%;%LocalAppData%\Programs\uv;%PATH%"
set "CURL=%SystemRoot%\System32\curl.exe"
set "TAR=%SystemRoot%\System32\tar.exe"
set "PS=%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe"
set "NODE_EXE="
set "NPM_CMD="

where uv >nul 2>&1
if errorlevel 1 (
  echo [1/5] uv not found, installing...
  if exist "%PS%" (
    "%PS%" -NoProfile -ExecutionPolicy Bypass -Command "irm https://astral.sh/uv/install.ps1 | iex"
  ) else (
    echo [ERROR] PowerShell missing, cannot install uv automatically.
    echo Install uv from https://docs.astral.sh/uv/ then rerun.
    pause
    exit /b 1
  )
  set "PATH=%UV_BIN%;%LocalAppData%\Programs\uv;%PATH%"
  where uv >nul 2>&1
  if errorlevel 1 (
    echo [ERROR] uv install failed. Check network.
    pause
    exit /b 1
  )
) else (
  echo [1/5] uv OK
)
for /f "delims=" %%v in ('uv --version 2^>nul') do echo       %%v

echo [2/5] Backend Python...
pushd "%BACKEND%"
if errorlevel 1 (
  echo [ERROR] backend folder not found
  pause
  exit /b 1
)

echo       Install Python 3.12 via uv...
uv python install 3.12
if errorlevel 1 (
  echo [ERROR] Python 3.12 install failed
  popd
  pause
  exit /b 1
)

set "NEED_VENV=1"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" -c "import sys; print(sys.version)" >nul 2>&1
  if not errorlevel 1 set "NEED_VENV=0"
)

if "!NEED_VENV!"=="1" (
  echo       Creating .venv ...
  if exist ".venv" rmdir /s /q ".venv" 2>nul
  uv venv .venv --python 3.12
  if errorlevel 1 (
    echo [ERROR] uv venv failed
    popd
    pause
    exit /b 1
  )
) else (
  echo       .venv OK
)

".venv\Scripts\python.exe" --version
if errorlevel 1 (
  echo [ERROR] venv python broken
  popd
  pause
  exit /b 1
)

echo       Install backend deps...
set "UV_PROJECT_ENVIRONMENT=%BACKEND%\.venv"
uv pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
if errorlevel 1 uv pip install -r requirements.txt
if errorlevel 1 (
  ".venv\Scripts\python.exe" -m ensurepip --upgrade >nul 2>&1
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
)
if errorlevel 1 ".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
  echo [ERROR] backend deps failed
  popd
  pause
  exit /b 1
)
echo       Backend OK
popd

echo [3/5] Node.js...
call :refresh_path
call :find_node
if defined NODE_EXE goto node_ok

echo       Node not found. Try winget...
where winget >nul 2>&1
if not errorlevel 1 (
  winget install -e --id OpenJS.NodeJS.LTS --accept-package-agreements --accept-source-agreements
  call :refresh_path
  call :find_node
  if defined NODE_EXE goto node_ok
)

echo       Download portable Node to tools\node ...
call :install_portable_node
call :find_node
if defined NODE_EXE goto node_ok

echo [ERROR] Cannot install Node.js automatically.
echo Please install Node.js LTS from https://nodejs.org/
echo Check Add to PATH, then rerun this script.
pause
exit /b 1

:node_ok
echo       Node.js OK
for /f "delims=" %%v in ('"%NODE_EXE%" -v') do echo       node %%v
echo       Using: %NODE_EXE%

echo [4/5] Frontend deps...
if not exist "%FRONTEND%\node_modules\vite" (
  echo       npm install...
  pushd "%FRONTEND%"
  call "%NPM_CMD%" install --registry=https://registry.npmmirror.com
  if errorlevel 1 call "%NPM_CMD%" install
  popd
  if errorlevel 1 (
    echo [ERROR] npm install failed
    pause
    exit /b 1
  )
) else (
  echo       Frontend deps OK
)

echo [5/5] Starting services...

netstat -ano | findstr ":8000 " | findstr "LISTENING" >nul 2>&1
if not errorlevel 1 echo       Note: port 8000 already in use
netstat -ano | findstr ":5173 " | findstr "LISTENING" >nul 2>&1
if not errorlevel 1 echo       Note: port 5173 already in use

for %%I in ("%NODE_EXE%") do set "WAFER_NODE_DIR=%%~dpI"

REM Do NOT put full PATH into start cmdline. Program Files (x86) breaks parsing.
REM Child windows inherit WAFER_NODE_DIR; start_dev.bat prepends it.
start "WaferBackend8000" /D "%BACKEND%" cmd /k call start_stable.bat

echo       Waiting for backend http://127.0.0.1:8000/api/health ...
set /a _bwait=0
:wait_back
set /a _bwait+=1
if exist "%CURL%" (
  "%CURL%" -fsS --max-time 1 http://127.0.0.1:8000/api/health >nul 2>&1
  if not errorlevel 1 goto back_ok
)
if !_bwait! GEQ 40 (
  echo       [WARN] backend health not ready, still starting frontend...
  goto start_front
)
timeout /t 1 /nobreak >nul
goto wait_back
:back_ok
echo       Backend ready
if exist "%CURL%" (
  REM Do NOT force-mock here — keep user's MySQL config (mige_nano etc.)
  "%CURL%" -sS --max-time 8 http://127.0.0.1:8000/api/wafers >nul 2>&1
  if errorlevel 1 (
    echo       [WARN] /api/wafers failed. Run check bat for details.
  ) else (
    echo       /api/wafers OK
  )
)

:start_front
start "WaferFrontend5173" /D "%FRONTEND%" cmd /k call start_dev.bat

echo.
echo Waiting for frontend...
set /a _wait=0
:wait_front
set /a _wait+=1
if exist "%CURL%" (
  "%CURL%" -fsS --max-time 1 http://localhost:5173/ >nul 2>&1
  if not errorlevel 1 goto open_browser
) else if exist "%PS%" (
  "%PS%" -NoProfile -Command "try { (Invoke-WebRequest -Uri 'http://localhost:5173/' -UseBasicParsing -TimeoutSec 1).StatusCode } catch { exit 1 }" >nul 2>&1
  if not errorlevel 1 goto open_browser
)
if !_wait! GEQ 60 goto open_browser
timeout /t 1 /nobreak >nul
goto wait_front

:open_browser
start "" http://localhost:5173/

echo.
echo ============================================
echo   DONE
echo   Frontend: http://localhost:5173/
echo   Backend:  http://127.0.0.1:8000/docs
echo   Close the two black windows to stop.
echo ============================================
echo.
pause
exit /b 0

:refresh_path
for /f "usebackq tokens=2*" %%A in (`reg query "HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Environment" /v Path 2^>nul`) do set "SYS_PATH=%%B"
for /f "usebackq tokens=2*" %%A in (`reg query "HKCU\Environment" /v Path 2^>nul`) do set "USR_PATH=%%B"
if defined SYS_PATH set "PATH=%SystemRoot%\System32;%SystemRoot%;%SystemRoot%\System32\Wbem;%SYS_PATH%"
if defined USR_PATH set "PATH=%PATH%;%USR_PATH%"
set "PATH=%UV_BIN%;%LocalAppData%\Programs\uv;%ProgramFiles%\nodejs;%PF86%\nodejs;%TOOLS_NODE%;%PATH%"
exit /b 0

:find_node
set "NODE_EXE="
set "NPM_CMD="
if exist "%TOOLS_NODE%\node.exe" (
  set "NODE_EXE=%TOOLS_NODE%\node.exe"
  set "NPM_CMD=%TOOLS_NODE%\npm.cmd"
  exit /b 0
)
if exist "%ProgramFiles%\nodejs\node.exe" (
  set "NODE_EXE=%ProgramFiles%\nodejs\node.exe"
  set "NPM_CMD=%ProgramFiles%\nodejs\npm.cmd"
  exit /b 0
)
if exist "%PF86%\nodejs\node.exe" (
  set "NODE_EXE=%PF86%\nodejs\node.exe"
  set "NPM_CMD=%PF86%\nodejs\npm.cmd"
  exit /b 0
)
for /f "delims=" %%i in ('where node 2^>nul') do set "NODE_EXE=%%i"
if defined NODE_EXE (
  set "NPM_CMD=npm.cmd"
  exit /b 0
)
exit /b 1

:install_portable_node
set "NODE_VER=v22.14.0"
set "ZIP_NAME=node-%NODE_VER%-win-x64.zip"
set "ZIP_PATH=%TEMP%\%ZIP_NAME%"
set "URL1=https://npmmirror.com/mirrors/node/%NODE_VER%/%ZIP_NAME%"
set "URL2=https://nodejs.org/dist/%NODE_VER%/%ZIP_NAME%"
set "EXTRACT=%ROOT%\tools\_node_extract"

if not exist "%ROOT%\tools" mkdir "%ROOT%\tools"
if exist "%TOOLS_NODE%" rmdir /s /q "%TOOLS_NODE%" 2>nul
if exist "%EXTRACT%" rmdir /s /q "%EXTRACT%" 2>nul
if exist "%ZIP_PATH%" del /f /q "%ZIP_PATH%" >nul 2>&1

echo       Downloading %ZIP_NAME% ...
set "DL_OK=0"
if exist "%CURL%" (
  "%CURL%" -L --retry 3 --connect-timeout 20 -o "%ZIP_PATH%" "%URL1%"
  if not errorlevel 1 if exist "%ZIP_PATH%" set "DL_OK=1"
  if "!DL_OK!"=="0" (
    echo       Mirror failed, try nodejs.org ...
    "%CURL%" -L --retry 3 --connect-timeout 20 -o "%ZIP_PATH%" "%URL2%"
    if not errorlevel 1 if exist "%ZIP_PATH%" set "DL_OK=1"
  )
)

if "!DL_OK!"=="0" if exist "%PS%" (
  echo       curl failed, try PowerShell full path...
  "%PS%" -NoProfile -ExecutionPolicy Bypass -Command "$ProgressPreference='SilentlyContinue'; try { Invoke-WebRequest -Uri '%URL1%' -OutFile '%ZIP_PATH%' -UseBasicParsing } catch { Invoke-WebRequest -Uri '%URL2%' -OutFile '%ZIP_PATH%' -UseBasicParsing }; if(-not (Test-Path '%ZIP_PATH%')){ exit 1 }"
  if not errorlevel 1 if exist "%ZIP_PATH%" set "DL_OK=1"
)

if "!DL_OK!"=="0" (
  echo       Download failed. Need curl or network access.
  exit /b 1
)

for %%A in ("%ZIP_PATH%") do set "ZIP_SIZE=%%~zA"
if not defined ZIP_SIZE set "ZIP_SIZE=0"
if !ZIP_SIZE! LSS 1000000 (
  echo       Download file too small, likely failed.
  exit /b 1
)

echo       Extracting...
mkdir "%EXTRACT%" >nul 2>&1
if exist "%TAR%" (
  "%TAR%" -xf "%ZIP_PATH%" -C "%EXTRACT%"
) else if exist "%PS%" (
  "%PS%" -NoProfile -ExecutionPolicy Bypass -Command "Expand-Archive -Path '%ZIP_PATH%' -DestinationPath '%EXTRACT%' -Force"
) else (
  echo       No tar/powershell to extract zip.
  exit /b 1
)

for /d %%D in ("%EXTRACT%\node-*") do (
  move "%%D" "%TOOLS_NODE%" >nul
  goto extract_done
)
echo       Extract layout unexpected.
exit /b 1

:extract_done
if exist "%EXTRACT%" rmdir /s /q "%EXTRACT%" 2>nul
del /f /q "%ZIP_PATH%" >nul 2>&1
if not exist "%TOOLS_NODE%\node.exe" (
  echo       node.exe missing after extract
  exit /b 1
)
echo       Portable Node ready
exit /b 0
