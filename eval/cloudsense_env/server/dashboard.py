"""Inline HTML dashboard served at GET /."""

DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>CloudSense — FinOps RL Benchmark</title>
<style>
  :root {
    --bg: #0b1020;
    --panel: #121a36;
    --panel-2: #182245;
    --text: #e6ecff;
    --muted: #9aa5c4;
    --accent: #5b9bff;
    --accent-2: #57d6a4;
    --warn: #ffb347;
    --danger: #ff6b6b;
    --border: #243056;
  }
  * { box-sizing: border-box; }
  html, body {
    margin: 0; padding: 0;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    background: radial-gradient(ellipse at top, #1a2547 0%, var(--bg) 60%);
    color: var(--text);
    min-height: 100vh;
  }
  .container { max-width: 1100px; margin: 0 auto; padding: 32px 24px 80px; }
  header { text-align: center; margin-bottom: 40px; }
  .logo { font-size: 56px; margin-bottom: 8px; }
  h1 {
    margin: 0 0 8px;
    font-size: 36px;
    letter-spacing: -0.5px;
    background: linear-gradient(135deg, var(--accent), var(--accent-2));
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
  }
  .tagline { color: var(--muted); font-size: 16px; max-width: 640px; margin: 0 auto; line-height: 1.5; }
  .badges { display: flex; gap: 8px; justify-content: center; margin-top: 16px; flex-wrap: wrap; }
  .badge {
    background: var(--panel);
    border: 1px solid var(--border);
    color: var(--muted);
    padding: 4px 12px;
    border-radius: 999px;
    font-size: 12px;
    font-family: ui-monospace, "SF Mono", Menlo, monospace;
  }
  .grid { display: grid; gap: 20px; }
  .grid-3 { grid-template-columns: repeat(3, 1fr); }
  .grid-2 { grid-template-columns: repeat(2, 1fr); }
  @media (max-width: 760px) {
    .grid-3, .grid-2 { grid-template-columns: 1fr; }
  }
  .card {
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: 14px;
    padding: 20px;
  }
  .stat { text-align: center; }
  .stat .num {
    font-size: 36px;
    font-weight: 700;
    background: linear-gradient(135deg, var(--accent), var(--accent-2));
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
  }
  .stat .label { color: var(--muted); font-size: 13px; margin-top: 4px; text-transform: uppercase; letter-spacing: 0.5px; }
  .section { margin-top: 40px; }
  .section h2 {
    font-size: 20px;
    margin: 0 0 16px;
    display: flex;
    align-items: center;
    gap: 8px;
  }
  .section h2::before {
    content: "";
    width: 4px;
    height: 18px;
    background: linear-gradient(to bottom, var(--accent), var(--accent-2));
    border-radius: 2px;
  }
  .task {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 14px 16px;
    border: 1px solid var(--border);
    border-radius: 10px;
    background: var(--panel-2);
    margin-bottom: 10px;
  }
  .task .meta { display: flex; flex-direction: column; gap: 4px; }
  .task .name { font-weight: 600; font-size: 15px; }
  .task .desc { color: var(--muted); font-size: 12px; }
  .task .right { display: flex; align-items: center; gap: 14px; }
  .pill {
    font-size: 11px;
    padding: 3px 10px;
    border-radius: 999px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    font-weight: 600;
  }
  .pill.easy { background: rgba(87, 214, 164, 0.15); color: var(--accent-2); }
  .pill.medium { background: rgba(255, 179, 71, 0.15); color: var(--warn); }
  .pill.hard { background: rgba(255, 107, 107, 0.15); color: var(--danger); }
  .score {
    font-family: ui-monospace, "SF Mono", Menlo, monospace;
    font-size: 14px;
    color: var(--accent);
    min-width: 48px;
    text-align: right;
  }
  table { width: 100%; border-collapse: collapse; font-size: 14px; }
  th, td { text-align: left; padding: 10px 8px; border-bottom: 1px solid var(--border); }
  th { color: var(--muted); font-weight: 500; font-size: 12px; text-transform: uppercase; letter-spacing: 0.5px; }
  td code {
    font-family: ui-monospace, "SF Mono", Menlo, monospace;
    font-size: 13px;
    color: var(--accent);
    background: var(--panel-2);
    padding: 2px 6px;
    border-radius: 4px;
  }
  .method {
    display: inline-block;
    font-family: ui-monospace, monospace;
    font-size: 11px;
    font-weight: 700;
    padding: 2px 8px;
    border-radius: 4px;
    min-width: 46px;
    text-align: center;
  }
  .method.get { background: rgba(91, 155, 255, 0.18); color: var(--accent); }
  .method.post { background: rgba(87, 214, 164, 0.18); color: var(--accent-2); }
  .actions { display: flex; gap: 12px; flex-wrap: wrap; margin-top: 24px; justify-content: center; }
  .btn {
    background: var(--panel);
    border: 1px solid var(--border);
    color: var(--text);
    padding: 10px 18px;
    border-radius: 10px;
    text-decoration: none;
    font-size: 14px;
    font-weight: 500;
    transition: all 0.15s ease;
  }
  .btn:hover { background: var(--panel-2); border-color: var(--accent); }
  .btn.primary {
    background: linear-gradient(135deg, var(--accent), var(--accent-2));
    color: #0b1020;
    border: none;
    font-weight: 600;
  }
  .btn.primary:hover { transform: translateY(-1px); box-shadow: 0 6px 20px rgba(91, 155, 255, 0.3); }
  footer {
    text-align: center;
    margin-top: 60px;
    color: var(--muted);
    font-size: 12px;
  }
  .feature {
    display: flex;
    gap: 12px;
    align-items: flex-start;
  }
  .feature .icon {
    font-size: 22px;
    line-height: 1;
    margin-top: 2px;
  }
  .feature .body strong { display: block; margin-bottom: 4px; color: var(--text); }
  .feature .body span { color: var(--muted); font-size: 13px; line-height: 1.5; }
</style>
</head>
<body>
<div class="container">
  <header>
    <div class="logo">☁️</div>
    <h1>CloudSense</h1>
    <p class="tagline">An OpenEnv-compatible RL benchmark for training and evaluating FinOps AI agents on cloud cost optimization. Real AWS pricing. Blast radius mechanics. Production-safety reasoning.</p>
    <div class="badges">
      <span class="badge">openenv</span>
      <span class="badge">finops</span>
      <span class="badge">v1.0.0</span>
      <span class="badge">aws • us-east-1</span>
    </div>
  </header>

  <div class="grid grid-3">
    <div class="card stat">
      <div class="num">3</div>
      <div class="label">Tasks</div>
    </div>
    <div class="card stat">
      <div class="num">62</div>
      <div class="label">Resources</div>
    </div>
    <div class="card stat">
      <div class="num">9</div>
      <div class="label">Action Types</div>
    </div>
  </div>

  <div class="section">
    <h2>Tasks</h2>
    <div class="task">
      <div class="meta">
        <div class="name">startup-cleanup</div>
        <div class="desc">7 resources · ~$627/mo · obvious dev/staging waste</div>
      </div>
      <div class="right">
        <span class="pill easy">easy</span>
        <span class="score">0.94</span>
      </div>
    </div>
    <div class="task">
      <div class="meta">
        <div class="name">mid-size-audit</div>
        <div class="desc">15 resources · ~$3,487/mo · prod safety required</div>
      </div>
      <div class="right">
        <span class="pill medium">medium</span>
        <span class="score">0.81</span>
      </div>
    </div>
    <div class="task">
      <div class="meta">
        <div class="name">enterprise-finops</div>
        <div class="desc">40 resources · ~$14,230/mo · dependencies + blast radius</div>
      </div>
      <div class="right">
        <span class="pill hard">hard</span>
        <span class="score">0.76</span>
      </div>
    </div>
    <p style="color: var(--muted); font-size: 12px; margin-top: 8px;">Baseline scores from <code style="background: var(--panel-2); padding: 2px 6px; border-radius: 4px; color: var(--accent);">Qwen/Qwen2.5-72B-Instruct</code> via Hugging Face Router.</p>
  </div>

  <div class="section">
    <h2>Why this matters</h2>
    <div class="grid grid-2">
      <div class="card feature">
        <div class="icon">💸</div>
        <div class="body">
          <strong>Real AWS pricing</strong>
          <span>Actual us-east-1 on-demand rates (Q1 2025) for EC2, RDS, S3, ELB, NAT, EBS, ES, K8s.</span>
        </div>
      </div>
      <div class="card feature">
        <div class="icon">💥</div>
        <div class="body">
          <strong>Blast radius mechanic</strong>
          <span>Every action computes cascading impact through dependency graphs. Agents that reason about it earn bonus reward.</span>
        </div>
      </div>
      <div class="card feature">
        <div class="icon">🛡️</div>
        <div class="body">
          <strong>Production safety</strong>
          <span>Critical prod resources must be skipped — terminating them costs −0.50. Distinguishes reasoning from optimization.</span>
        </div>
      </div>
      <div class="card feature">
        <div class="icon">📊</div>
        <div class="body">
          <strong>Multi-component reward</strong>
          <span>Cost reduction + action correctness + safety + reasoning quality + blast radius awareness. Clamped to [0, 1].</span>
        </div>
      </div>
    </div>
  </div>

  <div class="section">
    <h2>API endpoints</h2>
    <div class="card" style="padding: 4px 16px;">
      <table>
        <thead><tr><th>Method</th><th>Endpoint</th><th>Description</th></tr></thead>
        <tbody>
          <tr><td><span class="method get">GET</span></td><td><code>/health</code></td><td>Health check</td></tr>
          <tr><td><span class="method get">GET</span></td><td><code>/tasks</code></td><td>List available tasks</td></tr>
          <tr><td><span class="method post">POST</span></td><td><code>/reset?task_id=&lt;id&gt;</code></td><td>Start episode (defaults to easy)</td></tr>
          <tr><td><span class="method post">POST</span></td><td><code>/step</code></td><td>Execute action (JSON body)</td></tr>
          <tr><td><span class="method get">GET</span></td><td><code>/state</code></td><td>Current observation</td></tr>
          <tr><td><span class="method post">POST</span></td><td><code>/close</code></td><td>End episode</td></tr>
        </tbody>
      </table>
    </div>
  </div>

  <div class="actions">
    <a class="btn primary" href="/docs">Open API Docs</a>
    <a class="btn" href="/tasks">View tasks</a>
    <a class="btn" href="/health">Health</a>
    <a class="btn" href="https://github.com/Jaswanth-K1210/cloudsense" target="_blank" rel="noopener">GitHub</a>
  </div>

  <footer>
    CloudSense · OpenEnv FinOps Benchmark · Pricing data Q1 2025
  </footer>
</div>
</body>
</html>"""
