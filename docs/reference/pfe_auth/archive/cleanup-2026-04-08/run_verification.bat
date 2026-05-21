@echo off
echo ========================================
echo AdaptIQ Full Verification Script
echo ========================================
echo.

echo [1/5] Starting Docker services...
docker-compose up -d postgres redis
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: Failed to start Docker services
    pause
    exit /b 1
)
echo Docker services started!
echo.

echo [2/5] Waiting for services to be ready (10 seconds)...
timeout /t 10 /nobreak >nul
echo.

echo [3/5] Starting backend server...
cd backend
start "AdaptIQ Backend" cmd /c ".venv\Scripts\python.exe main.py"
cd ..
echo Backend starting in new window...
echo.

echo [4/5] Waiting for backend to start (5 seconds)...
timeout /t 5 /nobreak >nul
echo.

echo [5/5] Testing health endpoint...
curl -s http://localhost:8000/api/system/health
echo.
echo.

echo ========================================
echo Verification complete!
echo ========================================
echo.
echo Backend running at: http://localhost:8000
echo API docs at: http://localhost:8000/docs
echo.
echo To run seed script:
echo   cd backend ^&^& .venv\Scripts\python.exe seeds\seed.py
echo.
echo To start frontend:
echo   cd frontend ^&^& npm run dev
echo.
echo To run E2E tests:
echo   cd frontend ^&^& npx playwright test
echo.
pause
