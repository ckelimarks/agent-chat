#!/bin/bash
# PostToolUse hook for automatic heartbeat updates
# Fires on every tool use and infers activity from the tool name/input
# Only processes if AGENT_CHAT_ID is set (i.e., running inside agent-chat)

# Check if this is an agent-chat session
if [ -z "$AGENT_CHAT_ID" ]; then
    exit 0
fi

# Read hook input from stdin
INPUT=$(cat)

# Extract tool name and input
TOOL_NAME=$(echo "$INPUT" | jq -r '.tool_name // empty' 2>/dev/null)
TOOL_INPUT=$(echo "$INPUT" | jq -r '.tool_input // empty' 2>/dev/null)

# Skip if no tool name
if [ -z "$TOOL_NAME" ]; then
    exit 0
fi

# Infer task description from tool name
case "$TOOL_NAME" in
    "Read")
        FILE_PATH=$(echo "$TOOL_INPUT" | jq -r '.file_path // "file"' 2>/dev/null)
        TASK="Reading: $(basename "$FILE_PATH")"
        ;;
    "Edit")
        FILE_PATH=$(echo "$TOOL_INPUT" | jq -r '.file_path // "file"' 2>/dev/null)
        TASK="Editing: $(basename "$FILE_PATH")"
        ;;
    "Write")
        FILE_PATH=$(echo "$TOOL_INPUT" | jq -r '.file_path // "file"' 2>/dev/null)
        TASK="Writing: $(basename "$FILE_PATH")"
        ;;
    "Bash")
        CMD=$(echo "$TOOL_INPUT" | jq -r '.command // ""' 2>/dev/null | head -c 50)
        if [ -n "$CMD" ]; then
            TASK="Running: $CMD..."
        else
            TASK="Running command"
        fi
        ;;
    "Grep")
        PATTERN=$(echo "$TOOL_INPUT" | jq -r '.pattern // ""' 2>/dev/null | head -c 30)
        TASK="Searching: $PATTERN"
        ;;
    "Glob")
        PATTERN=$(echo "$TOOL_INPUT" | jq -r '.pattern // ""' 2>/dev/null | head -c 30)
        TASK="Finding files: $PATTERN"
        ;;
    "Task")
        DESC=$(echo "$TOOL_INPUT" | jq -r '.description // ""' 2>/dev/null | head -c 40)
        TASK="Delegating: $DESC"
        ;;
    "WebFetch")
        URL=$(echo "$TOOL_INPUT" | jq -r '.url // ""' 2>/dev/null | head -c 40)
        TASK="Fetching: $URL"
        ;;
    "WebSearch")
        QUERY=$(echo "$TOOL_INPUT" | jq -r '.query // ""' 2>/dev/null | head -c 30)
        TASK="Searching web: $QUERY"
        ;;
    *)
        TASK="Using: $TOOL_NAME"
        ;;
esac

# Send heartbeat update to bridge server
curl -s -X POST "http://localhost:8890/api/heartbeat" \
    -H "Content-Type: application/json" \
    -d "$(jq -n \
        --arg agent_id "$AGENT_CHAT_ID" \
        --arg agent_name "$AGENT_CHAT_NAME" \
        --arg task "$TASK" \
        --arg tool "$TOOL_NAME" \
        '{
            agent_id: $agent_id,
            agent_name: $agent_name,
            current_task: $task,
            last_tool: $tool,
            status: "active"
        }')" > /dev/null 2>&1 &

exit 0
