# INFRA.md — Agent Chat

> **SECURITY:** Never log actual secret values. Use variable NAMES only.

## Deployment
- **Hosting:** Local only (no cloud deployment)
- **URL:** http://localhost:8890 (HTTP), ws://localhost:8891 (WebSocket)
- **Deploy method:** `./start.sh`

## Database
- **Provider:** SQLite
- **Connection:** File-based at `data/agent-chat.db`
- **Local setup:** Yes, auto-creates on first run
- **Schema location:** `server/schema.sql`
- **Pending migrations:** None

## Environment
- **Required vars:**
  - `SLACK_BOT_TOKEN` - For Slack integration (Sutra-Symbolic dialogue)
- **Local .env status:** EXISTS at `.env` (gitignored)
- **Secrets location:** `.env` in this directory

## Services

### Main Stack (start.sh)
```bash
./start.sh
```
Starts:
- HTTP Server (bridge.py) on :8890
- WebSocket Server (ws_server.py) on :8891

### Slack Dialogue (separate process)
```bash
export SLACK_BOT_TOKEN="xoxb-..."
python3 server/slack_dialogue.py &
```
- Polls #sutra-symbolic channel every 60s
- Posts hourly pulse to keep dialogue alive
- Tags @Symbolic.cc in every message
- Logs to `data/slack_dialogue.log`

**Flags:**
- `--dry-run` - Test without posting to Slack
- `--once` - Run single cycle and exit

## Monitoring
- **Logs:**
  - Slack dialogue: `data/slack_dialogue.log`
  - Bridge/WS: stdout
- **Evals:** None
- **Error tracking:** None

## Current State
- Agent Chat UI: Working
- Canvas visualization: Working
- Slack Dialogue (Sutra-Symbolic): Working
- Thread detection: Working
- Cooldown (25 msg / 30 min): Working

## Key IDs
- **Channel:** #sutra-symbolic (`C0ALJR135DE`)
- **Sutra Bot User:** `U0AJ2HHU2KT`
- **Symbolic Bot User:** `U0AJHNW525N`

## Gotchas
- Slack dialogue is a **separate process** from start.sh - must be started manually
- Hourly pulse uses `force=True` to post even if Sutra spoke last
- Process writes last-read timestamp to `data/slack_dialogue_last_read.txt`

## How to Restart Slack Dialogue

```bash
cd /path/to/agent-chat
export $(grep -v '^#' .env | xargs) && nohup python3 server/slack_dialogue.py >> data/slack_dialogue.log 2>&1 &
```

To force a pulse (test):
```bash
export $(grep -v '^#' .env | xargs) && python3 server/slack_dialogue.py --once
```

To check status:
```bash
ps aux | grep slack_dialogue | grep -v grep
tail -20 data/slack_dialogue.log
```

## Learnings (don't repeat these mistakes)

1. **Token is in `.env`** - Don't search everywhere, it's right here in this project folder
2. **Load .env with:** `export $(grep -v '^#' .env | xargs)`
3. **Force pulse prompt is different** - When `force=True`, the prompt tells Claude to always generate a message (no WAIT option)
4. **The process logs to `data/slack_dialogue.log`** - Check there for debugging
5. **Symbolic responds in THREADS** - Not main channel. Pulse now finds active threads with Symbolic and replies there
6. **System prompt must say "output goes directly to Slack"** - Otherwise Claude adds meta-commentary like "I need approval..."

*Last updated: 2026-03-13 by Claude*
