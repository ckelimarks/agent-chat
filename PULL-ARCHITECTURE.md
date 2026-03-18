# Pull Architecture Implementation

## What We Built

Added **zoom capability** to Sutra without changing its synthesis quality. Sutra already writes good vritti-level summaries — we just added the infrastructure to pull deeper on demand.

## Changes Made

### 1. Worker Report Format (heartbeat.py)

Workers now write structured reports with three layers:

```json
{
  "report_id": "hackathon-2026-03-04-0951",
  "summary": "Mission Match at 95%. Human API visibility missing. 2hr fix.",
  "context": "Demo functional but narrative isn't tight. Blocker is storytelling, not technical. Database migration in backlog.",
  "details": {
    "decisions": ["Recommend Option A over full roadmap"],
    "blockers": [],
    "files": ["TODO-PROFILE-SHOWCASE.md"],
    "next_steps": ["Human API visibility", "Radar chart sizing"]
  },
  "status": "working"
}
```

**Field meanings:**
- **summary**: One sentence. The irreducible outcome. (Zoom level 0)
- **context**: One paragraph. Why it matters, what changed. (Zoom level 1)
- **details**: Full resolution. Everything needed to zoom in. (Zoom level 2)

### 2. Synthesis Logging (heartbeat.py)

Added functions to log what Sutra reads:

```python
def log_synthesis(observations: list) -> str:
    """Log a synthesis with pull references."""

def pull_detail(pull_id: str) -> Optional[Dict]:
    """Pull detailed context for a specific observation."""
```

**Synthesis log format:**
```json
{
  "synthesis_id": "sutra-2026-03-04-0915",
  "timestamp": "2026-03-04T09:15:00",
  "observations": [
    {
      "text": "Mission Match at 95% — narrative gap",
      "pull_id": "hackathon-2026-03-04-0951",
      "source": "reports/hackathon.json",
      "zoom_level": "summary"
    }
  ]
}
```

### 3. Sutra Prompt Updates

Added progressive disclosure guidance:

```markdown
**Progressive disclosure (zoom capability):**
- Worker reports have three layers: summary, context, details
- Read summaries first (one sentence each) — keeps context clean
- Pull context when pattern needs more resolution
- Pull details only when decision requires full data

**When Christopher asks "tell me more about X":**
Look for the observation in your recent synthesis, read the deeper
layer from that specific report. Don't re-synthesize — just zoom.
```

### 4. UI Enhancement

Added 30min and 1hr cron intervals to settings dropdown.

## How It Works

### Current Behavior (Unchanged)
1. Christopher asks Sutra: "status"
2. Sutra reads worker summaries
3. Sutra synthesizes: "Mission Match at 95% — narrative gap"
4. Output looks identical to before

### New Capability (Zoom)
1. Christopher asks: "Tell me more about the narrative gap"
2. Sutra searches synthesis log for "narrative gap"
3. Finds `pull_id: "hackathon-2026-03-04-0951"`
4. Reads `reports/hackathon.json | jq '.context'` or `.details`
5. Responds with deeper context **without re-running everything**

## File Structure

```
agent-chat/data/orchestrator/
├── heartbeats.json           # Real-time worker activity
├── synthesis-log.json        # Sutra's observation history (NEW)
├── reports/
│   ├── hackathon.json        # summary + context + details (UPDATED)
│   ├── LoveNotes.json
│   └── ...
└── sessions/
    └── *-2026-03-04.md       # Tool usage logs
```

## Testing

### Test 1: Worker Reports New Format
Workers should start writing reports with summary/context/details:

```bash
# Have a worker complete a milestone and write a report
# Check format:
cat agent-chat/data/orchestrator/reports/hackathon.json | jq .
```

Should show `summary`, `context`, `details` fields.

### Test 2: Sutra Read Summaries First
Ask Sutra: "status"

Should read summaries first (keeping context clean), then synthesize.

### Test 3: Pull Details on Demand
1. Sutra mentions something (e.g., "Mission Match narrative gap")
2. Ask: "Tell me more about the narrative gap"
3. Sutra should pull the context/details for that specific observation

## What Changed vs What Didn't

### ✅ Changed
- Worker REPORT format (now has 3 layers)
- Synthesis logging (tracks what Sutra reads)
- Sutra prompt (mentions zoom capability)
- UI (30min/1hr cron options)

### ❌ Didn't Change
- Sutra's synthesis quality (still writes vritti-level summaries)
- Sutra's output format (looks identical to before)
- Heartbeat system (still real-time tool tracking)
- Current observer behavior (reads, synthesizes, speaks)

## Why This Matters

**Before:**
- Sutra reads everything, synthesizes well
- If you ask "what's the narrative gap?" → Sutra guesses from memory or re-reads everything

**After:**
- Sutra reads summaries, synthesizes well (same quality)
- If you ask "what's the narrative gap?" → Sutra pulls the exact bhashya that generated that observation
- Context stays clean (row of seeds, not a forest)
- Zoom is deliberate, not automatic

## Next Steps (Not Implemented Yet)

1. **Automatic synthesis logging** - Sutra doesn't log yet, needs to be wired up
2. **Pull command** - Sutra doesn't have a "pull details" function call yet
3. **Context ledger UI** - Could show which observations have deeper context available
4. **Pull trigger rules** - Automatic expansion based on keywords (anomaly, blocked, etc.)

## The Philosophy

From the Vedic transmission model:
- **Sutra** (सूत्र): The seed. One sentence that contains the tree.
- **Vritti** (वृत्ति): The unfolding. Context and implication.
- **Bhashya** (भाष्य): The commentary. Full resolution and detail.

We're not using those exact terms in the code (Claude's latent space has stronger weights for summary/context/details), but the architecture embodies the same principle:

**Compression without reduction. The seed contains the tree. Pull only what you need.**

---

**Status**: Infrastructure in place. Ready for workers to start using new format and Sutra to start logging syntheses.
