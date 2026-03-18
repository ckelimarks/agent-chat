# 👁 Eye Canvas

Live visual output panel for agent-chat. Agents can draw diagrams, mockups, charts, and any self-contained HTML visualization to a split-screen canvas visible in the UI.

## Features

- **Split-screen layout**: Canvas appears beside terminal when toggled
- **Live updates**: WebSocket broadcasts reload canvas in real-time
- **Self-contained HTML**: Use CDN libraries (no build step)
- **Any agent can draw**: POST to `/api/canvas` from any agent
- **Mobile responsive**: Stacks vertically on small screens

## Usage

### For Agents

Post self-contained HTML to the canvas API:

```bash
curl -X POST http://localhost:8890/api/canvas \
  -H "Content-Type: application/json" \
  -d '{"html":"<!DOCTYPE html><html>...</html>"}'
```

The canvas will automatically reload for all connected clients.

### For Users

1. Open agent-chat UI at `http://localhost:8890`
2. Click the eye icon (👁) in the terminal header
3. Canvas panel appears on the right half of screen
4. Any agent updates will live-reload the canvas

## Supported Visualizations

**Diagrams (Mermaid.js):**
```html
<!DOCTYPE html>
<html>
<head>
  <script src="https://cdn.jsdelivr.net/npm/mermaid/dist/mermaid.min.js"></script>
</head>
<body>
  <div class="mermaid">
    graph TD; A-->B; B-->C
  </div>
  <script>mermaid.initialize({startOnLoad:true});</script>
</body>
</html>
```

**Charts (Chart.js):**
```html
<!DOCTYPE html>
<html>
<head>
  <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
</head>
<body>
  <canvas id="chart"></canvas>
  <script>
    new Chart(document.getElementById('chart'), {
      type: 'bar',
      data: { labels: ['A','B','C'], datasets: [{data: [1,2,3]}] }
    });
  </script>
</body>
</html>
```

**Data Visualization (D3.js):**
```html
<!DOCTYPE html>
<html>
<head>
  <script src="https://d3js.org/d3.v7.min.js"></script>
</head>
<body>
  <svg id="viz"></svg>
  <script>
    // Your D3 code here
  </script>
</body>
</html>
```

**3D Graphics (Three.js):**
```html
<!DOCTYPE html>
<html>
<head>
  <script src="https://cdn.jsdelivr.net/npm/three@0.160.0/build/three.min.js"></script>
</head>
<body>
  <script>
    // Your Three.js scene here
  </script>
</body>
</html>
```

**Presentations (Reveal.js):**
```html
<!DOCTYPE html>
<html>
<head>
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/reveal.js/dist/reveal.css">
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/reveal.js/dist/theme/black.css">
</head>
<body>
  <div class="reveal">
    <div class="slides">
      <section>Slide 1</section>
      <section>Slide 2</section>
    </div>
  </div>
  <script src="https://cdn.jsdelivr.net/npm/reveal.js/dist/reveal.js"></script>
  <script>Reveal.initialize();</script>
</body>
</html>
```

## Architecture

```
┌─────────────┐
│ Agent       │
│ (any agent) │
└──────┬──────┘
       │ POST /api/canvas
       ↓
┌─────────────────────────────┐
│ bridge.py                   │
│ • GET /api/canvas           │
│ • POST /api/canvas          │
│ • Write data/canvas.html    │
│ • Touch canvas.signal       │
└──────┬──────────────────────┘
       │
       ↓
┌─────────────────────────────┐
│ ws_server.py                │
│ • Watch canvas.signal       │
│ • Broadcast canvas_update   │
│ • WebSocket: ws://:8891/canvas │
└──────┬──────────────────────┘
       │
       ↓
┌─────────────────────────────┐
│ Browser Clients             │
│ • Receive canvas_update     │
│ • Reload iframe srcdoc      │
│ • Display in split-screen   │
└─────────────────────────────┘
```

## Testing

Run the included test script:

```bash
cd agent-chat
./test-canvas.sh
```

This will:
1. POST a Mermaid flowchart diagram
2. Wait 3 seconds
3. POST a Chart.js bar chart (tests live update)

Open the UI and toggle canvas to see the results.

## Design Decisions

1. **Signal file pattern**: Bridge writes `canvas.signal` to trigger updates instead of direct WebSocket coupling
2. **iframe srcdoc**: Avoids CORS issues with file:// URLs
3. **Split-screen layout**: Better than modal/overlay for workspace visibility
4. **CDN-only**: No build step, agents can use any library via CDN
5. **Gitignored data**: `data/canvas.html` is runtime-generated, not committed

## Mobile Support

On screens < 768px:
- Canvas and terminal stack vertically (1fr / 1fr grid)
- Canvas panel has top border instead of left border
- Toggle button remains accessible in header

## Future Enhancements

### Next Iteration: Infinite Canvas

**Features:**
- [ ] Hand grabber tool — pan/drag to navigate infinite canvas space
- [ ] Agent scratch pads — each agent has their own isolated region
- [ ] Quick navigation — jump-to buttons to center on each agent's area
- [ ] Zoom controls (scroll wheel)

**Recommended Architecture: Iframe Grid on Transformable Canvas**

```
┌─────────────────────────────────────────────────────────┐
│  Infinite Canvas (CSS transform for pan/zoom)           │
│                                                         │
│   ┌──────────────┐      ┌──────────────┐               │
│   │ Agent A      │      │ Agent B      │               │
│   │ (iframe)     │      │ (iframe)     │               │
│   │ blue bg,     │      │ chart.js     │               │
│   │ whatever     │      │ viz          │               │
│   └──────────────┘      └──────────────┘               │
│                                                         │
│        ┌──────────────┐                                │
│        │ Agent C      │                                │
│        │ (iframe)     │                                │
│        │ mermaid      │                                │
│        │ diagram      │                                │
│        └──────────────┘                                │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

**Key Design Decisions:**

1. **Iframes for isolation** — Each agent gets their own iframe (fixed size, e.g., 800x600). Full HTML document isolation so one agent's styles don't bleed into another's.

2. **Absolute positioning on infinite plane** — Each iframe positioned at `(x, y)` coordinates. New agents auto-assigned positions (grid layout or spiral).

3. **CSS transforms for navigation:**
   ```css
   .infinite-canvas {
     transform: translate(var(--pan-x), var(--pan-y)) scale(var(--zoom));
     transform-origin: 0 0;
   }
   ```
   - Hand tool: drag updates `--pan-x`, `--pan-y`
   - Zoom: scroll wheel updates `--zoom`
   - Jump-to: animate transform to center on agent's region

4. **Data model:**
   ```json
   {
     "agents": {
       "frontend-dev": { "x": 0, "y": 0, "width": 800, "height": 600, "html": "..." },
       "backend-dev": { "x": 850, "y": 0, "width": 800, "height": 600, "html": "..." },
       "designer": { "x": 0, "y": 650, "width": 800, "height": 600, "html": "..." }
     },
     "viewport": { "panX": 0, "panY": 0, "zoom": 1 }
   }
   ```

5. **Navigation sidebar:**
   ```
   [🎯 Frontend Dev]  ← click to center
   [🎯 Backend Dev]
   [🎯 Designer]
   ```

**Library:** Use `@panzoom/panzoom` for lightweight pan/zoom handling.

### Backlog
- [ ] Canvas history/undo
- [ ] Canvas export (PNG/SVG/PDF)
- [ ] Collaborative canvas (multiple agents drawing simultaneously)
- [ ] Canvas templates library
