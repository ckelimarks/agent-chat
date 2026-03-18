# Agent Chat

A local-first, Slack-style chat interface for orchestrating multiple Claude Code agents simultaneously. Spawn specialized agents, assign tasks, and monitor their work in real-time through an integrated terminal and visual canvas.

## Features

### 🤖 Multi-Agent Orchestration
- **Parallel agents** - Run multiple Claude Code agents simultaneously with distinct roles
- **Real-time monitoring** - Watch agents work via integrated xterm.js terminals
- **Persistent sessions** - Agents maintain context across restarts with automatic session resumption
- **Heartbeat tracking** - Live visibility into what each agent is doing

### 👁 Visual Canvas
- **Live diagrams** - Agents can draw Mermaid diagrams, charts, and visualizations
- **Interactive UI** - Canvas updates in real-time as agents generate visuals
- **Rich libraries** - Built-in support for Mermaid, Chart.js, D3, and other CDN libraries
- **Agent-to-user communication** - Visual output alongside terminal conversations

### 📊 Orchestrator Pattern
- **Designated orchestrators** - Assign orchestrator agents that monitor worker status
- **Report system** - Workers emit structured reports for milestones, blockers, and completions
- **Acknowledgment flow** - Orchestrators can acknowledge and respond to reports
- **Coordination** - Multi-agent workflows with explicit checkpoints

### 🔄 Slack Integration (Optional)
- **AI-to-AI dialogue** - Connect agents to Slack for asynchronous conversations
- **Dual-mode operation** - Fast polling (60s) for mentions + hourly pulse for unprompted responses
- **Thread tracking** - Maintains conversation context across sessions

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

### Optional: Slack Integration

1. Copy `.env.example` to `.env`
2. Add your `SLACK_BOT_TOKEN` from https://api.slack.com/apps
3. Configure thread timestamp (see [SLACK-DIALOGUE.md](SLACK-DIALOGUE.md))

## Architecture

```
┌─────────────────┐     ┌─────────────────┐
│   Web Browser   │────▶│  Bridge Server  │ :8890
│   (SPA)         │     │  (bridge.py)    │
└────────┬────────┘     └────────┬────────┘
         │                       │
         │ WebSocket             │ HTTP API
         ▼                       ▼
┌─────────────────┐     ┌─────────────────┐
│   WS Server     │────▶│    SQLite DB    │
│ (ws_server.py)  │     │ (agent-chat.db) │
└────────┬────────┘     └─────────────────┘
         │
         │ PTY/Process
         ▼
┌─────────────────┐
│  Claude Code    │
│   Subprocesses  │
└─────────────────┘
```

### Components

| Component | File | Purpose |
|-----------|------|---------|
| HTTP API | `server/bridge.py` | REST endpoints, static file serving, canvas updates |
| WebSocket | `server/ws_server.py` | Real-time terminal I/O and message streaming |
| Process Manager | `server/process_manager.py` | Claude CLI subprocess lifecycle management |
| PTY Manager | `server/pty_manager.py` | Pseudo-terminal allocation for agent terminals |
| Database | `server/db.py` | SQLite operations for agents, threads, messages |
| Web UI | `web/index.html` | Single-page app with no build step |
| Hooks | `hooks/agent-report.sh` | PostToolUse hook for REPORT detection |
| Slack Integration | `server/slack_dialogue.py` | AI-to-AI conversation loop (optional) |

## API Endpoints

### Agents
- `GET /api/agents` - List all agents
- `POST /api/agents` - Create agent with role and config
- `PUT /api/agents/{id}` - Update agent metadata
- `DELETE /api/agents/{id}` - Delete agent and cleanup subprocess

### Messages
- `GET /api/threads/{id}/messages` - Get thread message history
- `GET /api/threads/{id}/messages?since={id}` - Get new messages (polling)
- `POST /api/threads/{id}/messages` - Send message to agent

### Reports
- `GET /api/reports` - List reports from all agents
- `POST /api/reports` - Add report (typically from hooks)
- `POST /api/reports/{id}/acknowledge` - Acknowledge report

### Canvas
- `POST /api/canvas` - Update visual canvas with HTML content
- `GET /api/canvas` - Retrieve current canvas state

## Canvas Visualization

Agents can draw diagrams, charts, and visualizations to a live canvas visible in the UI.

**Agent usage:**
```bash
curl -X POST http://localhost:8890/api/canvas \
  -H "Content-Type: application/json" \
  -d '{"html":"<html>...your HTML here...</html>"}'
```

**Example - Mermaid Diagram:**
```html
<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <script src="https://cdn.jsdelivr.net/npm/mermaid/dist/mermaid.min.js"></script>
  <style>body { margin: 24px; }</style>
</head>
<body>
  <div class="mermaid">
    graph TD
      A[Agent 1] -->|Reports to| B[Orchestrator]
      C[Agent 2] -->|Reports to| B
      B -->|Coordinates| D[Final Output]
  </div>
  <script>mermaid.initialize({startOnLoad:true});</script>
</body>
</html>
```

Canvas capabilities:
- Self-contained HTML with CDN libraries
- Live-reloads when updated
- Visible to user as split-screen panel
- Any agent can append/update canvas content

See [CANVAS.md](CANVAS.md) for more examples.

## Agent Reporting Protocol

Agents emit structured JSON reports for significant events. The `hooks/agent-report.sh` PostToolUse hook automatically detects and captures these reports.

**Report format:**
```json
{
  "type": "REPORT",
  "report_type": "decision|plan|blocked|complete|checkpoint",
  "title": "Short summary",
  "summary": "1-2 sentence explanation",
  "details": {
    "key": "value"
  }
}
```

**Report types:**
- `decision` - Major decision made
- `plan` - Implementation plan created
- `blocked` - Agent is blocked and needs help
- `complete` - Task completed
- `checkpoint` - Progress milestone reached

Reports appear in the orchestrator's dashboard and can be acknowledged or responded to.

## Multi-Agent Workflows

**Example orchestrator setup:**

1. Create orchestrator agent:
```json
{
  "name": "Orchestrator",
  "role": "orchestrator",
  "system_prompt": "You coordinate work between agents..."
}
```

2. Create worker agents:
```json
{
  "name": "Frontend Builder",
  "role": "worker",
  "system_prompt": "You build React components..."
}
```

3. Workers emit reports at checkpoints:
```bash
# From worker agent via claude
echo '{"type":"REPORT","report_type":"checkpoint","title":"Component built","summary":"Created UserProfile component with tests"}'
```

4. Orchestrator sees reports and responds or delegates next tasks

## Development

**No build step required** - Edit files and refresh the browser.

**Reset database:**
```bash
rm data/agent-chat.db
# Database auto-recreates on next ./start.sh
```

**View logs:**
```bash
# Main server logs
tail -f logs/bridge.log

# Slack dialogue logs (if enabled)
tail -f data/slack_dialogue.log
```

**Test canvas locally:**
```bash
./test-canvas.sh
```

## Configuration

Edit `server/bridge.py` to customize:
- Port (default: 8890)
- Database path (default: `data/agent-chat.db`)
- Max agents (default: unlimited)

Edit `server/slack_dialogue.py` to customize:
- Message history limit (default: 5)
- Check interval (default: 3600s)
- Response length (default: 4 sentences)

## File Structure

```
agent-chat/
├── server/
│   ├── bridge.py              # HTTP API server
│   ├── ws_server.py           # WebSocket server
│   ├── db.py                  # SQLite operations
│   ├── process_manager.py     # Subprocess management
│   ├── pty_manager.py         # PTY allocation
│   ├── slack_dialogue.py      # Slack integration (optional)
│   ├── schema.sql             # Database schema
│   └── inject_statusline.js   # Token tracking injection
├── web/
│   └── index.html             # Complete SPA (no build)
├── hooks/
│   ├── agent-report.sh        # Report detection hook
│   └── auto-heartbeat.sh      # Heartbeat tracking hook
├── data/
│   ├── agent-chat.db          # SQLite database (gitignored)
│   └── canvas.html            # Current canvas state (gitignored)
├── docs/                      # Additional documentation
├── .env.example               # Environment template
├── requirements.txt           # Python dependencies
└── start.sh                   # Launch script
```

## Troubleshooting

**"claude: command not found"**
- Install Claude Code CLI: https://github.com/anthropics/claude-code

**"Port 8890 already in use"**
```bash
lsof -ti:8890 | xargs kill -9
./start.sh
```

**Agent not responding**
- Check WebSocket connection in browser console
- Verify Claude Code CLI is authenticated: `claude --version`
- Check agent process: `ps aux | grep claude`

**Canvas not updating**
- Verify POST request succeeded: check Network tab
- Ensure canvas HTML is valid and self-contained
- Check `data/canvas.html` file was created

## Advanced Usage

See documentation for advanced topics:
- [CANVAS.md](CANVAS.md) - Canvas visualization examples
- [SLACK-DIALOGUE.md](SLACK-DIALOGUE.md) - AI-to-AI Slack integration
- [INFRA.md](INFRA.md) - Infrastructure and deployment notes
- [AGENT-MATCH-SPEC.md](AGENT-MATCH-SPEC.md) - Orchestrator pattern specification

## License

MIT
