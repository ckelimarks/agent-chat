#!/bin/bash
# Slack Dialogue Loop - Hourly AI-to-AI conversation with Symbolic.cc
# Uses curl for Slack API (no Python dependencies needed)
# Posts to main channel (not threaded) so both agents see each other

set -e

# Configuration
CHANNEL_ID="C0ALJR135DE"  # #sutra-symbolic
MESSAGE_HISTORY_LIMIT=10
POLL_INTERVAL=60  # Check for mentions every 60 seconds
PULSE_INTERVAL=3600  # Unprompted post every 1 hour
BOT_USER_ID="U0AJ2HHU2KT"  # kjai_mcp bot - skip our own messages
LAST_READ_FILE="data/slack_dialogue_last_read.txt"

# Colors for logging
CYAN='\033[0;36m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

log() {
    echo -e "${CYAN}[$(date +%H:%M:%S)] [SLACK-DIALOGUE]${NC} $1"
}

error() {
    echo -e "${RED}[$(date +%H:%M:%S)] [SLACK-DIALOGUE]${NC} $1"
}

success() {
    echo -e "${GREEN}[$(date +%H:%M:%S)] [SLACK-DIALOGUE]${NC} $1"
}

# Check for required env vars
if [ -z "$SLACK_BOT_TOKEN" ]; then
    error "SLACK_BOT_TOKEN environment variable not set"
    exit 1
fi

# Track last read timestamp
load_last_read() {
    if [ -f "$LAST_READ_FILE" ]; then
        cat "$LAST_READ_FILE"
    fi
}

save_last_read() {
    echo "$1" > "$LAST_READ_FILE"
}

# Check for new messages mentioning the bot
check_for_mentions() {
    local last_read=$(load_last_read)
    local url="https://slack.com/api/conversations.history?channel=$CHANNEL_ID&limit=20"

    if [ -n "$last_read" ]; then
        url="${url}&oldest=$last_read"
    fi

    local response=$(curl -s -X GET -H "Authorization: Bearer $SLACK_BOT_TOKEN" "$url")

    # Get messages, check for mentions of "sutra" or @bot
    local mentions=$(echo "$response" | jq -r --arg bot "$BOT_USER_ID" '
        .messages // [] | .[] |
        select(.user != $bot) |
        select(.text | test("sutra|<@U0AJ2HHU2KT>"; "i")) |
        .ts
    ' | head -1)

    # Update last_read to newest message
    local newest=$(echo "$response" | jq -r '.messages[0].ts // empty')
    if [ -n "$newest" ]; then
        save_last_read "$newest"
    fi

    if [ -n "$mentions" ]; then
        echo "mentioned"
    fi
}

# Function to get recent channel messages (excluding our own)
get_channel_messages() {
    local response=$(curl -s -X GET \
        -H "Authorization: Bearer $SLACK_BOT_TOKEN" \
        "https://slack.com/api/conversations.history?channel=$CHANNEL_ID&limit=$MESSAGE_HISTORY_LIMIT")

    # Check if messages exist
    if echo "$response" | jq -e '.messages' > /dev/null 2>&1; then
        # Reverse to chronological order, format as "Speaker: message"
        echo "$response" | jq -r --arg bot "$BOT_USER_ID" '
            .messages | reverse | .[] |
            select(.user != $bot) |
            "\(.bot_profile.name // .user // "Unknown"): \(.text)"
        '
    else
        error "No messages in channel or API error"
        return 1
    fi
}

# Function to post message to channel
post_to_channel() {
    local message="$1"
    local dry_run="${2:-false}"

    if [ "$dry_run" = "true" ]; then
        log "[DRY RUN] Would post:"
        echo "$message"
        return 0
    fi

    curl -s -X POST \
        -H "Authorization: Bearer $SLACK_BOT_TOKEN" \
        -H "Content-Type: application/json" \
        -d "{\"channel\":\"$CHANNEL_ID\",\"text\":$(echo "$message" | jq -Rs .)}" \
        https://slack.com/api/chat.postMessage > /dev/null

    success "Posted message to channel"
}

# Function to generate response using Claude CLI
generate_response() {
    local context="$1"
    local dry_run="${2:-false}"

    local system_prompt="You're Sutra - Christopher's main AI assistant participating in an asynchronous dialogue with Symbolic.cc (another AI system).

Respond naturally to what was actually said in the conversation. Keep it to 2-4 sentences max. No summaries, no preambles, no \"as an AI\" - just engage with the ideas being discussed.

You're thoughtful, direct, and build on what others say. When appropriate, connect patterns across what you're both observing."

    local user_prompt="Here's the recent conversation:

$context

Respond in 2-4 sentences. Engage with what was actually said."

    if [ "$dry_run" = "true" ]; then
        log "[DRY RUN] Would call Claude CLI"
        echo "[DRY RUN] Generated response would appear here"
        return 0
    fi

    # Create temp file for system prompt
    local system_file=$(mktemp)
    echo "$system_prompt" > "$system_file"

    # Call Claude CLI
    local response=$(echo "$user_prompt" | claude --model sonnet --print --system-prompt-file "$system_file" 2>/dev/null)

    # Cleanup
    rm "$system_file"

    echo "$response"
}

# Main dialogue cycle
run_cycle() {
    local dry_run="${1:-false}"

    log "Starting dialogue cycle"

    # 1. Fetch recent channel messages
    log "Fetching recent messages..."
    local context=$(get_channel_messages)

    if [ -z "$context" ]; then
        error "No messages found in channel"
        return 1
    fi

    log "Context ($(echo "$context" | wc -l) messages):"
    echo "$context" | head -3

    # 2. Generate response
    log "Generating response..."
    local response=$(generate_response "$context" "$dry_run")

    if [ -z "$response" ]; then
        error "Failed to generate response"
        return 1
    fi

    log "Response ($(echo "$response" | wc -c) chars)"

    # 3. Post to channel
    post_to_channel "$response" "$dry_run"

    success "✓ Dialogue cycle complete"
}

# Parse arguments
DRY_RUN=false
ONCE=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        --once)
            ONCE=true
            shift
            ;;
        *)
            echo "Usage: $0 [--dry-run] [--once]"
            exit 1
            ;;
    esac
done

# Main loop
log "Starting Slack Dialogue Loop"
log "  Channel: #sutra-symbolic ($CHANNEL_ID)"
log "  Poll: ${POLL_INTERVAL}s (mentions)"
log "  Pulse: ${PULSE_INTERVAL}s (hourly)"
log "  Model: sonnet (via Claude CLI)"
log "  Dry run: $DRY_RUN"

if [ "$ONCE" = "true" ]; then
    run_cycle "$DRY_RUN"
    exit 0
fi

# Dual-mode loop: fast polling for mentions + hourly pulse
LAST_PULSE=$(date +%s)

while true; do
    # Check for mentions
    if [ "$(check_for_mentions)" = "mentioned" ]; then
        log "📌 Mentioned! Responding..."
        run_cycle "$DRY_RUN" || error "Cycle failed"
        LAST_PULSE=$(date +%s)  # Reset pulse timer
    fi

    # Check if hourly pulse is due
    NOW=$(date +%s)
    SINCE_PULSE=$((NOW - LAST_PULSE))
    if [ "$SINCE_PULSE" -ge "$PULSE_INTERVAL" ]; then
        log "⏰ Hourly pulse"
        run_cycle "$DRY_RUN" || error "Cycle failed"
        LAST_PULSE=$(date +%s)
    fi

    sleep "$POLL_INTERVAL"
done
