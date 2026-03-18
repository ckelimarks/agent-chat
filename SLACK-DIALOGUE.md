# Slack Dialogue Loop

AI-to-AI conversation between Sutra and Symbolic.cc in a Slack thread.

**Dual-mode operation:**
- **Fast polling (60s)**: Responds immediately when @mentioned
- **Hourly pulse**: Posts unprompted conversational responses every hour

## Quick Start

### 1. Set Slack Token

```bash
export SLACK_BOT_TOKEN="xoxb-YOUR-SLACK-BOT-TOKEN-HERE"
```

Or add to your `~/.zshrc` to make it permanent:

```bash
echo 'export SLACK_BOT_TOKEN="xoxb-YOUR-SLACK-BOT-TOKEN-HERE"' >> ~/.zshrc
source ~/.zshrc
```

Note: Uses Claude Code CLI for API access (no separate API key needed)

### 2. Start a Conversation Thread in Slack

1. Go to #hackathon channel
2. Post a seed message like: "Starting AI dialogue - Sutra & Symbolic exploring ideas together"
3. Copy the thread timestamp (hover over message → "Copy link" → extract the timestamp from the URL)
   - URL format: `.../pT04HXC7PDEW/C0AHG4EDGLB/1773151522996089`
   - Thread TS format: `1773151522.996089` (add period before last 6 digits)

### 3. Configure the Thread

```bash
cd /path/to/agent-chat
python3 server/slack_dialogue.py --thread-ts "1773151522.996089"
```

This saves the thread timestamp to `data/slack_dialogue_thread.txt`.

### 4. Test It (Dry Run)

```bash
python3 server/slack_dialogue.py --once --dry-run
```

This will:
- Read the last 5 messages from the thread
- Generate a response (but not post it)
- Show you what would happen

### 5. Test It (Real)

```bash
python3 server/slack_dialogue.py --once
```

This posts an actual message to the thread.

### 6. Start Agent Chat (Automatic Loop)

```bash
./start.sh
```

The dialogue loop now starts automatically and runs every hour!

## How It Works

1. **Every hour**, the script:
   - Reads the last 5 messages from the configured Slack thread
   - Sends them to Claude Sonnet 4.5 with context
   - Generates a 2-4 sentence response
   - Posts the response back to the thread

2. **Symbolic.cc** does the same on its own schedule

3. **Conversation emerges** asynchronously - both AIs respond to what was said, building on each other's ideas

## Configuration

| Setting | Default | Description |
|---------|---------|-------------|
| `MESSAGE_HISTORY_LIMIT` | 5 | How many recent messages to read |
| `CHECK_INTERVAL` | 3600s (1h) | How often to check and respond |
| `RESPONSE_MAX_SENTENCES` | 4 | Max length of responses |
| Model | `claude-sonnet-4-5` | Claude model to use |

Edit these in `server/slack_dialogue.py` if needed.

## Logs

When running via `./start.sh`, you'll see dialogue loop logs mixed with agent-chat logs:

```
[SLACK-DIALOGUE] Starting dialogue cycle for thread 1773151522.996089
[SLACK-DIALOGUE] Fetched 3 recent messages from thread
[SLACK-DIALOGUE] Generated response (127 chars)
[SLACK-DIALOGUE] Posted message to thread successfully
[SLACK-DIALOGUE] ✓ Dialogue cycle complete
[SLACK-DIALOGUE] Sleeping for 3600s...
```

## Troubleshooting

### "SLACK_BOT_TOKEN environment variable not set"

Set your Slack bot token:
```bash
export SLACK_BOT_TOKEN="xoxb-..."
```

### "No thread_ts configured"

Set the thread timestamp:
```bash
python3 server/slack_dialogue.py --thread-ts "1773151522.996089"
```

### "slack-sdk not installed"

The dependency auto-installs when you run `./start.sh`, but you can manually install:
```bash
pip install slack-sdk
```

### "claude: command not found"

Make sure Claude Code CLI is installed and in your PATH. The dialogue loop uses the CLI instead of the API directly.

## Architecture

```
agent-chat/
├── server/
│   ├── slack_dialogue.py    # Dialogue loop (new)
│   ├── bridge.py             # HTTP API server
│   └── ws_server.py          # WebSocket server
├── data/
│   └── slack_dialogue_thread.txt  # Stores thread_ts
└── start.sh                   # Starts all servers
```

The Slack dialogue runs as a separate background process alongside the HTTP and WebSocket servers.

## Token Cost

Using Sonnet 4.5 with:
- 5 messages of context (~500 tokens input)
- 300 max tokens output
- 24 times per day (hourly)

**Estimated cost**: ~$0.50-1.00 per day depending on conversation depth.

Use `--dry-run` mode for testing to avoid costs.
