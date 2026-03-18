#!/bin/bash
# Install agent-chat hooks in all worker project directories
# This enables real-time heartbeat updates from workers to orchestrator

set -e

AGENT_CHAT_HOOKS="$(cd "$(dirname "$0")/hooks" && pwd)"

echo "📡 Installing agent-chat hooks from: $AGENT_CHAT_HOOKS"
echo ""

# List of worker project directories (from database)
WORKERS=(
  "$HOME/Downloads/personal-os-main/Projects/LoveNotes"
  "$HOME/Downloads/personal-os-main/Projects/job-search"
  "$HOME/Downloads/personal-os-main/Projects/prototypes"
  "$HOME/Downloads/personal-os-main/Projects/content"
  "$HOME/Downloads/personal-os-main/Projects/hackathon"
  "$HOME/Downloads/personal-os-main/Projects/teaching/remington"
)

# Make hooks executable
chmod +x "$AGENT_CHAT_HOOKS/auto-heartbeat.sh"
chmod +x "$AGENT_CHAT_HOOKS/agent-report.sh"

for project in "${WORKERS[@]}"; do
  if [ ! -d "$project" ]; then
    echo "⚠️  Project not found: $project (skipping)"
    continue
  fi

  echo "Installing hooks in: $(basename "$project")"

  # Create .claude/hooks directory
  mkdir -p "$project/.claude/hooks"

  # Symlink the hooks
  # PostToolUse hook for automatic heartbeat updates
  ln -sf "$AGENT_CHAT_HOOKS/auto-heartbeat.sh" "$project/.claude/hooks/PostToolUse"

  # Optional: Add agent-report hook if needed
  # ln -sf "$AGENT_CHAT_HOOKS/agent-report.sh" "$project/.claude/hooks/PostToolUse.agent-report"

  echo "  ✓ PostToolUse hook installed"
done

echo ""
echo "✅ All worker hooks installed"
echo ""
echo "Workers will now send heartbeat updates on every tool use."
echo ""
echo "Test with:"
echo "  1. Send a message to a worker agent (e.g., LoveNotes)"
echo "  2. Check: cat ~/Downloads/personal-os-main/Projects/prototypes/agent-chat/data/orchestrator/heartbeats.json"
echo "  3. You should see real-time task updates"
echo ""
echo "To verify hook installation:"
echo "  cat ~/Downloads/personal-os-main/Projects/LoveNotes/.claude/hooks/PostToolUse"
