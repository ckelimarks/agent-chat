#!/usr/bin/env python3
"""
WebSocket Server for Agent Chat terminals.
Handles real-time terminal I/O between browser and PTY sessions.
"""

import asyncio
import json
import signal
import sys
import time
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
from slack_agent import init_slack_agent_loop, get_slack_agent_loop

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

WS_PORT = 8891
HEARTBEAT_INTERVAL = 120  # seconds (2 minutes)
IDLE_THRESHOLD = 5  # seconds before marking as 'done'

# Track connected clients per agent
clients: Dict[str, Set[Any]] = {}

# Track canvas WebSocket clients (not tied to specific agents)
canvas_clients: Set[Any] = set()

# Track agent metadata for heartbeats
agent_metadata: Dict[str, Dict] = {}

# Track last output time per agent for idle detection
last_output_time: Dict[str, float] = {}
agent_was_busy: Dict[str, bool] = {}
agent_waiting_for_response: Dict[str, bool] = {}

# Buffer output per agent for REPORT parsing (chunks are too small)
output_buffer: Dict[str, str] = {}
OUTPUT_BUFFER_MAX = 8000  # Keep last 8KB for REPORT detection

# Track last user input time (global) for orchestrator CRON
last_user_input_time: float = time.time()  # Initialize to now so first CRON can fire
USER_IDLE_THRESHOLD = 300  # 5 minutes - don't trigger CRON if user idle
ORCHESTRATOR_CRON_INTERVAL = 300  # 5 minutes (default, can be overridden by settings.json)
SETTINGS_FILE = Path(__file__).parent.parent / "data" / "settings.json"


def get_cron_settings():
    """Read CRON settings from config file."""
    try:
        if SETTINGS_FILE.exists():
            with open(SETTINGS_FILE) as f:
                settings = json.load(f)
                return {
                    'enabled': settings.get('orchestrator_cron_enabled', True),
                    'interval': settings.get('orchestrator_cron_interval', 300)
                }
    except (json.JSONDecodeError, IOError):
        pass
    return {'enabled': True, 'interval': 300}

# Global event loop reference
main_loop = None


async def handle_canvas(websocket):
    """Handle canvas WebSocket connection."""
    logger.info("Canvas WebSocket connection")

    # Track this client
    canvas_clients.add(websocket)

    try:
        async for message in websocket:
            # Canvas clients don't send messages, only receive updates
            pass
    except websockets.exceptions.ConnectionClosed:
        logger.info("Canvas WebSocket closed")
    finally:
        canvas_clients.discard(websocket)


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
        import time

        if main_loop:
            asyncio.run_coroutine_threadsafe(
                broadcast_output(agent_id, data),
                main_loop
            )

        # Track all output - if agent is producing output, it's working
        last_output_time[agent_id] = time.time()
        # Only update db if status is changing (avoid hammering db on every character)
        if not agent_was_busy.get(agent_id, False):
            agent_was_busy[agent_id] = True
            db.set_agent_status(agent_id, 'busy')
            db.clear_notification(agent_id)
            db.update_thread_activity(agent_id)  # Update activity for sorting

        # Check for bell character (permission prompt) - only during user-initiated turns
        if agent_waiting_for_response.get(agent_id, False):
            try:
                text = data.decode('utf-8', errors='ignore')
                if '\x07' in text or '\a' in text:
                    logger.info(f"Bell detected for agent {agent_id} - setting attention")
                    db.set_notification(agent_id, 'attention')
            except Exception as e:
                logger.debug(f"Bell detection error: {e}")

        # Buffer output for REPORT parsing (workers only)
        # Parsing happens on idle, not per-chunk, to catch split JSON
        if agent.get('role') != 'orchestrator':
            try:
                text = data.decode('utf-8', errors='ignore')
                # Accumulate in buffer
                current = output_buffer.get(agent_id, '')
                output_buffer[agent_id] = (current + text)[-OUTPUT_BUFFER_MAX:]
            except Exception as e:
                logger.debug(f"Buffer error: {e}")

        # Notify Slack agent loop of output (for response capture)
        slack_loop = get_slack_agent_loop()
        if slack_loop:
            slack_loop.on_agent_output(agent_id, data)

    # Track if we need to create session (wait for first resize)
    session_created = pty_mgr.has_session(agent_id)
    pending_rows = 24
    pending_cols = 80

    # Clean up dead sessions
    if session_created and not pty_mgr.is_alive(agent_id):
        logger.info(f"Cleaning up dead PTY session for {agent_id}")
        pty_mgr.kill_session(agent_id)
        session_created = False

    if session_created:
        # Existing session - update callback and send scrollback
        pty_mgr.set_output_callback(agent_id, on_output)
        # Reset waiting flag, but preserve busy state if there was recent activity
        agent_waiting_for_response[agent_id] = False
        # Check if there was recent output (within 10 seconds)
        recent_activity = agent_id in last_output_time and (time.time() - last_output_time[agent_id]) < 10
        if recent_activity:
            # Agent is still working - keep busy state
            agent_was_busy[agent_id] = True
            db.set_agent_status(agent_id, 'busy')
            logger.info(f"Reconnecting to active agent {agent_id} - preserving busy state")
        else:
            # Fresh reconnect to idle session
            agent_was_busy[agent_id] = False
            db.clear_notification(agent_id)
            db.set_agent_status(agent_id, 'online')
        scrollback = pty_mgr.get_scrollback(agent_id)
        if scrollback:
            await websocket.send(scrollback)

    try:
        global last_user_input_time
        async for message in websocket:
            if isinstance(message, bytes):
                # Raw terminal input - only mark as waiting when Enter is pressed
                if message and (b'\r' in message or b'\n' in message):
                    agent_waiting_for_response[agent_id] = True
                    last_user_input_time = time.time()
                    logger.info(f"User input detected (bytes) for agent {agent_id}")
                pty_mgr.write(agent_id, message)
            else:
                # JSON command
                try:
                    cmd = json.loads(message)
                    if not isinstance(cmd, dict):
                        raise ValueError("Not a command dict")
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
                            agent_waiting_for_response[agent_id] = False
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
                        # Only mark as waiting when Enter is pressed
                        if data and ('\r' in data or '\n' in data):
                            agent_waiting_for_response[agent_id] = True
                            last_user_input_time = time.time()
                            db.update_thread_activity(agent_id)  # Update activity on user input
                        pty_mgr.write(agent_id, data.encode())
                except (json.JSONDecodeError, ValueError):
                    # Treat as raw input - only mark as waiting when Enter is pressed
                    if message and ('\r' in message or '\n' in message):
                        agent_waiting_for_response[agent_id] = True
                        last_user_input_time = time.time()
                        db.update_thread_activity(agent_id)  # Update activity on user input
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


async def broadcast_canvas_update():
    """Notify all canvas clients that canvas was updated."""
    if canvas_clients:
        websockets_to_send = list(canvas_clients)
        message = json.dumps({"type": "canvas_update"})
        for ws in websockets_to_send:
            try:
                await ws.send(message)
            except websockets.exceptions.ConnectionClosed:
                canvas_clients.discard(ws)
        logger.info(f"Canvas update broadcast to {len(websockets_to_send)} clients")


async def inject_as_keystrokes(agent_id: str, text: str, submit: bool = False) -> bool:
    """Inject text as discrete keystrokes (closer to real terminal typing)."""
    pty_mgr = get_pty_manager()

    # Send one character at a time to avoid TTY apps treating this as paste.
    for ch in text:
        if not pty_mgr.write(agent_id, ch.encode('utf-8')):
            return False
        await asyncio.sleep(0.005)

    if submit:
        # Enter key in terminal mode is carriage return.
        if not pty_mgr.write(agent_id, b'\r'):
            return False
    return True


async def idle_check_timer():
    """Check for idle agents and mark them as 'done'."""
    import time

    while True:
        await asyncio.sleep(2)  # Check every 2 seconds

        current_time = time.time()

        for agent_id, last_time in list(last_output_time.items()):
            # Check if agent has been idle long enough
            idle_seconds = current_time - last_time
            if idle_seconds > IDLE_THRESHOLD and agent_was_busy.get(agent_id, False):
                # Check current notification state - don't overwrite 'attention'
                agent = db.get_agent(agent_id)
                if agent and agent.get('notification') != 'attention':
                    logger.info(f"Agent {agent_id} idle for {idle_seconds:.1f}s - setting done")
                    db.set_notification(agent_id, 'done')
                    db.set_agent_status(agent_id, 'online')  # Back to online from busy
                    agent_was_busy[agent_id] = False

                    # Parse buffered output for REPORT blocks now that agent is idle
                    if agent_id in output_buffer and output_buffer[agent_id]:
                        try:
                            agent_name = agent.get('display_name') or agent.get('name')
                            found = heartbeat.parse_report_from_output(
                                output_buffer[agent_id],
                                agent_id,
                                agent_name
                            )
                            if found:
                                logger.info(f"REPORT captured from {agent_name}")
                            # Clear buffer after parsing
                            output_buffer[agent_id] = ''
                        except Exception as e:
                            logger.debug(f"Buffer parse error: {e}")

                    # Keep agent_waiting_for_response True so resumed output triggers Working again


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


async def canvas_watcher():
    """Watch for canvas updates and broadcast to clients."""
    logger.info("Canvas watcher started")
    signal_path = Path(__file__).parent.parent / "data" / "canvas.signal"

    # Track last modified time
    last_mtime = 0.0

    while True:
        await asyncio.sleep(0.5)  # Check every 500ms

        try:
            if signal_path.exists():
                mtime = signal_path.stat().st_mtime
                if mtime > last_mtime:
                    last_mtime = mtime
                    await broadcast_canvas_update()
                    # Remove signal file
                    signal_path.unlink()
        except Exception as e:
            logger.debug(f"Canvas watcher error: {e}")


async def orchestrator_cron():
    """Periodically prompt the orchestrator to check in (if user is active)."""
    logger.info("Orchestrator CRON started")
    last_checkin_time = 0.0  # Track when we last sent a check-in

    while True:
        # Read settings dynamically each tick
        settings = get_cron_settings()
        interval = settings['interval']

        await asyncio.sleep(min(interval, 60))  # Check at least every 60s for setting changes

        # Re-read settings in case they changed
        settings = get_cron_settings()
        if not settings['enabled']:
            logger.debug("Orchestrator CRON: disabled in settings")
            continue

        current_time = time.time()

        # Check if enough time has passed since last check-in
        since_last_checkin = current_time - last_checkin_time
        if since_last_checkin < settings['interval']:
            logger.debug(f"Orchestrator CRON: waiting, {settings['interval'] - since_last_checkin:.0f}s until next check-in")
            continue
        idle_seconds = current_time - last_user_input_time
        logger.info(f"Orchestrator CRON tick: user idle for {idle_seconds:.0f}s")

        # Check if user has been active recently
        if idle_seconds > USER_IDLE_THRESHOLD:
            logger.info("Orchestrator CRON: user idle, skipping check-in")
            continue

        # Find the orchestrator agent
        agents = db.list_agents()
        orchestrator = None
        for agent in agents:
            if agent.get('role') == 'orchestrator':
                orchestrator = agent
                break

        if not orchestrator:
            logger.info("Orchestrator CRON: no orchestrator agent found")
            continue

        orchestrator_id = orchestrator['id']
        logger.info(f"Orchestrator CRON: found orchestrator {orchestrator.get('display_name')} ({orchestrator_id})")
        pty_mgr = get_pty_manager()

        # Check if orchestrator has active PTY session
        has_session = pty_mgr.has_session(orchestrator_id)
        is_alive = pty_mgr.is_alive(orchestrator_id) if has_session else False
        logger.info(f"Orchestrator CRON: has_session={has_session}, is_alive={is_alive}")

        if not has_session or not is_alive:
            logger.info("Orchestrator CRON: orchestrator has no active session, skipping")
            continue

        # Inject check-in prompt and submit with Enter.
        # Send as keystrokes (not one bulk write) so terminal UIs treat it as typed input.
        check_in_prompt = "[Check-in] Review worker status and share observations."
        ok = await inject_as_keystrokes(orchestrator_id, check_in_prompt, submit=True)
        if ok:
            last_checkin_time = time.time()  # Update last check-in time
            logger.info(f"Orchestrator CRON: injected check-in prompt to {orchestrator.get('display_name')}")
        else:
            logger.warning(
                f"Orchestrator CRON: failed to inject check-in prompt to {orchestrator.get('display_name')}"
            )


async def slack_agent_poller():
    """Poll Slack for mentions and handle responses."""
    logger.info("Slack agent poller started")

    while True:
        await asyncio.sleep(5)  # Check every 5 seconds (actual polling rate limited internally)

        slack_loop = get_slack_agent_loop()
        if slack_loop:
            try:
                await slack_loop.poll_and_respond()
            except Exception as e:
                logger.error(f"Slack agent error: {e}")


async def main():
    """Start the WebSocket server."""
    global main_loop
    main_loop = asyncio.get_running_loop()

    # Initialize database
    db.init_db()

    # Initialize Slack agent loop
    pty_mgr = get_pty_manager()
    slack_loop = init_slack_agent_loop(pty_mgr, db.get_agent)
    logger.info("Slack agent loop initialized")

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

    # Start idle check timer for notifications
    idle_task = asyncio.create_task(idle_check_timer())

    # Start orchestrator CRON
    orchestrator_cron_task = asyncio.create_task(orchestrator_cron())

    # Start canvas watcher
    canvas_watcher_task = asyncio.create_task(canvas_watcher())

    # Start Slack agent poller
    slack_agent_task = asyncio.create_task(slack_agent_poller())

    # Define router for WebSocket paths
    async def ws_router(websocket):
        path = websocket.request.path
        if path == '/canvas':
            await handle_canvas(websocket)
        elif path.startswith('/terminal/'):
            await handle_terminal(websocket)
        else:
            await websocket.close(1008, "Invalid path")

    async with serve(ws_router, "0.0.0.0", WS_PORT):
        logger.info(f"WebSocket server running at ws://0.0.0.0:{WS_PORT}")
        logger.info(f"Heartbeat interval: {HEARTBEAT_INTERVAL}s")
        logger.info(f"Idle threshold for 'done': {IDLE_THRESHOLD}s")
        logger.info(f"Orchestrator CRON interval: {ORCHESTRATOR_CRON_INTERVAL}s")
        logger.info("Canvas watcher enabled")
        logger.info("Slack agent poller enabled")
        await stop

    # Cancel timers
    heartbeat_task.cancel()
    idle_task.cancel()
    orchestrator_cron_task.cancel()
    canvas_watcher_task.cancel()
    slack_agent_task.cancel()

    # Cleanup PTY sessions
    pty_mgr = get_pty_manager()
    for agent_id in pty_mgr.list_sessions():
        pty_mgr.kill_session(agent_id)


if __name__ == '__main__':
    asyncio.run(main())
