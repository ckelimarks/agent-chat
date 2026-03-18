# Agent Notifications Spec

## Problem

Users run multiple agents simultaneously. They need to know when:
1. **Needs attention** - Agent is waiting for approval (permission prompt)
2. **Done** - Agent finished its task and is idle

Currently: Terminal bell plays but gets missed. No visual indicator for completion.

## Design Goals

- Zero-config: Works out of the box
- Instant: Notification appears immediately
- Glanceable: Quick scan to see agent states
- Actionable: One click to jump to agent

---

## Notification Triggers

### 1. Attention (orange) - Terminal Bell

Claude Code plays `\x07` (bell character) when it needs user approval.

```python
# ws_server.py
def on_output(self, data: str):
    if '\x07' in data:
        db.set_notification(self.agent_id, 'attention')
```

### 2. Done (green) - Idle After Work

Agent completed task, now waiting for next instruction.

Detection: No output for 5 seconds after agent was working.

```python
# ws_server.py
self.last_output_time = time.time()
self.was_busy = False

def on_output(self, data: str):
    self.last_output_time = time.time()
    self.was_busy = True

# Check every 2 seconds
def check_idle():
    idle_seconds = time.time() - self.last_output_time
    if idle_seconds > 5 and self.was_busy:
        db.set_notification(self.agent_id, 'done')
        self.was_busy = False
```

### Clear Conditions

| Event | Clears notification |
|-------|---------------------|
| User sends input | Yes |
| User clicks/selects agent | Yes |
| New output starts | Yes (resets idle timer) |

---

## Data Model

### agents table

```sql
ALTER TABLE agents ADD COLUMN notification TEXT DEFAULT NULL;
-- Values: NULL, 'attention', 'done'
```

### db.py

```python
def set_notification(agent_id: int, state: str):
    """Set notification state: 'attention', 'done', or None to clear"""
    execute("UPDATE agents SET notification = ? WHERE id = ?", (state, agent_id))

def clear_notification(agent_id: int):
    set_notification(agent_id, None)
```

---

## UI

### Agent List Badges

```
┌─────────────────────────────┐
│ 🤖 Worker 1            🟢   │  ← green = done
│ 🔧 Worker 2            🟠   │  ← orange pulsing = attention
│ 📊 Analyst                  │  ← no badge = working/idle
└─────────────────────────────┘
```

```css
.badge-done {
  background: #22c55e;
}

.badge-attention {
  background: #f97316;
  animation: pulse 1.5s infinite;
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}
```

### Tab Title

```javascript
const attention = agents.filter(a => a.notification === 'attention').length;
const done = agents.filter(a => a.notification === 'done').length;

if (attention > 0) {
  document.title = `(!) Agent Chat`;  // Urgent
} else if (done > 0) {
  document.title = `(${done}) Agent Chat`;  // Count of done
} else {
  document.title = 'Agent Chat';
}
```

---

## Implementation

### Files to modify

| File | Changes |
|------|---------|
| `server/schema.sql` | Add `notification` column |
| `server/db.py` | Add `set_notification()`, `clear_notification()` |
| `server/ws_server.py` | Detect bell char, track idle, call db functions |
| `server/bridge.py` | Clear notification when message sent |
| `web/index.html` | Render badges, update tab title |

### Steps

1. Add `notification` column to schema
2. Add db helper functions
3. Detect `\x07` in ws_server output → set 'attention'
4. Track idle time in ws_server → set 'done' after 5s
5. Clear notification on user input (bridge.py)
6. Render badges in frontend
7. Update document.title based on counts

---

## Edge Cases

| Scenario | Behavior |
|----------|----------|
| Both done + attention possible | attention wins (higher priority) |
| Rapid bell characters | Single notification, don't stack |
| Agent goes offline | Keep notification visible |
| Page refresh | Persists via database |

---

## Testing

- [ ] Orange badge appears on permission prompt
- [ ] Green badge appears after agent goes idle
- [ ] Badge clears when user sends message
- [ ] Badge clears when user clicks agent
- [ ] Tab title shows (!) for attention
- [ ] Tab title shows count for done
- [ ] State persists across refresh
