#!/bin/bash
# Test script for Eye Canvas

echo "🎨 Testing Eye Canvas..."

# Test 1: Draw Mermaid diagram
echo ""
echo "Test 1: Drawing Mermaid flowchart..."

MERMAID_HTML='<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <script src="https://cdn.jsdelivr.net/npm/mermaid/dist/mermaid.min.js"></script>
  <style>
    body {
      margin: 0;
      padding: 40px;
      background: #fafafa;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }
    h1 {
      font-size: 24px;
      color: #18181b;
      margin-bottom: 24px;
    }
  </style>
</head>
<body>
  <h1>Eye Canvas Test - Mermaid Diagram</h1>
  <div class="mermaid">
    graph TD
    A[User Request] -->|POST /api/canvas| B[Bridge Server]
    B -->|Write HTML| C[data/canvas.html]
    B -->|Touch signal| D[canvas.signal]
    E[WebSocket Server] -->|Watch signal| D
    E -->|Broadcast update| F[Browser Clients]
    F -->|Reload iframe| G[Canvas Visible]
  </div>
  <script>mermaid.initialize({startOnLoad:true,theme:"default"});</script>
</body>
</html>'

curl -X POST http://localhost:8890/api/canvas \
  -H "Content-Type: application/json" \
  -d "{\"html\":$(echo "$MERMAID_HTML" | jq -Rs .)}" \
  && echo "✅ Mermaid diagram sent" \
  || echo "❌ Failed to send diagram"

echo ""
echo "📊 Canvas should now display a flowchart in the UI"
echo "   1. Open http://localhost:8890 in your browser"
echo "   2. Click the eye icon 👁 in the terminal header"
echo "   3. Canvas panel should appear on the right with the diagram"
echo ""

# Test 2: Update with Chart.js
echo "Waiting 3 seconds before next test..."
sleep 3

echo ""
echo "Test 2: Drawing Chart.js bar chart..."

CHART_HTML='<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
  <style>
    body {
      margin: 0;
      padding: 40px;
      background: #fafafa;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }
    h1 {
      font-size: 24px;
      color: #18181b;
      margin-bottom: 24px;
    }
    canvas {
      max-width: 600px;
    }
  </style>
</head>
<body>
  <h1>Canvas Live Update Test - Chart.js</h1>
  <canvas id="myChart"></canvas>
  <script>
    const ctx = document.getElementById("myChart").getContext("2d");
    new Chart(ctx, {
      type: "bar",
      data: {
        labels: ["Bridge", "WebSocket", "Signal", "Broadcast", "Client"],
        datasets: [{
          label: "Canvas System Components",
          data: [12, 19, 8, 15, 10],
          backgroundColor: "rgba(168, 85, 247, 0.7)",
          borderColor: "rgba(168, 85, 247, 1)",
          borderWidth: 1
        }]
      },
      options: {
        scales: {
          y: {
            beginAtZero: true
          }
        }
      }
    });
  </script>
</body>
</html>'

curl -X POST http://localhost:8890/api/canvas \
  -H "Content-Type: application/json" \
  -d "{\"html\":$(echo "$CHART_HTML" | jq -Rs .)}" \
  && echo "✅ Chart sent" \
  || echo "❌ Failed to send chart"

echo ""
echo "📈 Canvas should now show a bar chart (live update test)"
echo ""
echo "✨ Canvas tests complete!"
