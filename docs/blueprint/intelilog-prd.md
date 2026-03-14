# InteliLog — Product Requirements Document

## HackTheBreak 2026 | March 13–15

---

## Overview

InteliLog is a self-contained, AI-powered log intelligence pipeline that ingests application logs, scores them for anomalies using a built-in ML model, and routes significant events through a tiered LLM cascade. The top-tier model has agent capabilities to explore the application's source code — running git blame, grepping files, and reading code — to produce full incident reports with root cause analysis, delivered to developers via Discord/Slack before they even know something is wrong.

### The problem

Developers drown in logs and alerts. Traditional monitoring tools (Grafana, Datadog, Prometheus) are great at collecting data and detecting that something is unusual, but they leave interpretation to humans. A developer gets woken up at 3 AM with "pod-xyz memory exceeded threshold" and spends 20 minutes digging through logs, correlating events, and reading code to figure out what happened.

### Our approach

We separate **detection** from **interpretation**. A lightweight ML model handles anomaly detection (is this unusual?), and an LLM cascade handles reasoning (what does this mean, what caused it, and who needs to know?). The key architectural idea is a **tiered model cascade** that's cost-conscious — most logs get filtered before touching an LLM, medium-anomaly logs go through a cheap/fast model, and only serious events reach a powerful reasoning model with agent capabilities.

### What makes this different

Enterprise tools like Rootly, IncidentFox, and Coroot exist in this space, but they're designed for large SRE teams with mature observability stacks. They require PagerDuty, Datadog, and complex integrations. InteliLog is **self-contained** — it needs nothing but raw log input. No existing tool combines built-in ML scoring with a tiered LLM agent that can investigate your codebase, packaged as a single deployable unit that a solo developer or small team can adopt immediately.

---

## Target user

Indie developers, small teams, and startups running applications on VPS/cloud without enterprise monitoring budgets. Anyone who has a deployed app producing logs and wants intelligent alerting without setting up a full observability stack.

---

## System architecture

```
Log sources (CLI, Docker sidecar, webhook, syslog)
        │
        ▼
┌─────────────────────────────┐
│   Log ingestion + parsing   │  ← Normalize to unified JSON
└─────────────────────────────┘
        │
        ▼
┌─────────────────────────────┐
│   Rule-based pre-filter     │  ← Drop known noise (health checks, etc.)
└─────────────────────────────┘
        │
        ▼
┌─────────────────────────────┐
│   ML anomaly scorer         │  ← Isolation forest, score 0.0–1.0
│   (scikit-learn in Python)    │
└─────────────────────────────┘
        │
   ┌────┼────────────┐
   ▼    ▼            ▼
 DROP  CHEAP LLM   REASONING LLM
       (Flash/     (Sonnet/GPT-4o)
       Haiku)           │
         │              ▼
         │     ┌────────────────┐
         │     │ Agent Framework │
         │     │ • Read files    │
         │     │ • Grep code     │
         │     │ • Git blame     │
         │     │ • Search logs   │
         │     └────────────────┘
         │              │
         ▼              ▼
    ┌──────────────────────┐
    │   Incident report    │
    │   (root cause +      │
    │    code refs + fix)  │
    └──────────────────────┘
         │            │
         ▼            ▼
    Discord/     Dashboard
    Slack        (Vercel)
```

---

## Shared data contract

Every component communicates using this JSON schema. This is the first thing the team agrees on before splitting into tracks. In the Python/FastAPI pipeline, this contract is enforced with Pydantic models.

```json
{
  "id": "uuid-v4",
  "timestamp": "2026-03-14T03:22:15.123Z",
  "source": "dummy-ecommerce-api",
  "level": "error",
  "message": "ECONNREFUSED - Connection refused to postgres:5432",
  "raw": "2026-03-14T03:22:15.123Z ERROR [db-pool] ECONNREFUSED...",
  "metadata": {
    "service": "order-service",
    "host": "prod-1",
    "container_id": "abc123"
  },
  "pipeline": {
    "anomaly_score": 0.87,
    "tier": "high",
    "tier_model": "openrouter/anthropic/claude-sonnet",
    "filtered": false,
    "filter_reason": null
  },
  "incident": {
    "report": "Connection pool exhaustion detected...",
    "root_cause": "Recent config change reduced max pool size...",
    "code_refs": [
      {
        "file": "src/db/pool.ts",
        "line": 42,
        "blame_author": "sepehr",
        "blame_date": "2026-03-13",
        "blame_commit": "a1b2c3d"
      }
    ],
    "severity": "high",
    "suggested_fix": "Revert pool size change in src/db/pool.ts:42"
  }
}
```

---

## Tech stack

| Component | Technology |
|---|---|
| Core pipeline | Python (FastAPI) |
| ML anomaly scorer | Native scikit-learn (train + score directly in Python) |
| LLM access | OpenRouter (single API for cheap + expensive tiers) |
| Agent framework | Custom lightweight loop with tool-use via OpenRouter API |
| Dashboard | Next.js on Vercel |
| Integrations | Discord webhooks, WebSocket for dashboard |
| Dummy app | Next.js (e-commerce API with deliberate failure modes) |
| Deployment | Docker Compose on GCP (Compute Engine or Cloud Run) |
| ML baseline storage | Pre-trained model serialized in Docker image; GCS bucket for production retraining |

---

## Security: agent sandboxing

The agent has read access to the application's source code. This is powerful but dangerous if not contained.

### Docker-based isolation

The agent runs inside a dedicated Docker container with restricted permissions:

```yaml
# docker-compose.yml (agent service)
agent:
  image: intelilog-agent
  user: "1000:1000"              # Non-root user
  read_only: true                 # Read-only filesystem
  security_opt:
    - no-new-privileges:true      # Cannot escalate
  cap_drop:
    - ALL                         # Drop all Linux capabilities
  volumes:
    - repo-volume:/repo:ro        # Source code mounted READ-ONLY
    - /tmp                        # Writable tmp for agent scratch
  networks:
    - agent-net                   # Isolated network
  deploy:
    resources:
      limits:
        memory: 512M
        cpus: "0.5"
```

### Agent access rules

- The agent can ONLY read files, run grep, and run git commands against the mounted repo volume.
- The agent CANNOT execute arbitrary code, make network requests beyond the OpenRouter API, or write to the repo.
- All agent tool calls are logged for audit.
- The agent has a timeout per investigation (60 seconds max for hackathon).

### Repo cloning strategy

The application's source code is cloned into a Docker volume at deploy time. For the hackathon, the dummy app repo is pre-cloned into the volume when the Docker Compose stack starts. In production, a webhook listener would trigger re-clone on each deploy.

```bash
# Init container clones repo into shared volume
git clone --depth 1 https://github.com/team/dummy-app.git /repo
```

---

## LLM tier routing

| Anomaly score | Tier | Model (via OpenRouter) | Action |
|---|---|---|---|
| < 0.3 | Low | None | Archive log, no LLM call |
| 0.3 – 0.7 | Medium | Gemini Flash / Haiku | Quick triage: is this worth escalating? |
| > 0.7 | High | Claude Sonnet / GPT-4o | Full investigation with agent tools |

The cheap model returns a structured response:

```json
{
  "escalate": true | false,
  "reason": "Brief explanation",
  "urgency": "low" | "medium" | "high"
}
```

If `escalate: true`, the log + context is forwarded to the expensive model with agent capabilities.

---

## ML anomaly scoring

### Training phase (pre-hackathon or during setup)

1. Collect "healthy" logs from the dummy app running normally (1000+ log lines).
2. Feature extraction: log level frequency, message length, error rate per time window, new/unseen log patterns, time between errors.
3. Train isolation forest using scikit-learn.
4. Serialize the trained model with `joblib.dump`.
5. Bundle the `.joblib` model file in the Docker image.

### Runtime inference

1. Log arrives, features are extracted using the same pipeline.
2. The Python scorer loads the model with `joblib.load` and runs `score_samples` (normalized to 0.0-1.0 anomaly score).
3. Score is attached to the log event JSON.
4. Routing logic uses the score to determine tier.

### Baseline storage

For the hackathon, the pre-trained model file lives in the Docker image at `/models/anomaly_scorer.joblib`. No external storage needed. The feature extraction config (expected log patterns, baseline stats) is a JSON file alongside it at `/models/baseline_config.json`.

---

## Dummy app specification

A simple Next.js e-commerce API with deliberate, triggerable failure modes:

### Endpoints

- `GET /api/products` — list products
- `POST /api/orders` — create order (uses DB)
- `GET /api/health` — health check

### Triggerable failures (via environment variables or API calls)

- `POST /api/chaos/db-leak` — starts leaking database connections
- `POST /api/chaos/memory` — begins allocating memory until OOM
- `POST /api/chaos/slow-query` — makes DB queries take 5+ seconds
- `POST /api/chaos/auth-fail` — starts returning 401s on random requests
- `POST /api/chaos/reset` — restores normal operation

### Log output

Structured JSON logs to stdout with timestamp, level, service, message, and request metadata. Docker captures stdout and routes to InteliLog.

---

## Dashboard requirements

A Next.js app on Vercel showing:

1. **Live pipeline view** — logs streaming in real-time via WebSocket, showing anomaly scores and tier routing decisions as they happen.
2. **Incident feed** — list of generated incident reports with severity, timestamp, root cause summary, and code references.
3. **Incident detail** — full report view with the agent's reasoning chain, referenced files, and suggested fix.
4. **Pipeline stats** — how many logs processed, how many filtered, tier distribution, estimated cost savings from the cascade.
5. **Configuration panel** (stretch goal) — adjust anomaly thresholds, manage webhook destinations.

---

## Team breakdown

| Person | Track | Primary deliverable |
|---|---|---|
| Person 1 | Ingestion + ML scoring | CLI/agent, log parsing, isolation forest scorer, feature extraction |
| Person 2 | LLM cascade + agent framework | Tier routing, prompt engineering, agent tools (read, grep, blame), investigation loop |
| Person 3 | Dashboard | Next.js app, WebSocket client, live pipeline view, incident feed/detail |
| Person 4 | Integrations + deployment + dummy app | Discord webhooks, Docker Compose, GCP deployment, dummy e-commerce app, demo script |

See individual specification documents for detailed implementation guides.

---

## Demo flow (for judging)

1. Show the dashboard — empty, waiting for logs.
2. Start the dummy app. Healthy logs flow in. Dashboard shows green, low anomaly scores, everything filtered.
3. Trigger a chaos endpoint (e.g., DB connection leak).
4. Watch the dashboard: anomaly scores climb, logs start hitting the cheap model, then escalation to the reasoning model.
5. The agent investigates: reads the dummy app's source code, runs git blame, finds the chaos endpoint.
6. A full incident report appears on the dashboard AND in the Discord channel.
7. Show the report: "Connection pool exhaustion detected. Source: /api/chaos/db-leak triggered at [time]. Relevant code: src/chaos.ts:24. Suggested fix: call /api/chaos/reset to restore normal pool behavior."
8. Talk through the architecture, the cost efficiency of the cascade, and the security model.

---

## Milestones

### Saturday morning
- Data contract agreed
- Repo set up with Docker Compose skeleton
- Each person can run the full stack locally

### Saturday evening
- Person 1: Logs flowing through ingestion, ML scoring working
- Person 2: LLM cascade routing logs, agent can read files
- Person 3: Dashboard rendering mock data via WebSocket
- Person 4: Dummy app running, Discord webhook sending test messages

### Sunday morning
- End-to-end pipeline working: dummy app → InteliLog → incident report → Discord + dashboard
- Demo script rehearsed
- Edge cases handled, error states graceful

### Sunday 11 AM
- Devpost submission with description, screenshots, GitHub link


