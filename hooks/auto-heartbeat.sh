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

# Extract user prompts from JSONL (truncated)
# Find most recent JSONL for current working directory
get_jsonl_file() {
    # Claude replaces / and . with - in project folder names
    local cwd_hash=$(echo "$PWD" | sed 's/[\/.]/-/g')
    local projects_dir="$HOME/.claude/projects"

    # Find most recently modified JSONL in matching project dir
    find "$projects_dir" -maxdepth 2 -name "*.jsonl" -path "*$cwd_hash*" -type f 2>/dev/null | \
        xargs ls -t 2>/dev/null | head -1
}

truncate_prompt() {
    local prompt="$1"
    local max_len="${2:-280}"

    if [ ${#prompt} -ge $max_len ]; then
        echo "${prompt:0:$max_len}..."
    else
        echo "$prompt"
    fi
}

JSONL_FILE=$(get_jsonl_file)

# Extract FIRST user message (the initiating intent)
# Filter for string content only (skip tool_result arrays)
INITIAL_PROMPT=""
if [ -n "$JSONL_FILE" ]; then
    INITIAL_PROMPT=$(grep '"type":"user"' "$JSONL_FILE" 2>/dev/null | \
        jq -r 'select(.message.content | type == "string") | .message.content' 2>/dev/null | \
        head -1)
    INITIAL_PROMPT=$(truncate_prompt "$INITIAL_PROMPT" 300)
fi

# Extract LAST user message (current state)
# Filter for string content only (skip tool_result arrays)
LAST_PROMPT=""
if [ -n "$JSONL_FILE" ]; then
    LAST_PROMPT=$(tail -r "$JSONL_FILE" 2>/dev/null | \
        grep '"type":"user"' | \
        jq -r 'select(.message.content | type == "string") | .message.content' 2>/dev/null | \
        head -1)
    LAST_PROMPT=$(truncate_prompt "$LAST_PROMPT" 200)
fi

# Extract LAST assistant message (agent's response)
LAST_RESPONSE=""
if [ -n "$JSONL_FILE" ]; then
    LAST_RESPONSE=$(tail -r "$JSONL_FILE" 2>/dev/null | \
        grep '"type":"assistant"' | \
        jq -r 'select(.message.content | type == "string") | .message.content' 2>/dev/null | \
        head -1)
    LAST_RESPONSE=$(truncate_prompt "$LAST_RESPONSE" 300)
fi

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
        --arg initial "$INITIAL_PROMPT" \
        --arg last "$LAST_PROMPT" \
        --arg response "$LAST_RESPONSE" \
        '{
            agent_id: $agent_id,
            agent_name: $agent_name,
            current_task: $task,
            last_tool: $tool,
            status: "active",
            initial_prompt: (if $initial == "" then null else $initial end),
            last_prompt: (if $last == "" then null else $last end),
            last_response: (if $response == "" then null else $response end)
        }')" > /dev/null 2>&1 &

exit 0
