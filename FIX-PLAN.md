# Agent Chat: Complete Fix Plan

## Problems Identified

1. ❌ **Workers have no heartbeat hooks** → Sutra sees stale data
2. ❌ **Cron race condition** → Submits user's typing when injecting check-in
3. ❌ **Only 1/5/10 min intervals** → Need 30min and 1hr options
4. ❌ **Sutra prompt too constrained** → Can't execute morning/end-day skills

## Solutions

### Fix 1: Install Hooks in Worker Projects

**Problem:** Hooks in `agent-chat/hooks/` but not in worker `.claude/hooks/` directories.

**Solution:** Symlink hooks to all worker project directories.

```bash
#!/bin/bash
# install-worker-hooks.sh

AGENT_CHAT_HOOKS="$HOME/Downloads/personal-os-main/Projects/prototypes/agent-chat/hooks"

# List of worker project directories
WORKERS=(
  "$HOME/Downloads/personal-os-main/Projects/LoveNotes"
  "$HOME/Downloads/personal-os-main/Projects/job-search"
  "$HOME/Downloads/personal-os-main/Projects/prototypes"
  "$HOME/Downloads/personal-os-main/Projects/content"
  "$HOME/Downloads/personal-os-main/Projects/hackathon"
  "$HOME/Downloads/personal-os-main/Projects/teaching/remington"
)

for project in "${WORKERS[@]}"; do
  echo "Installing hooks in $project"
  mkdir -p "$project/.claude/hooks"

  # Symlink the hooks
  ln -sf "$AGENT_CHAT_HOOKS/auto-heartbeat.sh" "$project/.claude/hooks/PostToolUse"
  ln -sf "$AGENT_CHAT_HOOKS/agent-report.sh" "$project/.claude/hooks/PostToolUse.agent-report"

  # Make sure they're executable
  chmod +x "$AGENT_CHAT_HOOKS/auto-heartbeat.sh"
  chmod +x "$AGENT_CHAT_HOOKS/agent-report.sh"

  echo "✓ Hooks installed in $project"
done

echo ""
echo "✅ All worker hooks installed"
echo ""
echo "Test with: cat ~/Downloads/personal-os-main/Projects/LoveNotes/.claude/hooks/PostToolUse"
```

**Alternative:** Install globally in `~/.claude/hooks/` so ALL projects get them:
```bash
ln -sf "$AGENT_CHAT_HOOKS/auto-heartbeat.sh" ~/.claude/hooks/PostToolUse
```

### Fix 2: Fix Cron Race Condition

**File:** `agent-chat/server/ws_server.py` lines 437-447

**Current (broken):**
```python
check_in_prompt = "[Check-in] Review worker status and share observations."
ok = await inject_as_keystrokes(orchestrator_id, check_in_prompt, submit=True)
```

**Fixed:**
```python
# Clear input buffer first (Ctrl+U in bash/zsh)
await inject_as_keystrokes(orchestrator_id, '\x15')  # Ctrl+U
await asyncio.sleep(0.1)  # Let terminal process

check_in_prompt = "[Check-in] Review worker status and share observations."
ok = await inject_as_keystrokes(orchestrator_id, check_in_prompt, submit=True)
```

**Better Alternative:** Don't auto-submit. Let user hit Enter when ready:
```python
# Option: Inject prompt but DON'T auto-submit
check_in_prompt = "[Check-in] Review worker status and share observations."
ok = await inject_as_keystrokes(orchestrator_id, check_in_prompt, submit=False)
# User can edit or just hit Enter
```

### Fix 3: Add 30min and 1hr Cron Intervals

**File:** `agent-chat/web/index.html` (find the settings UI)

Add options for 30 and 60 minute intervals:

```javascript
// In the settings dropdown
const intervalOptions = [
  { value: 60, label: '1 minute' },
  { value: 300, label: '5 minutes' },
  { value: 600, label: '10 minutes' },
  { value: 1800, label: '30 minutes' },   // NEW
  { value: 3600, label: '1 hour' }        // NEW
];
```

### Fix 4: Update Sutra Prompt

**File:** `agent-chat/server/heartbeat.py` line 208-250

Replace `get_orchestrator_system_prompt()` with the dual-mode version from `PROPOSED-SUTRA-PROMPT.md`.

**Key changes:**
- Remove "3-4 sentences" constraint from default mode
- Make "primary assistant" the default role
- Observer mode triggered by "status" / "check-in" keywords
- Emphasize READING the actual data files

## Implementation Order

1. **Install worker hooks** (biggest impact) → Workers start sending heartbeats immediately
2. **Fix cron race condition** → Check-ins don't mess with user typing
3. **Update Sutra prompt** → Can execute skills + observe
4. **Add 30/60min intervals** → Nice to have

## Testing

After fixes:

1. **Test worker heartbeats:**
   ```bash
   # In LoveNotes agent terminal
   # Run any command (Read, Write, etc.)
   # Check heartbeat file
   cat agent-chat/data/orchestrator/heartbeats.json
   # Should see LoveNotes agent with current task
   ```

2. **Test cron injection:**
   - Enable cron in settings
   - Start typing in Sutra terminal
   - Wait for cron to fire
   - Should clear your typing and inject check-in prompt (or just inject without submitting)

3. **Test Sutra dual-mode:**
   ```
   # In Sutra terminal:

   # Test assistant mode (should be verbose)
   "good morning"

   # Test observer mode (should be concise, strategic)
   "status"
   ```

4. **Test 30min/1hr intervals:**
   - Set to 30 minutes in UI
   - Wait for check-in to fire
   - Verify timing in logs

## Additional Improvements (Future)

### Proactive Observations

Instead of just responding to check-ins, Sutra could MESSAGE Christopher when patterns emerge:

```python
# In orchestrator_cron():
# After reading worker reports...

if blocking_issue_detected():
    msg = "FYI: Two agents hit the same auth blocker - might be a system issue"
    db.add_message(orchestrator_thread_id, 'assistant', msg)
    # This appears in Sutra's chat without interrupting Christopher

if cross_project_opportunity():
    msg = "Interesting: JobSearch agent learned X that LoveNotes needs for Y"
    db.add_message(orchestrator_thread_id, 'assistant', msg)
```

This makes the observer truly "omnipresent" — it notices and speaks up, not just when asked.

### Worker Report Quality

Current worker reports are hit or miss. Some workers write good status, others don't.

**Improve the worker prompt:**
```markdown
## Multi-Agent System

You're part of a multi-agent system. An orchestrator monitors all workers.

**When you complete a meaningful milestone:**
Write to your status file:
```bash
cat > ~/Downloads/personal-os-main/Projects/prototypes/agent-chat/data/orchestrator/reports/$AGENT_CHAT_NAME.json << 'EOF'
{
  "summary": "Specific accomplishment in one sentence",
  "decisions": ["Key choices made"],
  "blockers": ["Anything stuck"],
  "status": "done|blocked|working"
}
EOF
```

**Examples of meaningful milestones:**
- Feature completed
- Decision made that affects other projects
- Blocker encountered
- Integration point discovered

**Don't report:**
- Routine file reads
- Small edits
- Research (unless findings are significant)
```

### Heartbeat Visualization

Add to the web UI:
- Real-time heartbeat display
- "Last seen" for each worker
- Current task tooltip on hover
- Idle vs active indicators

## Files to Modify

- [ ] `agent-chat/hooks/install-worker-hooks.sh` (new file)
- [ ] `agent-chat/server/ws_server.py` (lines 437-447 - fix cron)
- [ ] `agent-chat/server/heartbeat.py` (line 208-250 - new Sutra prompt)
- [ ] `agent-chat/web/index.html` (add 30min/1hr options)

## Quick Start

```bash
cd ~/Downloads/personal-os-main/Projects/prototypes/agent-chat

# 1. Install hooks
bash install-worker-hooks.sh

# 2. Apply code fixes
# Edit ws_server.py, heartbeat.py, web/index.html as described above

# 3. Restart servers
./start.sh

# 4. Enable cron in UI
# Open http://localhost:8890
# Settings → Enable cron → Set interval

# 5. Test
# Send message to LoveNotes worker
# Check heartbeats file
# Wait for Sutra check-in
```

---

**Bottom line:** Workers can't report status because hooks aren't installed. Fix that first, then everything else falls into place.
