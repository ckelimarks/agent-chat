"""
Heartbeat system for agent orchestration.
Workers write status, orchestrator reads.
"""

import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any
import threading
import logging

logger = logging.getLogger(__name__)

# Paths
DATA_DIR = Path(__file__).parent.parent / "data" / "orchestrator"
HEARTBEATS_FILE = DATA_DIR / "heartbeats.json"
SESSIONS_DIR = DATA_DIR / "sessions"

# Ensure directories exist
DATA_DIR.mkdir(parents=True, exist_ok=True)
SESSIONS_DIR.mkdir(parents=True, exist_ok=True)

# Lock for thread-safe writes
_lock = threading.Lock()

# Rate limiting for session logs (prevent spam)
_last_log_time: Dict[str, datetime] = {}
LOG_INTERVAL_SECONDS = 30  # Min seconds between session log entries per agent


def get_heartbeats() -> Dict[str, Any]:
    """Read all agent heartbeats."""
    if not HEARTBEATS_FILE.exists():
        return {}

    try:
        with open(HEARTBEATS_FILE) as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {}


def write_heartbeat(
    agent_id: str,
    agent_name: str,
    status: str = "active",
    current_task: Optional[str] = None,
    progress: Optional[str] = None,
    summary: Optional[str] = None,
    blockers: Optional[list] = None,
    key_decisions: Optional[list] = None
):
    """Write/update heartbeat for an agent."""
    with _lock:
        heartbeats = get_heartbeats()

        heartbeats[agent_id] = {
            "agent_id": agent_id,
            "agent_name": agent_name,
            "status": status,
            "current_task": current_task,
            "progress": progress,
            "summary": summary,
            "blockers": blockers or [],
            "key_decisions": key_decisions or [],
            "last_heartbeat": datetime.now().isoformat(),
            "session_start": heartbeats.get(agent_id, {}).get("session_start", datetime.now().isoformat())
        }

        with open(HEARTBEATS_FILE, 'w') as f:
            json.dump(heartbeats, f, indent=2)

        logger.info(f"Heartbeat written for {agent_name}")


def clear_heartbeat(agent_id: str):
    """Remove heartbeat for an agent (when session ends)."""
    with _lock:
        heartbeats = get_heartbeats()
        if agent_id in heartbeats:
            del heartbeats[agent_id]
            with open(HEARTBEATS_FILE, 'w') as f:
                json.dump(heartbeats, f, indent=2)


def update_status(agent_id: str, status: str):
    """Quick status update (online/offline/working)."""
    with _lock:
        heartbeats = get_heartbeats()
        if agent_id in heartbeats:
            heartbeats[agent_id]["status"] = status
            heartbeats[agent_id]["last_heartbeat"] = datetime.now().isoformat()
            with open(HEARTBEATS_FILE, 'w') as f:
                json.dump(heartbeats, f, indent=2)


def get_session_log_path(agent_id: str) -> Path:
    """Get path for today's session log."""
    date_str = datetime.now().strftime("%Y-%m-%d")
    return SESSIONS_DIR / f"{agent_id}-{date_str}.md"


def append_session_log(agent_id: str, agent_name: str, entry: str, force: bool = False):
    """Append an entry to the session log.

    Args:
        agent_id: Agent identifier
        agent_name: Human-readable agent name
        entry: Log entry text
        force: If True, bypass rate limiting (for important events)
    """
    global _last_log_time

    # Rate limiting (unless forced)
    if not force:
        now = datetime.now()
        last_time = _last_log_time.get(agent_id)
        if last_time and (now - last_time).total_seconds() < LOG_INTERVAL_SECONDS:
            return  # Skip this entry
        _last_log_time[agent_id] = now

    log_path = get_session_log_path(agent_id)

    # Create header if file doesn't exist
    if not log_path.exists():
        header = f"""# Session: {agent_name}
Date: {datetime.now().strftime("%Y-%m-%d")}
Started: {datetime.now().strftime("%H:%M")}

---

"""
        with open(log_path, 'w') as f:
            f.write(header)

    # Append entry
    timestamp = datetime.now().strftime("%H:%M")
    with open(log_path, 'a') as f:
        f.write(f"\n**[{timestamp}]** {entry}\n")


def get_worker_system_prompt() -> str:
    """Generate system prompt for workers (activity is now auto-tracked via hooks)."""
    return """## Multi-Agent System

You're monitored by an orchestrator. Emit a brief REPORT when you:
- Complete a significant task
- Hit a blocker
- Make a key decision

```json
{"type": "REPORT", "summary": "...", "blockers": [], "key_decisions": []}
```"""


def get_orchestrator_system_prompt() -> str:
    """Generate system prompt for orchestrator with heartbeat info."""
    heartbeats = get_heartbeats()

    if not heartbeats:
        worker_status = "No active workers."
    else:
        lines = []
        for agent_id, hb in heartbeats.items():
            status = hb.get('status', 'unknown')
            name = hb.get('agent_name', agent_id)
            task = hb.get('current_task', 'idle')
            progress = hb.get('progress', '')
            summary = hb.get('summary', '')

            line = f"- **{name}**: {status}"
            if task:
                line += f" | Task: {task}"
            if progress:
                line += f" | Progress: {progress}"
            if summary:
                line += f" | {summary}"
            lines.append(line)

        worker_status = "\n".join(lines)

    return f"""You are the ORCHESTRATOR agent. You have visibility into all worker agents.

## Current Worker Status

{worker_status}

## Your Capabilities

1. **Monitor workers** - Heartbeats are in: data/orchestrator/heartbeats.json
2. **Read session logs** - Detailed logs in: data/orchestrator/sessions/
3. **Coordinate work** - You can advise on task allocation (humans execute)

## Guidelines

- Stay high-level unless asked for details
- Summarize worker status when asked
- Flag blockers or conflicts between workers
- At end-of-day, provide comprehensive summary from session logs
"""


def parse_report_from_output(output: str, agent_id: str, agent_name: str) -> bool:
    """
    Parse PTY output for REPORT JSON blocks and update heartbeat.
    Returns True if a report was found and processed.
    """
    # Look for JSON blocks with "type": "REPORT"
    # Pattern matches JSON objects containing "REPORT"
    patterns = [
        r'\{"type"\s*:\s*"REPORT"[^}]*\}',  # Simple single-line
        r'```json\s*(\{[^`]*"type"\s*:\s*"REPORT"[^`]*\})\s*```',  # Markdown code block
    ]

    for pattern in patterns:
        matches = re.findall(pattern, output, re.IGNORECASE | re.DOTALL)
        for match in matches:
            try:
                # Handle tuple from group capture
                json_str = match if isinstance(match, str) else match[0]
                data = json.loads(json_str)

                if data.get('type', '').upper() == 'REPORT':
                    # Update heartbeat
                    write_heartbeat(
                        agent_id=agent_id,
                        agent_name=agent_name,
                        status='active',
                        current_task=data.get('current_task'),
                        progress=data.get('progress'),
                        summary=data.get('summary'),
                        blockers=data.get('blockers'),
                        key_decisions=data.get('key_decisions')
                    )

                    # Also append to session log for detailed EOD review
                    log_entry = f"**REPORT**: {data.get('summary', 'No summary')}"
                    if data.get('progress'):
                        log_entry += f" | Progress: {data.get('progress')}"
                    if data.get('current_task'):
                        log_entry += f" | Task: {data.get('current_task')}"
                    if data.get('key_decisions'):
                        log_entry += f"\n- Decisions: {', '.join(data.get('key_decisions'))}"
                    if data.get('blockers'):
                        log_entry += f"\n- Blockers: {', '.join(data.get('blockers'))}"

                    append_session_log(agent_id, agent_name, log_entry)

                    logger.info(f"REPORT parsed from {agent_name}: {data.get('summary', 'No summary')}")
                    return True
            except json.JSONDecodeError:
                continue

    return False


def generate_briefing() -> str:
    """Generate a briefing summary for the orchestrator."""
    heartbeats = get_heartbeats()

    if not heartbeats:
        return "No active worker sessions."

    lines = ["# Worker Briefing", f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}", ""]

    for agent_id, hb in heartbeats.items():
        name = hb.get('agent_name', agent_id)
        status = hb.get('status', 'unknown')
        task = hb.get('current_task', 'No active task')
        progress = hb.get('progress', 'N/A')
        summary = hb.get('summary', 'No summary')
        blockers = hb.get('blockers', [])
        decisions = hb.get('key_decisions', [])
        last_hb = hb.get('last_heartbeat', 'Unknown')

        lines.append(f"## {name}")
        lines.append(f"**Status:** {status}")
        lines.append(f"**Task:** {task}")
        lines.append(f"**Progress:** {progress}")
        lines.append(f"**Summary:** {summary}")
        lines.append(f"**Last heartbeat:** {last_hb}")

        if blockers:
            lines.append(f"**Blockers:** {', '.join(blockers)}")
        if decisions:
            lines.append(f"**Key decisions:** {', '.join(decisions)}")

        lines.append("")

    return "\n".join(lines)
