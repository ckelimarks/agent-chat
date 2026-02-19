"""
Database operations for Agent Chat.
SQLite-based storage for agents, threads, messages, and reports.
"""

import sqlite3
import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any
from contextlib import contextmanager

DB_PATH = Path(__file__).parent.parent / "data" / "agent-chat.db"
SCHEMA_PATH = Path(__file__).parent / "schema.sql"


@contextmanager
def get_connection():
    """Context manager for database connections."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    """Initialize database with schema."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with get_connection() as conn:
        with open(SCHEMA_PATH) as f:
            conn.executescript(f.read())


def row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
    """Convert sqlite Row to dictionary."""
    if row is None:
        return None
    return dict(row)


# =============================================================================
# Agent Operations
# =============================================================================

def create_agent(
    name: str,
    cwd: str,
    display_name: Optional[str] = None,
    emoji: str = "🤖",
    model: str = "sonnet",
    system_prompt: Optional[str] = None,
    role: str = "worker"
) -> Dict[str, Any]:
    """Create a new agent and its associated thread."""
    agent_id = str(uuid.uuid4())[:8]
    thread_id = str(uuid.uuid4())[:8]

    with get_connection() as conn:
        conn.execute("""
            INSERT INTO agents (id, name, display_name, emoji, model, cwd, system_prompt, role)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (agent_id, name, display_name or name, emoji, model, cwd, system_prompt, role))

        conn.execute("""
            INSERT INTO threads (id, agent_id, last_activity)
            VALUES (?, ?, ?)
        """, (thread_id, agent_id, datetime.now().isoformat()))

    return get_agent(agent_id)


def get_agent(agent_id: str) -> Optional[Dict[str, Any]]:
    """Get agent by ID with thread info."""
    with get_connection() as conn:
        row = conn.execute("""
            SELECT a.*, t.id as thread_id, t.session_id, t.unread_count, t.last_activity
            FROM agents a
            LEFT JOIN threads t ON t.agent_id = a.id
            WHERE a.id = ?
        """, (agent_id,)).fetchone()
        return row_to_dict(row)


def list_agents() -> List[Dict[str, Any]]:
    """List all agents with thread info."""
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT a.*, t.id as thread_id, t.session_id, t.unread_count, t.last_activity
            FROM agents a
            LEFT JOIN threads t ON t.agent_id = a.id
            ORDER BY t.last_activity DESC NULLS LAST
        """).fetchall()
        return [row_to_dict(r) for r in rows]


def update_agent(agent_id: str, **kwargs) -> Optional[Dict[str, Any]]:
    """Update agent fields."""
    allowed = {'name', 'display_name', 'avatar_path', 'emoji', 'model', 'cwd', 'system_prompt', 'role', 'status'}
    updates = {k: v for k, v in kwargs.items() if k in allowed}

    if not updates:
        return get_agent(agent_id)

    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [agent_id]

    with get_connection() as conn:
        conn.execute(f"UPDATE agents SET {set_clause} WHERE id = ?", values)

    return get_agent(agent_id)


def delete_agent(agent_id: str) -> bool:
    """Delete an agent and its thread/messages (cascading)."""
    with get_connection() as conn:
        cursor = conn.execute("DELETE FROM agents WHERE id = ?", (agent_id,))
        return cursor.rowcount > 0


def set_agent_status(agent_id: str, status: str):
    """Update agent status (offline/online/busy)."""
    with get_connection() as conn:
        conn.execute("UPDATE agents SET status = ? WHERE id = ?", (status, agent_id))


# =============================================================================
# Thread Operations
# =============================================================================

def get_thread(thread_id: str) -> Optional[Dict[str, Any]]:
    """Get thread by ID."""
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM threads WHERE id = ?", (thread_id,)).fetchone()
        return row_to_dict(row)


def get_thread_by_agent(agent_id: str) -> Optional[Dict[str, Any]]:
    """Get thread for an agent."""
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM threads WHERE agent_id = ?", (agent_id,)).fetchone()
        return row_to_dict(row)


def update_thread_session(thread_id: str, session_id: str):
    """Update thread session ID for --resume."""
    with get_connection() as conn:
        conn.execute("""
            UPDATE threads SET session_id = ?, last_activity = ? WHERE id = ?
        """, (session_id, datetime.now().isoformat(), thread_id))


def update_thread_activity(thread_id: str):
    """Update thread last activity timestamp."""
    with get_connection() as conn:
        conn.execute("""
            UPDATE threads SET last_activity = ? WHERE id = ?
        """, (datetime.now().isoformat(), thread_id))


def increment_unread(thread_id: str):
    """Increment unread count for a thread."""
    with get_connection() as conn:
        conn.execute("UPDATE threads SET unread_count = unread_count + 1 WHERE id = ?", (thread_id,))


def clear_unread(thread_id: str):
    """Clear unread count for a thread."""
    with get_connection() as conn:
        conn.execute("UPDATE threads SET unread_count = 0 WHERE id = ?", (thread_id,))


# =============================================================================
# Message Operations
# =============================================================================

def add_message(thread_id: str, role: str, content: str) -> Dict[str, Any]:
    """Add a message to a thread."""
    with get_connection() as conn:
        cursor = conn.execute("""
            INSERT INTO messages (thread_id, role, content)
            VALUES (?, ?, ?)
        """, (thread_id, role, content))

        # Update thread activity
        conn.execute("""
            UPDATE threads SET last_activity = ? WHERE id = ?
        """, (datetime.now().isoformat(), thread_id))

        row = conn.execute("SELECT * FROM messages WHERE id = ?", (cursor.lastrowid,)).fetchone()
        return row_to_dict(row)


def get_messages(thread_id: str, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
    """Get messages for a thread, newest last."""
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT * FROM messages
            WHERE thread_id = ?
            ORDER BY created_at ASC
            LIMIT ? OFFSET ?
        """, (thread_id, limit, offset)).fetchall()
        return [row_to_dict(r) for r in rows]


def get_messages_since(thread_id: str, since_id: int) -> List[Dict[str, Any]]:
    """Get messages newer than a given ID."""
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT * FROM messages
            WHERE thread_id = ? AND id > ?
            ORDER BY created_at ASC
        """, (thread_id, since_id)).fetchall()
        return [row_to_dict(r) for r in rows]


# =============================================================================
# Report Operations
# =============================================================================

def add_report(
    agent_id: str,
    agent_name: str,
    report_type: str,
    title: str,
    summary: str,
    payload: Optional[Dict] = None
) -> Dict[str, Any]:
    """Add a report to the manager inbox."""
    with get_connection() as conn:
        cursor = conn.execute("""
            INSERT INTO reports (agent_id, agent_name, type, title, summary, payload)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (agent_id, agent_name, report_type, title, summary, json.dumps(payload) if payload else None))

        row = conn.execute("SELECT * FROM reports WHERE id = ?", (cursor.lastrowid,)).fetchone()
        result = row_to_dict(row)
        if result and result.get('payload'):
            result['payload'] = json.loads(result['payload'])
        return result


def get_reports(acknowledged: Optional[bool] = None, limit: int = 50) -> List[Dict[str, Any]]:
    """Get reports, optionally filtered by acknowledged status."""
    with get_connection() as conn:
        if acknowledged is None:
            rows = conn.execute("""
                SELECT * FROM reports ORDER BY created_at DESC LIMIT ?
            """, (limit,)).fetchall()
        else:
            rows = conn.execute("""
                SELECT * FROM reports WHERE acknowledged = ? ORDER BY created_at DESC LIMIT ?
            """, (acknowledged, limit)).fetchall()

        results = []
        for row in rows:
            d = row_to_dict(row)
            if d.get('payload'):
                d['payload'] = json.loads(d['payload'])
            results.append(d)
        return results


def get_unacknowledged_count() -> int:
    """Get count of unacknowledged reports."""
    with get_connection() as conn:
        row = conn.execute("SELECT COUNT(*) as count FROM reports WHERE acknowledged = FALSE").fetchone()
        return row['count'] if row else 0


def acknowledge_report(report_id: int) -> bool:
    """Mark a report as acknowledged."""
    with get_connection() as conn:
        cursor = conn.execute("UPDATE reports SET acknowledged = TRUE WHERE id = ?", (report_id,))
        return cursor.rowcount > 0


def acknowledge_all_reports() -> int:
    """Mark all reports as acknowledged."""
    with get_connection() as conn:
        cursor = conn.execute("UPDATE reports SET acknowledged = TRUE WHERE acknowledged = FALSE")
        return cursor.rowcount


# Initialize database on import
if __name__ == "__main__":
    init_db()
    print(f"Database initialized at {DB_PATH}")
