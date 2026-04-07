#!/usr/bin/env bash
set -e

echo "Starting Backend & Frontend..."

# Kill processes on port 8000 and 5173 if they exist
lsof -ti:8000 | xargs kill -9 2>/dev/null || true
lsof -ti:5173 | xargs kill -9 2>/dev/null || true

# Boot Backend
cd backend
if [ ! -d ".venv" ]; then
    echo "Creating virtualenv for backend..."
    python3 -m venv .venv
fi
source .venv/bin/activate
pip install -q -r requirements.txt
echo "Starting Flask Server on port 8000..."
python server.py &
BACKEND_PID=$!
cd ..

# Boot Frontend
cd careercorps-ui
if [ ! -d "node_modules" ]; then
    echo "Installing frontend dependencies..."
    npm install
fi
echo "Starting Vite dev server..."
npm run dev -- --port 5173 &
FRONTEND_PID=$!
cd ..

echo "Backend (PID: $BACKEND_PID) and Frontend (PID: $FRONTEND_PID) are running!"
echo "Press Ctrl+C to stop both."

wait $BACKEND_PID $FRONTEND_PID
