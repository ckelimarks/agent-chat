#!/usr/bin/env python3
"""
WebSocket Server for Agent Chat terminals.
Handles real-time terminal I/O between browser and PTY sessions.
"""

import asyncio
import json
import signal
import sys
from pathlib import Path
from typing import Dict, Set, Any
import logging

try:
    import websockets
    from websockets.asyncio.server import serve
except ImportError:
    print("Please install websockets: pip install websockets")
    sys.exit(1)

# Add server directory to path
sys.path.insert(0, str(Path(__file__).parent))

import db
from pty_manager import get_pty_manager
import heartbeat

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

WS_PORT = 8891
HEARTBEAT_INTERVAL = 120  # seconds (2 minutes)

# Track connected clients per agent
clients: Dict[str, Set[Any]] = {}

# Track agent metadata for heartbeats
agent_metadata: Dict[str, Dict] = {}

# Global event loop reference
main_loop = None


async def handle_terminal(websocket):
    """Handle a terminal WebSocket connection."""
    global main_loop

    # Get path from websocket
    path = websocket.request.path

    # Extract agent_id from path: /terminal/{agent_id}
    parts = path.strip('/').split('/')
    if len(parts) != 2 or parts[0] != 'terminal':
        await websocket.close(1008, "Invalid path")
        return

    agent_id = parts[1]
    logger.info(f"WebSocket connection for agent {agent_id}")

    # Get agent from database
    agent = db.get_agent(agent_id)
    if not agent:
        await websocket.close(1008, "Agent not found")
        return

    # Get or create PTY session
    pty_mgr = get_pty_manager()

    # Track this client
    if agent_id not in clients:
        clients[agent_id] = set()
    clients[agent_id].add(websocket)

    # Define output callback to send to all clients
    def on_output(data: bytes):
        if main_loop:
            asyncio.run_coroutine_threadsafe(
                broadcast_output(agent_id, data),
                main_loop
            )

        # Parse for REPORT blocks (workers only)
        if agent.get('role') != 'orchestrator':
            try:
                text = data.decode('utf-8', errors='ignore')
                heartbeat.parse_report_from_output(
                    text,
                    agent_id,
                    agent.get('display_name') or agent.get('name')
                )
            except Exception as e:
                logger.debug(f"Report parse error: {e}")

    # Track if we need to create session (wait for first resize)
    session_created = pty_mgr.has_session(agent_id)
    pending_rows = 24
    pending_cols = 80

    if session_created:
        # Existing session - update callback and send scrollback
        pty_mgr.set_output_callback(agent_id, on_output)
        scrollback = pty_mgr.get_scrollback(agent_id)
        if scrollback:
            await websocket.send(scrollback)

    try:
        async for message in websocket:
            if isinstance(message, bytes):
                # Raw terminal input
                pty_mgr.write(agent_id, message)
            else:
                # JSON command
                try:
                    cmd = json.loads(message)
                    if cmd.get('type') == 'resize':
                        rows = cmd.get('rows', 24)
                        cols = cmd.get('cols', 80)
                        logger.info(f"Resize agent {agent_id}: {cols}x{rows}")

                        if not session_created:
                            # First resize - now create the session with correct size
                            pending_rows = rows
                            pending_cols = cols

                            # Determine system prompt (orchestrator and workers get different prompts)
                            system_prompt = agent.get('system_prompt') or ''
                            if agent.get('role') == 'orchestrator':
                                orchestrator_prompt = heartbeat.get_orchestrator_system_prompt()
                                system_prompt = f"{orchestrator_prompt}\n\n{system_prompt}".strip()
                            else:
                                worker_prompt = heartbeat.get_worker_system_prompt()
                                system_prompt = f"{worker_prompt}\n\n{system_prompt}".strip()

                            pty_mgr.create_session(
                                agent_id=agent_id,
                                cwd=agent['cwd'],
                                model=agent.get('model', 'sonnet'),
                                system_prompt=system_prompt if system_prompt else None,
                                output_callback=on_output,
                                initial_rows=rows,
                                initial_cols=cols,
                                agent_name=agent.get('display_name') or agent.get('name')
                            )
                            db.set_agent_status(agent_id, 'online')
                            session_created = True

                            # Write heartbeat and session log for non-orchestrator agents
                            if agent.get('role') != 'orchestrator':
                                agent_name = agent.get('display_name') or agent.get('name')
                                agent_metadata[agent_id] = {
                                    'name': agent_name,
                                    'role': agent.get('role', 'worker')
                                }
                                heartbeat.write_heartbeat(
                                    agent_id=agent_id,
                                    agent_name=agent_name,
                                    status='online',
                                    current_task='Session started'
                                )
                                # Start session log (force=True to bypass rate limiting)
                                heartbeat.append_session_log(
                                    agent_id=agent_id,
                                    agent_name=agent_name,
                                    entry=f"Session started. Working directory: `{agent['cwd']}`",
                                    force=True
                                )
                        else:
                            pty_mgr.resize(agent_id, rows, cols)
                    elif cmd.get('type') == 'input':
                        data = cmd.get('data', '')
                        pty_mgr.write(agent_id, data.encode())
                except json.JSONDecodeError:
                    # Treat as raw input
                    pty_mgr.write(agent_id, message.encode())

    except websockets.exceptions.ConnectionClosed:
        logger.info(f"WebSocket closed for agent {agent_id}")
    finally:
        # Remove this client
        clients[agent_id].discard(websocket)
        if not clients[agent_id]:
            del clients[agent_id]
            # Don't kill the PTY - keep it alive for reconnection
            # Update heartbeat to show disconnected
            if agent.get('role') != 'orchestrator':
                heartbeat.update_status(agent_id, 'idle')


async def broadcast_output(agent_id: str, data: bytes):
    """Send output to all connected clients for an agent."""
    if agent_id in clients:
        # Create list to avoid modification during iteration
        websockets_to_send = list(clients[agent_id])
        for ws in websockets_to_send:
            try:
                await ws.send(data)
            except websockets.exceptions.ConnectionClosed:
                clients[agent_id].discard(ws)


async def heartbeat_timer():
    """Periodically update heartbeats for active workers."""
    while True:
        await asyncio.sleep(HEARTBEAT_INTERVAL)

        pty_mgr = get_pty_manager()
        active_sessions = pty_mgr.list_sessions()

        for agent_id in active_sessions:
            # Skip if not a tracked worker
            if agent_id not in agent_metadata:
                continue

            meta = agent_metadata[agent_id]
            if meta.get('role') == 'orchestrator':
                continue

            # Check if session is still alive
            if pty_mgr.is_alive(agent_id):
                heartbeat.write_heartbeat(
                    agent_id=agent_id,
                    agent_name=meta.get('name', agent_id),
                    status='active',
                    current_task='Working...'
                )
                logger.info(f"Heartbeat timer: updated {agent_id}")


async def main():
    """Start the WebSocket server."""
    global main_loop
    main_loop = asyncio.get_running_loop()

    # Initialize database
    db.init_db()

    # Handle shutdown gracefully
    stop = asyncio.Future()

    def handle_signal():
        logger.info("Shutting down WebSocket server...")
        if not stop.done():
            stop.set_result(None)

    for sig in (signal.SIGTERM, signal.SIGINT):
        main_loop.add_signal_handler(sig, handle_signal)

    # Start heartbeat timer
    heartbeat_task = asyncio.create_task(heartbeat_timer())

    async with serve(handle_terminal, "localhost", WS_PORT):
        logger.info(f"WebSocket server running at ws://localhost:{WS_PORT}")
        logger.info(f"Heartbeat interval: {HEARTBEAT_INTERVAL}s")
        await stop

    # Cancel heartbeat timer
    heartbeat_task.cancel()

    # Cleanup PTY sessions
    pty_mgr = get_pty_manager()
    for agent_id in pty_mgr.list_sessions():
        pty_mgr.kill_session(agent_id)


if __name__ == '__main__':
    asyncio.run(main())
