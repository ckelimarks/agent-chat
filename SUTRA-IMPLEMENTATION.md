# Sutra Implementation Plan

Progressive rollout of sutra-based compression architecture for agent-chat orchestration.

## Context

Based on Vedic sutra pattern: compress knowledge into seeds, unfold on demand. Three-layer structure:
- **Sutra** (1 sentence): What happened
- **Vritti** (1 paragraph): Why it matters
- **Bhashya** (full detail): Everything

Goal: Protect orchestrator context window, enable on-demand zoom, prevent "agent forgets infrastructure" issues.

See `Sutra - Handoff.md` for full architectural background.

---

## Phase 1: Add Sutra Layer (Non-Breaking)

**Status**: Planned
**Goal**: Validate sutra generation quality without changing existing system
**Timeline**: 1 week test period

### What to Build

1. **Sutra Generator Function**
   - Input: Agent's full output (existing report data)
   - Output: One-sentence sutra following template
   - Template: `[PAST_TENSE_VERB] + [SUBJECT] + [OUTCOME] + [SIGNAL_WORD]`
   - Must pass 3 gates:
     - **alpākṣaram**: One sentence max
     - **asandigdham**: One clear meaning
     - **sāravat**: Only what matters for next decision

2. **Sutra Index Storage**
   - File: `data/sutra-index.jsonl` (append-only log)
   - Schema:
     ```json
     {
       "pull_id": "sutra_{agent_id}_{timestamp}",
       "timestamp": "2025-03-06T14:30:22Z",
       "agent_id": "mission-match-builder",
       "sutra": "Profile showcase rebuilt. Gap identified: explainability.",
       "vritti": "[existing summary text]",
       "bhashya_path": null,  // Phase 2
       "triggers": ["rebuilt", "gap"]
     }
     ```

3. **Report Hook Integration**
   - Keep existing report format unchanged
   - Add sutra generation as extra step
   - Write to both: existing reports + sutra index
   - No changes to orchestrator display yet

### Implementation

**File**: `server/sutra_generator.py`

```python
import re
from datetime import datetime

# Trigger words that indicate vritti pull might be needed
TRIGGER_WORDS = [
    'deployed', 'blocked', 'failed', 'anomaly',
    'gap', 'awaiting', 'decision-required', 'error'
]

def extract_sutra(report_data: dict) -> dict:
    """
    Generate sutra from existing report data.

    Returns:
        {
            "text": "One sentence sutra",
            "triggers": ["word1", "word2"],
            "confidence": 0.85
        }
    """
    # Take first sentence of summary
    summary = report_data.get('summary', '')
    sentences = summary.split('.')
    first_sentence = sentences[0].strip() + '.'

    # Extract trigger words
    triggers = [w for w in TRIGGER_WORDS if w in first_sentence.lower()]

    # Validate gates
    if not validate_sutra(first_sentence):
        # Fallback: compress more aggressively
        first_sentence = compress_to_sutra(summary)

    return {
        "text": first_sentence,
        "triggers": triggers,
        "confidence": calculate_confidence(first_sentence)
    }

def validate_sutra(text: str) -> bool:
    """Check if text passes the 3 gates."""
    # Gate 1: One sentence (alpākṣaram)
    if text.count('.') > 1:
        return False

    # Gate 2: Clear meaning (asandigdham) - basic heuristic
    vague_words = ['stuff', 'things', 'various', 'some']
    if any(word in text.lower() for word in vague_words):
        return False

    # Gate 3: Essential only (sāravat) - length heuristic
    if len(text.split()) > 15:  # Max 15 words
        return False

    return True

def write_sutra_index(agent_id: str, report_data: dict):
    """Append sutra to index (non-breaking addition)."""
    sutra_data = extract_sutra(report_data)

    entry = {
        "pull_id": f"sutra_{agent_id}_{int(datetime.now().timestamp())}",
        "timestamp": datetime.now().isoformat(),
        "agent_id": agent_id,
        "sutra": sutra_data["text"],
        "vritti": report_data.get('summary', ''),
        "bhashya_path": None,
        "triggers": sutra_data["triggers"]
    }

    # Append to index
    with open('data/sutra-index.jsonl', 'a') as f:
        f.write(json.dumps(entry) + '\n')
```

**File**: `server/heartbeat.py` (modify existing)

```python
# Add to existing report generation
def add_report(agent_id, agent_name, report_type, title, summary, payload=None):
    # Existing code stays unchanged
    report = db.add_report(...)

    # NEW: Also write to sutra index
    from sutra_generator import write_sutra_index
    write_sutra_index(agent_id, {
        'summary': summary,
        'title': title,
        'type': report_type
    })

    return report
```

### Testing Checklist

- [ ] Create `data/sutra-index.jsonl`
- [ ] Run system for 1 week
- [ ] Generate at least 20 sutras from real agent activity
- [ ] Manual review: Do sutras pass 3 gates?
- [ ] Manual review: Can you understand agent state from sutras alone?
- [ ] Manual review: When do you need vritti? (track mentally)

### Success Criteria

After 1 week:
- 80%+ of sutras are readable and actionable
- You can answer "what's the state?" by reading sutras
- You notice patterns in when you want more detail (validates pull triggers)

**If success criteria met** → Proceed to Phase 2
**If not met** → Pattern doesn't work for this domain, abort

---

## Phase 2: Add Pull-ID Storage (Planned)

**Status**: Not started
**Dependencies**: Phase 1 success

Store full bhashya with retrieval capability. Details TBD after Phase 1 validation.

---

## Phase 3: Orchestrator Pull Logic (Planned)

**Status**: Not started
**Dependencies**: Phase 2 complete

Enable orchestrator to zoom into vritti/bhashya on demand. Details TBD.

---

## Metrics Dashboard (Future)

Track after all phases complete:
- Sutras generated
- Vritti pulls (target: 20-30%)
- Bhashya pulls (target: <5%)
- Top trigger words
- Retrieval speed
- Infrastructure lookup efficiency

---

## Rollback Plan

Phase 1 is non-breaking. To rollback:
1. Stop writing to `sutra-index.jsonl`
2. Delete file
3. System continues with existing reports unchanged

---

## Reference

- Full architecture: `Sutra - Handoff.md`
- Canvas architecture: `CANVAS.md`
- Current system: `CLAUDE.md`
