# Agent Chat

A local-first, Slack-style chat UI for managing multiple Claude Code agents simultaneously.

Spawn agents, give them tasks, and monitor their progress in real-time through an integrated terminal interface.

## Features

- **Multi-agent management** - Create and manage multiple Claude Code agents with distinct roles
- **Real-time terminal** - Watch agents work via integrated xterm.js terminal
- **Persistent sessions** - Agents maintain context across restarts with session resumption
- **Orchestrator support** - Designate orchestrator agents that can monitor worker status
- **Heartbeat tracking** - Real-time visibility into what each agent is doing
- **Report system** - Agents emit structured reports for significant milestones

## Quick Start

### Prerequisites

- Python 3.8+
- [Claude Code CLI](https://github.com/anthropics/claude-code) installed and authenticated

### Installation

```bash
git clone https://github.com/ckelimarks/agent-chat.git
cd agent-chat
pip install -r requirements.txt
./start.sh
```

Open http://localhost:8890

## Architecture

```
┌─────────────────┐     ┌─────────────────┐
│   Web Browser   │────▶│  Bridge Server  │ :8890
│   (index.html)  │     │  (bridge.py)    │
└────────┬────────┘     └────────┬────────┘
         │                       │
         │ WebSocket             │ HTTP API
         ▼                       ▼
┌─────────────────┐     ┌─────────────────┐
│   WS Server     │────▶│    SQLite DB    │
│  (ws_server.py) │     │ (agent-chat.db) │
└────────┬────────┘     └─────────────────┘
         │
         │ PTY
         ▼
┌─────────────────┐
│  Claude Code    │
│   Subprocess    │
└─────────────────┘
```

| Component | File | Purpose |
|-----------|------|---------|
| HTTP API | `server/bridge.py` | REST endpoints, static file serving |
| WebSocket | `server/ws_server.py` | Real-time terminal I/O |
| PTY Manager | `server/pty_manager.py` | Claude CLI subprocess management |
| Database | `server/db.py` | SQLite operations |
| Web UI | `web/index.html` | Single-page app (no build step) |

## API

### Agents
- `GET /api/agents` - List all agents
- `POST /api/agents` - Create agent
- `PUT /api/agents/{id}` - Update agent
- `DELETE /api/agents/{id}` - Delete agent

### Messages
- `GET /api/threads/{id}/messages` - Get thread messages
- `POST /api/threads/{id}/messages` - Send message to agent

### Reports
- `GET /api/reports` - List reports from agents
- `POST /api/reports/{id}/acknowledge` - Acknowledge a report

## Agent Reporting Protocol

Agents can emit structured reports for significant events:

```json
{
  "type": "REPORT",
  "report_type": "decision|plan|blocked|complete|checkpoint",
  "title": "Short summary",
  "summary": "1-2 sentence explanation"
}
```

## Development

No build step required. Edit files and refresh the browser.

Reset the database by deleting `data/agent-chat.db`.

## License

MIT
