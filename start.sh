#!/bin/bash
# Start the Agent Chat servers

cd "$(dirname "$0")"

# Check for websockets
python3 -c "import websockets" 2>/dev/null || {
    echo "Installing websockets..."
    pip install websockets
}

# Kill any existing servers
pkill -f "python3 server/bridge.py" 2>/dev/null
pkill -f "python3 server/ws_server.py" 2>/dev/null
sleep 1

echo "Starting Agent Chat..."
echo "  HTTP Server: http://localhost:8890"
echo "  WebSocket:   ws://localhost:8891"
echo ""

# Start HTTP server in background
python3 server/bridge.py &
HTTP_PID=$!

# Start WebSocket server in background
python3 server/ws_server.py &
WS_PID=$!

# Handle Ctrl+C
trap "echo 'Shutting down...'; kill $HTTP_PID $WS_PID 2>/dev/null; exit" INT TERM

echo "Press Ctrl+C to stop"
echo ""

# Wait for either to exit
wait
