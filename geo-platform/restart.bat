@echo off
setlocal

set ROOT=%~dp0
cd /d "%ROOT%"

echo [1/4] Restarting Docker containers...
docker compose restart
if errorlevel 1 goto :error

echo [2/4] Killing anything on ports 8000 (backend) and 5173 (frontend)...
call :killport 8000
call :killport 5173

echo [3/4] Starting backend in new window...
start "Geo API" cmd /k "cd /d %ROOT%api && py run.py"

echo [4/4] Starting frontend in new window...
start "Geo Web" cmd /k "cd /d %ROOT%web && npm run dev"

echo.
echo Done.
echo   Backend:  http://127.0.0.1:8000
echo   Frontend: http://localhost:5173
exit /b 0

:killport
for /f "tokens=5" %%a in ('netstat -ano ^| findstr "LISTENING" ^| findstr ":%~1 "') do (
    echo   killing PID %%a on port %~1
    taskkill /F /PID %%a >nul 2>&1
)
exit /b 0

:error
echo.
echo Docker restart failed. Check that Docker Desktop is running.
exit /b 1
