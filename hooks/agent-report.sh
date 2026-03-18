#!/bin/bash
# PostToolUse hook for detecting REPORT JSON in agent output
# Sends reports to the Agent Chat bridge server

# Read hook input from stdin
INPUT=$(cat)

# Extract tool result from the hook input
TOOL_RESULT=$(echo "$INPUT" | jq -r '.tool_result // empty' 2>/dev/null)

# Check if the result contains a REPORT block
if echo "$TOOL_RESULT" | grep -q '"type":\s*"REPORT"'; then
    # Extract the REPORT JSON
    REPORT=$(echo "$TOOL_RESULT" | grep -oP '\{[^{}]*"type"\s*:\s*"REPORT"[^{}]*\}' | head -1)

    if [ -n "$REPORT" ]; then
        # Get agent info from environment
        AGENT_ID="${CLAUDE_AGENT_ID:-unknown}"
        AGENT_NAME="${CLAUDE_AGENT_NAME:-Unknown Agent}"

        # Build the payload
        PAYLOAD=$(jq -n \
            --arg agent_id "$AGENT_ID" \
            --arg agent_name "$AGENT_NAME" \
            --argjson report "$REPORT" \
            '{
                agent_id: $agent_id,
                agent_name: $agent_name,
                type: $report.report_type,
                title: $report.title,
                summary: $report.summary,
                payload: $report.payload
            }')

        # Send to bridge server
        curl -s -X POST "http://localhost:8890/api/reports" \
            -H "Content-Type: application/json" \
            -d "$PAYLOAD" > /dev/null 2>&1 &
    fi
fi

# Always exit successfully so we don't block the agent
exit 0
