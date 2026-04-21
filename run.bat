@echo off
echo Starting Backend ^& Frontend...

:: Kill anything on port 8000 and 5173
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":8000 " 2^>nul') do taskkill /PID %%a /F >nul 2>&1
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":5173 " 2^>nul') do taskkill /PID %%a /F >nul 2>&1

:: Boot Backend
cd backend
if not exist ".venv" (
    echo Creating virtualenv for backend...
    python -m venv .venv
)
call .venv\Scripts\activate.bat
pip install -q -r requirements.txt
echo Starting Flask server on port 8000...
start "Backend" python server.py
cd ..

:: Boot Frontend
cd careercorps-ui
if not exist "node_modules" (
    echo Installing frontend dependencies...
    npm install
)
echo Starting Vite dev server...
start "Frontend" npm run dev -- --port 5173
cd ..

echo.
echo Backend and Frontend are running in separate windows.
echo Close those windows (or press Ctrl+C in each) to stop them.
