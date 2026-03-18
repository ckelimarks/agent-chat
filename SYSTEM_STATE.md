# Agent Chat - Current System State

**Last Updated:** 2026-03-03 1:03 PM

## What's Currently Running
- HTTP Server (bridge.py): http://localhost:8890 - PID 9803
- WebSocket Server (ws_server.py): ws://localhost:8891 - PID 9804
- Database: `data/agent-chat.db` (SQLite, initialized, has schema)

## DON'T REBUILD
- ✅ Servers are running - just use them
- ✅ Database exists with schema
- ✅ Web UI at web/index.html works
- ✅ start.sh script works

## To Verify State (don't assume broken)
```bash
# Check if running
ps aux | grep -E "(bridge|ws_server)" | grep -v grep
# Check ports
lsof -i :8890 -i :8891
# Check database
ls -lh data/agent-chat.db
```

## Architecture
- Single-page app (no build step)
- Python backend (no npm, no node)
- SQLite for persistence
- Claude CLI subprocesses per agent

## Current Work Context
[Add your current plan/next steps here before compaction]

## Next Session Should
- Read this file first
- Verify state before assuming anything needs rebuilding
- Check what's running before starting services
