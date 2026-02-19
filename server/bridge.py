#!/usr/bin/env python3
"""
Bridge Server for Agent Chat.
HTTP server handling agent management, chat messages, and reports.
"""

import json
import os
import sys
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from pathlib import Path
import logging

# Add server directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

import db
import heartbeat
from process_manager import get_process_manager, AgentConfig

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

PORT = 8890
WEB_DIR = Path(__file__).parent.parent / "web"


class AgentChatHandler(BaseHTTPRequestHandler):
    """HTTP request handler for Agent Chat API."""

    def log_message(self, format, *args):
        """Custom log format."""
        logger.info(f"{self.address_string()} - {format % args}")

    def send_json(self, data: dict, status: int = 200):
        """Send JSON response."""
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def send_error_json(self, message: str, status: int = 400):
        """Send JSON error response."""
        self.send_json({"error": message}, status)

    def do_OPTIONS(self):
        """Handle CORS preflight."""
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def do_GET(self):
        """Handle GET requests."""
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)

        # API routes
        if path == '/api/health':
            self.send_json({"status": "ok", "port": PORT})

        elif path == '/api/agents':
            agents = db.list_agents()
            self.send_json({"agents": agents})

        elif path.startswith('/api/agents/') and path.count('/') == 3:
            agent_id = path.split('/')[3]
            agent = db.get_agent(agent_id)
            if agent:
                self.send_json({"agent": agent})
            else:
                self.send_error_json("Agent not found", 404)

        elif path.startswith('/api/threads/') and '/messages' in path:
            # /api/threads/{id}/messages
            parts = path.split('/')
            thread_id = parts[3]
            since_id = int(query.get('since', [0])[0])

            if since_id > 0:
                messages = db.get_messages_since(thread_id, since_id)
            else:
                messages = db.get_messages(thread_id)

            self.send_json({"messages": messages})

        elif path == '/api/reports':
            acknowledged = query.get('acknowledged', [None])[0]
            if acknowledged is not None:
                acknowledged = acknowledged.lower() == 'true'
            reports = db.get_reports(acknowledged=acknowledged)
            unread_count = db.get_unacknowledged_count()
            self.send_json({"reports": reports, "unread_count": unread_count})

        elif path == '/api/orchestrator/heartbeats':
            # Get all worker heartbeats
            heartbeats = heartbeat.get_heartbeats()
            self.send_json({"heartbeats": heartbeats})

        elif path == '/api/orchestrator/briefing':
            # Generate briefing summary
            briefing = heartbeat.generate_briefing()
            self.send_json({"briefing": briefing})

        elif path == '/api/browse':
            # Directory browser
            dir_path = query.get('path', ['~'])[0]
            try:
                # Handle ~ expansion
                if dir_path.startswith('~'):
                    dir_path = str(Path.home()) + dir_path[1:]
                p = Path(dir_path).expanduser().resolve()
                if not p.exists():
                    self.send_error_json("Path not found", 404)
                    return
                if not p.is_dir():
                    self.send_error_json("Not a directory", 400)
                    return

                items = []
                # Add parent directory option
                if p.parent != p:
                    items.append({
                        "name": "..",
                        "path": str(p.parent),
                        "is_dir": True
                    })

                # List directory contents
                for item in sorted(p.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower())):
                    # Skip hidden files and common non-project dirs
                    if item.name.startswith('.') and item.name not in ['.']:
                        continue
                    if item.name in ['node_modules', '__pycache__', 'venv', '.git']:
                        continue
                    if item.is_dir():
                        items.append({
                            "name": item.name,
                            "path": str(item),
                            "is_dir": True
                        })

                self.send_json({
                    "current": str(p),
                    "items": items
                })
            except PermissionError:
                self.send_error_json("Permission denied", 403)
            except Exception as e:
                self.send_error_json(str(e), 500)

        # Static files
        elif path == '/' or path == '/index.html':
            self.serve_file('index.html', 'text/html')

        elif path.endswith('.js'):
            self.serve_file(path[1:], 'application/javascript')

        elif path.endswith('.css'):
            self.serve_file(path[1:], 'text/css')

        elif path.startswith('/avatars/'):
            avatar_path = Path(__file__).parent.parent / "data" / path[1:]
            if avatar_path.exists():
                content_type = 'image/png' if path.endswith('.png') else 'image/jpeg'
                self.serve_file_absolute(avatar_path, content_type)
            else:
                self.send_error(404)

        else:
            self.send_error(404)

    def do_POST(self):
        """Handle POST requests."""
        parsed = urlparse(self.path)
        path = parsed.path

        # Read body
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length).decode() if content_length > 0 else '{}'

        try:
            data = json.loads(body) if body else {}
        except json.JSONDecodeError:
            self.send_error_json("Invalid JSON")
            return

        # API routes
        if path == '/api/agents':
            # Create agent
            required = ['name', 'cwd']
            if not all(k in data for k in required):
                self.send_error_json(f"Missing required fields: {required}")
                return

            agent = db.create_agent(
                name=data['name'],
                cwd=data['cwd'],
                display_name=data.get('display_name'),
                emoji=data.get('emoji', '🤖'),
                model=data.get('model', 'sonnet'),
                system_prompt=data.get('system_prompt'),
                role=data.get('role', 'worker')
            )
            self.send_json({"agent": agent}, 201)

        elif path.startswith('/api/threads/') and '/messages' in path:
            # Send message to agent
            parts = path.split('/')
            thread_id = parts[3]

            if 'content' not in data:
                self.send_error_json("Missing 'content' field")
                return

            thread = db.get_thread(thread_id)
            if not thread:
                self.send_error_json("Thread not found", 404)
                return

            agent = db.get_agent(thread['agent_id'])
            if not agent:
                self.send_error_json("Agent not found", 404)
                return

            # Add user message
            user_msg = db.add_message(thread_id, 'user', data['content'])

            # Update agent status and clear any notification
            db.set_agent_status(agent['id'], 'busy')
            db.clear_notification(agent['id'])

            # Send to Claude asynchronously
            pm = get_process_manager()
            config = AgentConfig(
                agent_id=agent['id'],
                name=agent['name'],
                cwd=agent['cwd'],
                model=agent['model'],
                system_prompt=agent['system_prompt'],
                session_id=thread.get('session_id')
            )

            def on_complete(response: str, session_id: str):
                # Add assistant message
                db.add_message(thread_id, 'assistant', response)

                # Update session ID if provided
                if session_id:
                    db.update_thread_session(thread_id, session_id)

                # Update agent status
                db.set_agent_status(agent['id'], 'online')

                # Increment unread if not current thread
                db.increment_unread(thread_id)

            pm.send_message_async(config, data['content'], on_complete)

            self.send_json({
                "message": user_msg,
                "status": "processing"
            }, 202)

        elif path == '/api/reports':
            # Add report (from hook)
            required = ['agent_id', 'agent_name', 'type', 'title', 'summary']
            if not all(k in data for k in required):
                self.send_error_json(f"Missing required fields: {required}")
                return

            report = db.add_report(
                agent_id=data['agent_id'],
                agent_name=data['agent_name'],
                report_type=data['type'],
                title=data['title'],
                summary=data['summary'],
                payload=data.get('payload')
            )
            self.send_json({"report": report}, 201)

        elif path.startswith('/api/reports/') and '/acknowledge' in path:
            # Acknowledge report
            parts = path.split('/')
            report_id = int(parts[3])
            success = db.acknowledge_report(report_id)
            self.send_json({"success": success})

        elif path == '/api/reports/acknowledge-all':
            # Acknowledge all reports
            count = db.acknowledge_all_reports()
            self.send_json({"acknowledged": count})

        elif path == '/api/heartbeat':
            # Heartbeat update from hook
            required = ['agent_id', 'agent_name']
            if not all(k in data for k in required):
                self.send_error_json(f"Missing required fields: {required}")
                return

            # Update heartbeat
            heartbeat.write_heartbeat(
                agent_id=data['agent_id'],
                agent_name=data['agent_name'],
                status=data.get('status', 'active'),
                current_task=data.get('current_task'),
                progress=data.get('progress'),
                summary=data.get('summary'),
                blockers=data.get('blockers'),
                key_decisions=data.get('key_decisions')
            )

            # Also append to session log (rate limited)
            if data.get('current_task'):
                heartbeat.append_session_log(
                    agent_id=data['agent_id'],
                    agent_name=data['agent_name'],
                    entry=data.get('current_task')
                )

            self.send_json({"success": True}, 200)

        elif path.startswith('/api/threads/') and '/read' in path:
            # Mark thread as read
            parts = path.split('/')
            thread_id = parts[3]
            db.clear_unread(thread_id)
            self.send_json({"success": True})

        else:
            self.send_error_json("Not found", 404)

    def do_PUT(self):
        """Handle PUT requests."""
        parsed = urlparse(self.path)
        path = parsed.path

        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length).decode() if content_length > 0 else '{}'

        try:
            data = json.loads(body) if body else {}
        except json.JSONDecodeError:
            self.send_error_json("Invalid JSON")
            return

        if path.startswith('/api/agents/'):
            agent_id = path.split('/')[3]
            agent = db.update_agent(agent_id, **data)
            if agent:
                self.send_json({"agent": agent})
            else:
                self.send_error_json("Agent not found", 404)
        else:
            self.send_error_json("Not found", 404)

    def do_DELETE(self):
        """Handle DELETE requests."""
        parsed = urlparse(self.path)
        path = parsed.path

        if path.startswith('/api/agents/'):
            agent_id = path.split('/')[3]
            success = db.delete_agent(agent_id)
            if success:
                self.send_json({"success": True})
            else:
                self.send_error_json("Agent not found", 404)
        else:
            self.send_error_json("Not found", 404)

    def serve_file(self, filename: str, content_type: str):
        """Serve a static file from the web directory."""
        filepath = WEB_DIR / filename
        self.serve_file_absolute(filepath, content_type)

    def serve_file_absolute(self, filepath: Path, content_type: str):
        """Serve a file from an absolute path."""
        if filepath.exists():
            self.send_response(200)
            self.send_header('Content-Type', content_type)
            self.send_header('Cache-Control', 'no-cache')
            self.end_headers()
            with open(filepath, 'rb') as f:
                self.wfile.write(f.read())
        else:
            self.send_error(404)


def run_server():
    """Start the HTTP server."""
    # Initialize database
    db.init_db()
    logger.info(f"Database initialized at {db.DB_PATH}")

    # Reset stale statuses from previous session
    with db.get_connection() as conn:
        conn.execute("UPDATE agents SET status = 'offline', notification = NULL")
    logger.info("Reset agent statuses on startup")

    # Start server
    server = HTTPServer(('localhost', PORT), AgentChatHandler)
    logger.info(f"Agent Chat server running at http://localhost:{PORT}")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Shutting down...")
        server.shutdown()


if __name__ == '__main__':
    run_server()
