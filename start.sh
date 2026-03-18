#!/bin/bash
# Start the Agent Chat servers

cd "$(dirname "$0")"

# Check for dependencies
python3 -c "import websockets" 2>/dev/null || {
    echo "Installing websockets..."
    pip install websockets
}

# Kill any existing servers
pkill -f "python3 server/bridge.py" 2>/dev/null
pkill -f "python3 server/ws_server.py" 2>/dev/null
pkill -f "server/slack_dialogue.sh" 2>/dev/null
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

# Slack agent is now integrated into ws_server.py
# Configure via: POST /api/slack-agent/config {agent_id, channel_id, thread_ts}
if [ -n "$SLACK_BOT_TOKEN" ]; then
    echo "  Slack Agent: Enabled (configure via API)"
else
    echo "  Slack Agent: SLACK_BOT_TOKEN not set"
fi

# Handle Ctrl+C
trap "echo 'Shutting down...'; kill $HTTP_PID $WS_PID 2>/dev/null; exit" INT TERM

echo "Press Ctrl+C to stop"
echo ""

# Wait for either to exit
wait
