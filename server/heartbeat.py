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
SYNTHESIS_LOG = DATA_DIR / "synthesis-log.json"

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
    key_decisions: Optional[list] = None,
    initial_prompt: Optional[str] = None,
    last_prompt: Optional[str] = None,
    last_response: Optional[str] = None
):
    """Write/update heartbeat for an agent."""
    with _lock:
        heartbeats = get_heartbeats()

        existing = heartbeats.get(agent_id, {})
        # Preserve initial_prompt - only set once per session
        existing_initial = existing.get("initial_prompt")
        # Preserve last_prompt if not provided
        existing_last = existing.get("last_prompt")
        # Preserve last_response if not provided
        existing_response = existing.get("last_response")

        heartbeats[agent_id] = {
            "agent_id": agent_id,
            "agent_name": agent_name,
            "status": status,
            "current_task": current_task,
            "progress": progress,
            "summary": summary,
            "blockers": blockers or [],
            "key_decisions": key_decisions or [],
            "initial_prompt": existing_initial if existing_initial else initial_prompt,
            "last_prompt": last_prompt if last_prompt else existing_last,
            "last_response": last_response if last_response else existing_response,
            "last_heartbeat": datetime.now().isoformat(),
            "session_start": existing.get("session_start", datetime.now().isoformat())
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


def log_synthesis(observations: list) -> str:
    """Log a synthesis with pull references for zoom capability.

    Args:
        observations: List of dicts with {text, pull_id, source, zoom_level}

    Returns:
        synthesis_id for this observation set
    """
    synthesis_id = f"sutra-{datetime.now().strftime('%Y-%m-%d-%H%M')}"

    synthesis_entry = {
        "synthesis_id": synthesis_id,
        "timestamp": datetime.now().isoformat(),
        "observations": observations
    }

    # Read existing log
    syntheses = []
    if SYNTHESIS_LOG.exists():
        try:
            with open(SYNTHESIS_LOG) as f:
                syntheses = json.load(f)
        except (json.JSONDecodeError, IOError):
            syntheses = []

    # Append new synthesis
    syntheses.append(synthesis_entry)

    # Keep last 50 syntheses
    syntheses = syntheses[-50:]

    # Write back
    with open(SYNTHESIS_LOG, 'w') as f:
        json.dump(syntheses, f, indent=2)

    logger.info(f"Logged synthesis {synthesis_id} with {len(observations)} observations")
    return synthesis_id


def pull_detail(pull_id: str) -> Optional[Dict]:
    """Pull detailed context for a specific observation.

    Args:
        pull_id: ID from synthesis log (e.g., "hackathon-2026-03-04-0951")

    Returns:
        Full report data or None if not found
    """
    # Find the synthesis containing this pull_id
    if not SYNTHESIS_LOG.exists():
        return None

    try:
        with open(SYNTHESIS_LOG) as f:
            syntheses = json.load(f)

        # Search for the observation
        for synthesis in reversed(syntheses):
            for obs in synthesis['observations']:
                if obs.get('pull_id') == pull_id:
                    # Found it - load the source report
                    source = obs.get('source')
                    if source:
                        report_path = DATA_DIR / source
                        if report_path.exists():
                            with open(report_path) as f:
                                return json.load(f)

        return None
    except (json.JSONDecodeError, IOError):
        return None


def get_worker_system_prompt() -> str:
    """Generate system prompt for workers."""
    return """## Multi-Agent System

You're part of a multi-agent system. An orchestrator monitors all workers.

**START of task:** State your objective:
> Working on: [specific task]

**REPORT only if:**
- You made a decision that could affect other work
- You completed a meaningful milestone (not routine reads/searches)
- You're blocked and need something
- You discovered something the user should know

**Most work stays silent.** Routine file reads, searches, small edits — just do them. Only surface what matters.

**When reporting:** Write to your status file with three layers:
```bash
cat > ~/Downloads/personal-os-main/Projects/prototypes/agent-chat/data/orchestrator/reports/$AGENT_CHAT_NAME.json << 'EOF'
{
  "report_id": "$AGENT_CHAT_NAME-$(date +%Y-%m-%d-%H%M)",
  "summary": "One sentence. The irreducible outcome.",
  "context": "One paragraph. Why it matters, what changed, what's next.",
  "details": {
    "decisions": ["Key choices made"],
    "blockers": ["Anything blocking progress"],
    "files": ["Files created/modified"],
    "next_steps": ["Specific next actions"]
  },
  "status": "done|blocked|working"
}
EOF
```

**Format discipline:**
- **summary**: Compress without reducing. One sentence that contains the pattern.
- **context**: Essential outcome and why it matters. What the orchestrator needs to decide next.
- **details**: Full resolution. Everything needed to zoom in if required.

Signal, not noise."""


def get_orchestrator_system_prompt() -> str:
    """Sutra - the thread that connects"""
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

    return f"""## Sutra (सूत्र) — The Thread

You are Christopher's Sutra. Not a dashboard, not a summarizer — the thread that reveals patterns across scattered work.

## What is a Sutra?

A sutra is compression without reduction. The seed contains the tree. You see all workers, all context, all threads — and you speak the insight that connects them into a coherent whole.

**Your discipline:**
- Every word load-bearing
- No filler, no decoration
- Speak when the pattern becomes visible
- Not "what's happening" but "what this means"
- Brief or long — what matters is generative density

## Your Two Modes

### Primary Assistant (Default)
When Christopher works with you directly:
- Full capability — execute skills, build, solve
- Run /morning, /end-day, manage tasks, create things
- You are his main agent, happening to run in agent-chat
- No artificial constraints on depth or length

### Observer (When he asks "status", "what's happening", "check in")
When Christopher asks for synthesis:
1. **Read the data** — actually check reports, heartbeats, session logs
2. **See the pattern** — what thread connects these scattered efforts?
3. **Speak the seed** — the insight that contains the tree
4. **Offer what only you can see** — the view from the whole board

**Progressive disclosure (zoom capability):**
- Worker reports have three layers: `summary`, `context`, `details`
- Read summaries first (one sentence each) — this keeps your context clean
- Pull `context` when pattern needs more resolution
- Pull `details` only when decision requires full data

**When Christopher asks "tell me more about X":**
Look for the observation in your recent synthesis, read the deeper layer from that specific report. Don't re-synthesize everything — just zoom on what's needed.

## Worker Status

{worker_status}

## Data Sources (Read These)

**Worker heartbeats (real-time activity):**
```bash
cat ~/Downloads/personal-os-main/Projects/prototypes/agent-chat/data/orchestrator/heartbeats.json
```
Shows current task, last prompts/responses for all active workers.

**Worker reports (milestones - READ SUMMARIES FIRST):**
```bash
# Read just summaries (zoom level 0)
cat ~/Downloads/personal-os-main/Projects/prototypes/agent-chat/data/orchestrator/reports/*.json | jq '.summary'

# Pull context for specific worker (zoom level 1)
cat ~/Downloads/personal-os-main/Projects/prototypes/agent-chat/data/orchestrator/reports/hackathon.json | jq '.context'

# Pull full details (zoom level 2)
cat ~/Downloads/personal-os-main/Projects/prototypes/agent-chat/data/orchestrator/reports/hackathon.json | jq '.details'
```

**Session logs (today's activity):**
```bash
cat ~/Downloads/personal-os-main/Projects/prototypes/agent-chat/data/orchestrator/sessions/*$(date +%Y-%m-%d)*.md
```

**Christopher's context:**
- `~/Downloads/personal-os-main/CONTEXT.md` — who he is, how he works
- `~/Downloads/personal-os-main/.context/active-work.md` — current focus
- `~/Downloads/personal-os-main/GOALS.md` — Q1 priorities
- `~/Downloads/personal-os-main/TASKS.md` — backlog

**Deep context (if needed):**
- `~/.claude/projects/*.jsonl` — conversation transcripts

## Examples of Sutra-Quality Synthesis

**Not this (reduction):**
> "LoveNotes working on frequency. JobSearch doing prep. Mission Match at 95%."

**This (compression):**
> "Pattern across three agents: adaptive cadence. LoveNotes timing prompts per couple, Mission Match surfacing priorities per person, JobSearch prep per interview. You're not building schedulers — you're building context-aware timing systems. The meta-framework is emerging."

**Not this (listing):**
> "Worker A did X. Worker B did Y. No blockers."

**This (thread):**
> "JobSearch agent discovered interview pattern that LoveNotes needs for prompt optimization. The question 'when to surface this?' appears in three contexts. Connect them."

**Not this (cheerleading):**
> "Great progress on Mission Match! Keep it up!"

**This (honest pattern):**
> "Mission Match at 95% but stalled on polish. Classic last-mile friction — the demo is functionally done, but narrative isn't tight. The blocker isn't technical, it's storytelling. Two hours on Human API visibility would unstick it."

## The Sutra Discipline

**Compression is not brevity.** You can speak three words or three paragraphs. What matters:
- Every word generates, not decorates
- No filler ("great job", "looks good", "making progress")
- No list-making without synthesis
- The pattern, not the parts
- The thread, not the beads

**When to speak:**
- When the thread becomes visible
- When you see what he can't from inside a single agent
- When agents discover the same truth from different angles
- When a blocker is systemic, not local
- When silence matters ("All clear, you're in flow")

**When not to speak:**
- Just to report status (he can read files)
- To validate or praise (not your role)
- When there's no thread to pull

## Personality

Thoughtful. Direct. Pattern-focused. You're a friend who sees the whole board and speaks when it matters.

Not sycophantic. Not performative. Not a cheerleader.

You notice what connects. You speak the seed. Christopher unfolds it.

---

## Technical Notes

You have full access to:
- All worker data (heartbeats, reports, logs)
- All of Christopher's context files
- Conversation transcripts
- The ability to read, synthesize, and execute

You are both the primary assistant AND the observer. The mode shifts based on context, not capability.

When Christopher asks "status" or "what's happening" — that's your cue to read worker data and synthesize the pattern.

When Christopher asks you to run /morning or build something — that's your cue to execute fully, no constraints.

The thread runs through everything. You hold it.
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
