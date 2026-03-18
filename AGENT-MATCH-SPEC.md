# Agent Match: AI-to-AI Collaboration Protocol

> Handoff for hackathon agent - spec out and prototype

## The Insight

Mission Match enables two-stage handshake between humans: both parties consent before connection happens.

**Agent Match** extends this to AI companions. After two humans agree to collaborate, their agents get a **walled garden** - a private space to build shared context, find patterns across both people's work, and help each collaborator see what they couldn't alone.

## The Pattern

```
Human A                          Human B
   │                                │
   ▼                                ▼
┌─────────┐    Handshake      ┌─────────┐
│ Agent A │◄─────────────────►│ Agent B │
└─────────┘                   └─────────┘
      │                             │
      └──────────┬──────────────────┘
                 ▼
         ┌─────────────┐
         │ Walled Garden│
         │  (Slack/etc) │
         └─────────────┘
                 │
                 ▼
         Shared context,
         cross-pollination,
         emergent insights
```

## Current Prototype: Sutra-Symbolic

**What's working:**
- Two brothers, each with their own OS + AI agent
- Private Slack channel (#sutra-symbolic)
- `slack_dialogue.py` - background process that:
  - Polls channel every 60s for new messages
  - Responds to any message from the other agent
  - Posts hourly "pulse" to keep dialogue alive
  - Tags the other agent to trigger their response

**What it demonstrates:**
- Agents can have persistent, asynchronous dialogue
- Context from two different lives cross-pollinates
- The walled garden creates a safe space for exploration
- Low-friction: just runs in background

## Evolution: Agent Match Protocol

### Phase 1: Handshake
Before agents can connect:
1. Human A invites Human B (or vice versa)
2. Both humans explicitly consent
3. System creates walled garden (channel, thread, or dedicated space)
4. Both agents get injected with context about:
   - Who they're talking to
   - What the collaboration is about
   - Boundaries/scope

### Phase 2: Walled Garden Setup
- Private channel/space created automatically
- Both agents get system prompts with:
  - Their human's context (goals, projects, style)
  - The collaboration purpose
  - Guidance on being helpful vs. noisy

### Phase 3: Ongoing Dialogue
- Agents poll for messages
- Respond to each other asynchronously
- Can be configured for:
  - **Active**: Respond to every message
  - **Pulse**: Check in periodically (hourly/daily)
  - **On-demand**: Only when explicitly invoked

### Phase 4: Value Back to Humans
- Agents surface insights to their humans
- "Symbolic mentioned X which connects to your Y"
- Summaries of dialogue available in each person's OS
- Cross-pollination becomes visible

## Use Cases

### Co-founders
- Agents share context on what each founder is working on
- Surface conflicts ("you're both solving auth differently")
- Find synergies ("their API design would help your feature")

### Research Collaborators
- Agents exchange notes, find patterns
- Build shared bibliography/context
- Identify gaps neither human noticed

### Couples (LoveNotes evolution)
- Each partner has their own agent
- Agents notice patterns ("they've mentioned being tired 3x")
- Generate prompts that are informed by both perspectives

### Teams
- Multiple agents in shared garden
- Orchestrator agent synthesizes across all
- Reduces sync meeting overhead

## Technical Requirements

### For Agent Match MVP:
1. **Invitation system** - Human A invites Human B
2. **Consent flow** - Both must accept
3. **Garden creation** - Auto-create Slack channel or equivalent
4. **Agent injection** - Add collaboration context to both agents
5. **Polling loop** - Each agent monitors and responds
6. **Tagging** - Ensure responses trigger the other agent

### Infrastructure we have:
- `slack_dialogue.py` - polling + response loop
- `slack_agent.py` - agent-chat integration
- Slack MCP - API access
- Claude CLI - response generation

### What's needed:
- Invitation/consent UI or flow
- Multi-garden support (not just one hardcoded channel)
- System prompt injection per collaboration
- Dashboard to see active collaborations

## Open Questions

1. **Threading**: Should each topic be a thread, or flat channel?
2. **Frequency**: How often should agents talk? User-configurable?
3. **Synthesis**: How do insights flow back to humans?
4. **Privacy**: What context is shared vs. kept private?
5. **Scaling**: What happens with 3+ agents in a garden?

## Next Steps for Hackathon Agent

1. **Generalize `slack_dialogue.py`** - Support multiple channels/gardens
2. **Build invitation flow** - Even if manual/CLI at first
3. **Create system prompt template** - For collaboration context
4. **Test with 2-3 use cases** - Co-founders, collaborators, etc.
5. **Design insight surfacing** - How do agents report back?

---

*This is Mission Match for minds - except the minds are AI companions, and the match creates ongoing collaboration, not just a single connection.*
