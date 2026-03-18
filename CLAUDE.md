# Agent Chat

Local-first Slack-style chat UI for managing multiple Claude Code agents.

## Quick Start

```bash
./start.sh
# Open http://localhost:8890
```

## 👁 Visual Canvas

Agents can draw diagrams, mockups, and visualizations to a live canvas visible in the UI.

**To draw on canvas:**
```bash
curl -X POST http://localhost:8890/api/canvas \
  -H "Content-Type: application/json" \
  -d '{"html":"<html>...your HTML here...</html>"}'
```

**Canvas capabilities:**
- Self-contained HTML with CDN libraries (Mermaid, Chart.js, D3, etc.)
- Live-reloads when updated
- Visible to user as split-screen panel
- Any agent can append/update canvas content

**Template:**
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
    graph TD; A-->B; B-->C
  </div>
  <script>mermaid.initialize({startOnLoad:true});</script>
</body>
</html>
```

## Architecture

- **Web UI**: Single-page app served from `web/index.html`
- **Bridge Server**: Python HTTP server at port 8890
- **SQLite Database**: Persistent storage in `data/agent-chat.db`
- **Process Manager**: Spawns Claude CLI subprocesses per agent

## Key Files

| File | Purpose |
|------|---------|
| `server/bridge.py` | HTTP API server |
| `server/db.py` | SQLite operations |
| `server/process_manager.py` | Claude CLI subprocess management |
| `server/schema.sql` | Database schema |
| `web/index.html` | Complete SPA (no build step) |
| `hooks/agent-report.sh` | PostToolUse hook for REPORT detection |

## API Endpoints

### Agents
- `GET /api/agents` - List all agents
- `POST /api/agents` - Create agent
- `PUT /api/agents/{id}` - Update agent
- `DELETE /api/agents/{id}` - Delete agent

### Messages
- `GET /api/threads/{id}/messages` - Get messages
- `GET /api/threads/{id}/messages?since={id}` - Get new messages
- `POST /api/threads/{id}/messages` - Send message

### Reports
- `GET /api/reports` - List reports
- `POST /api/reports` - Add report (from hooks)
- `POST /api/reports/{id}/acknowledge` - Acknowledge report

## Reporting Protocol

Agents emit REPORT JSON for significant events:

```json
{
  "type": "REPORT",
  "report_type": "decision|plan|blocked|complete|checkpoint",
  "title": "Short summary",
  "summary": "1-2 sentence explanation"
}
```

## Development

No build step required - just edit files and refresh the browser.

Database can be reset by deleting `data/agent-chat.db`.
