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
if not exist "%ROOT%frontend\node_modules\vite\bin\vite.js" (
  echo Frontend dependencies are not installed. Run npm install in the frontend folder first.
  exit /b 1
)

start "OmagMES API - internal 8000" /D "%ROOT%" cmd /k ".venv\Scripts\python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000"
echo Waiting for the internal FastAPI health endpoint...
curl.exe --silent --show-error --fail --retry 30 --retry-connrefused --retry-delay 1 --max-time 2 http://127.0.0.1:8000/api/health >nul
if errorlevel 1 (
  echo FastAPI did not become ready on 127.0.0.1:8000. Check the API console before opening OmagMES.
  exit /b 1
)
start "OmagMES Web - access %APP_PORT%" /D "%ROOT%frontend" cmd /k "npm run dev"

echo OmagMES is starting.
echo Open http://localhost:%APP_PORT% on this computer, or http://HOSTNAME-OR-IP:%APP_PORT% from another computer.
echo The FastAPI backend remains internal on 127.0.0.1:8000.
