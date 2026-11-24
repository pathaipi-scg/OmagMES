@echo off
setlocal
set "ROOT=%~dp0"
set "APP_PORT="

if exist "%ROOT%.env" (
  for /f "usebackq tokens=1,* delims==" %%A in (`findstr /B /C:"APP_PORT=" "%ROOT%.env"`) do set "APP_PORT=%%B"
)
if not defined APP_PORT set "APP_PORT=3001"

if not exist "%ROOT%.venv\Scripts\python.exe" (
  echo OmagMES virtual environment not found at "%ROOT%.venv".
  echo Create/configure the project Python environment first.
  exit /b 1
)
start "OmagMES Web - %APP_PORT%" /D "%ROOT%" cmd /k ".venv\Scripts\python.exe -m uvicorn backend.app.main:app --host 0.0.0.0 --port %APP_PORT%"
echo Waiting for the server-rendered FastAPI application...
curl.exe --silent --show-error --fail --retry 30 --retry-connrefused --retry-delay 1 --max-time 2 http://127.0.0.1:%APP_PORT%/api/health >nul
if errorlevel 1 (
  echo OmagMES did not become ready on 127.0.0.1:%APP_PORT%. Check the application console.
  exit /b 1
)

echo OmagMES is starting.
echo Open http://localhost:%APP_PORT% on this computer.
echo OmagMES is available on this computer and reachable network interfaces at port %APP_PORT%.
