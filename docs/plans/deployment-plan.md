# SnoopLog Deployment Plan

**Goal:** Zero-cost portfolio deployment. Dashboard and dummy-app on Vercel (free), pipeline on Google Cloud Run (scale-to-zero). Firestore for persistent log/incident history. GitHub Actions for periodic traffic generation.

**Date:** 2026-03-14

---

## Architecture

```
    Portfolio visitor                    GitHub Actions (cron)
         |                                     |
         v                                     v
  ┌─────────────┐                     ┌─────────────────┐
  │  Dashboard   │                     │   Dummy App      │
  │  (Vercel)    │                     │   (Vercel)       │
  └──────┬───┬──┘                     └────────┬─────────┘
         |   |                                  |
    Firestore|   WebSocket (only when           | POST /api/ingest
    (read)   |    pipeline is live)              | (fire-and-forget)
         |   |                                  |
         v   └──────────────┐   ┌───────────────┘
  ┌──────────────┐          v   v
  │  Firestore   │    ┌──────────────────┐
  │  (free tier) │<───│    Pipeline       │
  │              │    │  (Cloud Run)      │
  │  - logs      │    │  min-instances: 0 │
  │  - incidents │    │                   │
  │  - stats     │    │  Writes incidents │
  └──────────────┘    │  + logs to        │
                      │  Firestore        │
                      └──────────────────┘
```

**Key insight:** The dashboard never wakes the pipeline. It reads from Firestore directly. The pipeline only runs when logs are being ingested (during GitHub Actions cron or live demo).

---

## What Gets Dropped

| Docker-compose service | Reason |
|------------------------|--------|
| `caddy` | Cloud Run + Vercel handle TLS |
| `log-forwarder` | Redundant — dummy-app already POSTs logs directly via `lib/logger.js` |
| `repo-init` / `repo-sync` | Replace with git clone at container startup |
| `traffic-gen` | Replaced by GitHub Actions cron workflow |

---

## Phases

### Phase 0: Firebase Project Setup

**What:** Create a Firebase project with Firestore enabled.

1. Go to [Firebase Console](https://console.firebase.google.com) or use `firebase init`
2. Create project (or use existing GCP project)
3. Enable Firestore in **Native mode** (not Datastore mode)
4. Create a service account for the pipeline with `Cloud Datastore User` role
5. Generate a service account key JSON (for Cloud Run)
6. Note the project ID — needed for both pipeline and dashboard env vars

**Firestore collections:**

```
snooplog-logs/          (capped — keep last ~500)
  ├── {auto-id}
  │   ├── id: string
  │   ├── timestamp: string
  │   ├── level: string
  │   ├── message: string
  │   ├── source: string
  │   ├── score: number
  │   ├── tier: string
  │   └── filtered: boolean
  │
snooplog-incidents/     (all incidents, newest first)
  ├── {auto-id}
  │   ├── id: string
  │   ├── timestamp: string
  │   ├── severity: string
  │   ├── source: string
  │   ├── report: string
  │   ├── root_cause: string
  │   ├── suggested_fix: string
  │   ├── code_refs: array
  │   ├── context_events: array
  │   ├── log_count: number
  │   └── investigation_reason: string
  │
snooplog-stats/         (single document, running counters)
  └── current
      ├── logs_scored: number
      ├── triaged_batches: number
      ├── incidents_raised: number
      ├── tool_calls: number
      └── logs_suppressed: number
```

**Firestore security rules** (dashboard reads are public, writes from pipeline only):

```
rules_version = '2';
service cloud.firestore {
  match /databases/{database}/documents {
    match /snooplog-logs/{doc} {
      allow read: if true;
      allow write: if false; // pipeline uses admin SDK (bypasses rules)
    }
    match /snooplog-incidents/{doc} {
      allow read: if true;
      allow write: if false;
    }
    match /snooplog-stats/{doc} {
      allow read: if true;
      allow write: if false;
    }
  }
}
```

> The pipeline uses the Firebase Admin SDK (server-side, authenticated via service account), which bypasses security rules entirely. The rules above only govern client-side reads from the dashboard.

---

### Phase 1: Pipeline — Add Firestore Persistence

**What:** Subscribe to events on the bus and write logs/incidents/stats to Firestore. This is a new integration module, same pattern as the existing Discord integration.

#### 1a. New file: `pipeline/integrations/firestore.py` (~60 lines)

```python
"""Firestore integration — persists logs, incidents, and stats for the dashboard."""

import logging
import os
from shared.events import bus

logger = logging.getLogger("snooplog.integrations.firestore")

# Lazy-init Firestore client (only when enabled)
_db = None
_stats_ref = None

LOG_COLLECTION = "snooplog-logs"
INCIDENT_COLLECTION = "snooplog-incidents"
STATS_COLLECTION = "snooplog-stats"
MAX_STORED_LOGS = 500


def _get_db():
    global _db, _stats_ref
    if _db is None:
        from google.cloud import firestore
        _db = firestore.Client()
        _stats_ref = _db.collection(STATS_COLLECTION).document("current")
        # Initialize stats doc if missing
        if not _stats_ref.get().exists:
            _stats_ref.set({
                "logs_scored": 0,
                "triaged_batches": 0,
                "incidents_raised": 0,
                "tool_calls": 0,
                "logs_suppressed": 0,
            })
    return _db


def _on_log_scored(data: dict):
    """Write scored log to Firestore and increment counter."""
    try:
        from google.cloud import firestore
        db = _get_db()
        doc = {
            "id": data.get("id", ""),
            "timestamp": data.get("timestamp", ""),
            "level": data.get("level", ""),
            "message": data.get("message", ""),
            "source": data.get("source", ""),
            "score": data.get("pipeline", {}).get("anomaly_score", 0),
            "tier": data.get("pipeline", {}).get("tier", ""),
            "filtered": data.get("pipeline", {}).get("filtered", False),
        }
        db.collection(LOG_COLLECTION).add(doc)
        _stats_ref.update({"logs_scored": firestore.Increment(1)})
    except Exception:
        logger.warning("Failed to write log to Firestore", exc_info=True)


def _on_incident_created(data: dict):
    """Write incident to Firestore and increment counter."""
    try:
        from google.cloud import firestore
        db = _get_db()
        incident = data.get("incident", data)
        doc = {
            "id": data.get("id", ""),
            "timestamp": data.get("timestamp", ""),
            "severity": incident.get("severity", "medium"),
            "source": data.get("source", ""),
            "report": incident.get("report", ""),
            "root_cause": incident.get("root_cause", ""),
            "suggested_fix": incident.get("suggested_fix", ""),
            "code_refs": incident.get("code_refs", []),
            "context_events": data.get("context_events", []),
            "log_count": data.get("log_count", 0),
            "investigation_reason": data.get("investigation_reason", ""),
            "primary_event": data.get("primary_event", {}),
            "related_log_ids": data.get("related_log_ids", []),
        }
        db.collection(INCIDENT_COLLECTION).add(doc)
        _stats_ref.update({"incidents_raised": firestore.Increment(1)})
    except Exception:
        logger.warning("Failed to write incident to Firestore", exc_info=True)


def _on_triaged(data: dict):
    try:
        from google.cloud import firestore
        _get_db()
        _stats_ref.update({"triaged_batches": firestore.Increment(1)})
    except Exception:
        pass


def _on_tool_call(data: dict):
    try:
        from google.cloud import firestore
        _get_db()
        _stats_ref.update({"tool_calls": firestore.Increment(1)})
    except Exception:
        pass


def _on_suppressed(data: dict):
    try:
        from google.cloud import firestore
        _get_db()
        _stats_ref.update({"logs_suppressed": firestore.Increment(1)})
    except Exception:
        pass


def configure_firestore_integration():
    """Subscribe to bus events. Call during app startup."""
    if not os.getenv("FIRESTORE_ENABLED", "").lower() in ("1", "true", "yes"):
        logger.info("Firestore integration disabled (set FIRESTORE_ENABLED=true to enable)")
        return

    logger.info("Firestore integration enabled")
    bus.subscribe("log:scored", _on_log_scored)
    bus.subscribe("incident:created", _on_incident_created)
    bus.subscribe("log:triaged", _on_triaged)
    bus.subscribe("agent:tool_call", _on_tool_call)
    bus.subscribe("log:suppressed", _on_suppressed)
```

#### 1b. Wire into startup in `pipeline/main.py`

Add to the existing `startup()` function, right after `configure_discord_integration()`:

```python
from pipeline.integrations.firestore import configure_firestore_integration
# ... in startup():
configure_firestore_integration()
```

#### 1c. Add dependency to `pipeline/requirements.txt`

```
google-cloud-firestore>=2.16.0
```

#### 1d. Add Firestore REST endpoint for stats/cleanup (optional, nice-to-have)

A `GET /api/stats` endpoint that returns current stats from Firestore. Not critical — the dashboard can read Firestore directly.

---

### Phase 2: Dashboard — Load Historical Data from Firestore

**What:** On page load, fetch logs + incidents + stats from Firestore. Layer live WebSocket data on top when available. Fix the aggressive WebSocket retry loop.

#### 2a. Install Firebase JS SDK

```bash
cd dashboard && npm install firebase
```

#### 2b. New file: `dashboard/lib/firebase.ts` (~25 lines)

```typescript
import { initializeApp } from "firebase/app";
import { getFirestore } from "firebase/firestore";

const firebaseConfig = {
  apiKey: process.env.NEXT_PUBLIC_FIREBASE_API_KEY,
  projectId: process.env.NEXT_PUBLIC_FIREBASE_PROJECT_ID,
  // No auth needed — Firestore rules allow public reads
};

const app = initializeApp(firebaseConfig);
export const db = getFirestore(app);
```

#### 2c. New file: `dashboard/lib/firestore-history.ts` (~50 lines)

```typescript
import { db } from "./firebase";
import {
  collection,
  query,
  orderBy,
  limit,
  getDocs,
  doc,
  getDoc,
} from "firebase/firestore";

export async function fetchHistoricalLogs(max = 200) {
  const q = query(
    collection(db, "snooplog-logs"),
    orderBy("timestamp", "desc"),
    limit(max)
  );
  const snap = await getDocs(q);
  return snap.docs.map((d) => d.data()).reverse();
}

export async function fetchHistoricalIncidents(max = 50) {
  const q = query(
    collection(db, "snooplog-incidents"),
    orderBy("timestamp", "desc"),
    limit(max)
  );
  const snap = await getDocs(q);
  return snap.docs.map((d) => d.data());
}

export async function fetchStats() {
  const ref = doc(db, "snooplog-stats", "current");
  const snap = await getDoc(ref);
  if (!snap.exists()) return null;
  return snap.data();
}
```

#### 2d. Update `dashboard/app/components/live-data.tsx`

**Change 1:** Load Firestore history on mount (before WebSocket connects).

In the `useEffect`, before `connect()`:

```typescript
// Load historical data from Firestore
async function loadHistory() {
  try {
    const [histLogs, histIncidents, histStats] = await Promise.all([
      fetchHistoricalLogs(),
      fetchHistoricalIncidents(),
      fetchStats(),
    ]);
    if (histLogs.length) setLogs(histLogs as LogEvent[]);
    if (histIncidents.length) setIncidents(histIncidents.map(normalizeIncident).filter(Boolean));
    if (histStats) setStats({
      logsScored: histStats.logs_scored ?? 0,
      triagedBatches: histStats.triaged_batches ?? 0,
      incidentsRaised: histStats.incidents_raised ?? 0,
      toolCalls: histStats.tool_calls ?? 0,
      logsSuppressed: histStats.logs_suppressed ?? 0,
    });
  } catch (e) {
    console.warn("Could not load Firestore history:", e);
  }
}
loadHistory();
```

**Change 2:** Exponential backoff on WebSocket retry.

Replace the fixed 1.5s retry at line 440:

```typescript
// Before:
retryTimer = setTimeout(connect, 1500);

// After (exponential backoff, cap at 60s):
retryDelay = Math.min(retryDelay * 2, 60000);
retryTimer = setTimeout(connect, retryDelay);

// Reset on successful connect:
ws.onopen = () => {
  retryDelay = 1500;  // reset backoff
  // ... rest of onopen
};
```

This ensures a portfolio visitor's browser stops hammering the pipeline after a few failed attempts (1.5s -> 3s -> 6s -> 12s -> 24s -> 48s -> 60s cap).

**Change 3:** Show a "portfolio mode" indicator when WebSocket is disconnected but Firestore data is loaded.

Update the connection status display — instead of "Check that the pipeline is running on localhost:3001", show something like "Viewing historical data. Live stream available during demo." This is a copy change in the `ws.onclose` and `ws.onerror` handlers.

---

### Phase 3: Pipeline Dockerfile & Cloud Run Config

**What:** Update the Dockerfile for Cloud Run compatibility. Handle repo cloning at startup.

#### 3a. Update `pipeline/Dockerfile`

```dockerfile
FROM python:3.12-slim

# Install git for agent tool calls (grep_code, git_blame, etc.)
RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*

RUN groupadd -r snooplog && useradd -r -g snooplog -m snooplog

WORKDIR /app

COPY pipeline/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY shared/ /app/shared/
COPY pipeline/ /app/pipeline/
COPY snooplog.yaml /app/snooplog.yaml

# Writable dirs for SQLite, snapshots, and repo clone
RUN mkdir -p /data /app/data /repo \
    && chown -R snooplog:snooplog /data /app/data /repo

USER snooplog

EXPOSE 3001

# Clone repo at startup, then launch uvicorn
CMD ["sh", "-c", "\
  if [ -n \"$REPO_URL\" ] && [ ! -d /repo/.git ]; then \
    echo 'Cloning repo...' && git clone --depth=1 \"$REPO_URL\" /repo 2>/dev/null || echo 'Repo clone failed (non-fatal)'; \
  fi && \
  exec uvicorn pipeline.main:app --host 0.0.0.0 --port 3001"]
```

Key changes from current Dockerfile:
- Installs `git` (needed for `ToolExecutor` subprocess calls)
- Removes `read_only` constraint (Cloud Run handles this differently)
- Clones repo at startup instead of relying on shared Docker volume
- Removes `gosu` / `docker-entrypoint.sh` (not needed on Cloud Run)

#### 3b. Cloud Run deployment command

```bash
PROJECT_ID=your-project-id
REGION=us-central1
REPO=$REGION-docker.pkg.dev/$PROJECT_ID/snooplog

# Create Artifact Registry (one-time)
gcloud artifacts repositories create snooplog \
  --repository-format=docker \
  --location=$REGION

# Build from repo root (Dockerfile COPY paths need repo root as build context)
gcloud builds submit \
  --tag $REPO/pipeline:latest \
  --timeout=600s

# Create secrets (one-time)
printf '%s' "$OPENROUTER_API_KEY" | gcloud secrets create openrouter-key --data-file=-
printf '%s' "$DISCORD_WEBHOOK_URL" | gcloud secrets create discord-webhook --data-file=-

# Deploy
gcloud run deploy snooplog-pipeline \
  --image $REPO/pipeline:latest \
  --port 3001 \
  --memory 512Mi \
  --cpu 1 \
  --min-instances 0 \
  --max-instances 2 \
  --timeout 300 \
  --set-secrets "OPENROUTER_API_KEY=openrouter-key:latest,DISCORD_WEBHOOK_URL=discord-webhook:latest" \
  --set-env-vars "\
FIRESTORE_ENABLED=true,\
CORS_ORIGINS=https://your-dashboard.vercel.app,\
REPO_URL=https://github.com/FonseLULW/HackathonW2026.git,\
KNOWN_LOG_DB_PATH=/data/known_patterns.db" \
  --allow-unauthenticated \
  --region $REGION
```

Notes:
- `--min-instances 0` — scale to zero when idle
- `--timeout 300` — 5min request timeout (enough for investigations, WebSocket sessions will reconnect)
- `--allow-unauthenticated` — the pipeline API is public (dummy-app needs to POST to it)
- Firestore auth happens automatically via the Cloud Run service account (no key needed if same GCP project)

---

### Phase 4: Vercel Deployment

**What:** Deploy dashboard and dummy-app to Vercel. Both are standard Next.js apps.

#### 4a. Dashboard

```bash
cd dashboard
npx vercel link          # link to Vercel project
npx vercel env add NEXT_PUBLIC_WS_URL              # wss://snooplog-pipeline-xxx.run.app/ws
npx vercel env add NEXT_PUBLIC_FIREBASE_API_KEY    # from Firebase console
npx vercel env add NEXT_PUBLIC_FIREBASE_PROJECT_ID # your GCP project ID
npx vercel --prod
```

No `vercel.json` needed — Next.js is auto-detected. The `output: "standalone"` in `next.config.ts` is fine; Vercel ignores it and uses its own build pipeline.

#### 4b. Dummy App

```bash
cd dummy-app
npx vercel link
npx vercel env add PIPELINE_URL  # https://snooplog-pipeline-xxx.run.app/api/ingest
npx vercel --prod
```

**Important:** `PIPELINE_URL` is used server-side in `lib/logger.js` (inside API routes). Vercel serverless functions can make outbound HTTP requests, so fire-and-forget `fetch()` works. The `catch(() => {})` ensures the function doesn't crash if the pipeline is down.

**Gotcha:** Vercel serverless functions have a 10s timeout on free tier. The `fetch()` to the pipeline is fire-and-forget so this is fine — the function doesn't await the response.

---

### Phase 5: GitHub Actions Traffic Generator

**What:** A cron workflow that hits the dummy-app to generate realistic log traffic. This wakes the pipeline, which processes logs, writes to Firestore, then scales back to zero.

#### 5a. New file: `.github/workflows/traffic-gen.yml`

```yaml
name: Traffic Generator

on:
  schedule:
    # Run every 6 hours — keeps Firestore data fresh for portfolio visitors
    - cron: '0 */6 * * *'
  workflow_dispatch: {}  # Allow manual trigger

env:
  DUMMY_APP_URL: ${{ vars.DUMMY_APP_URL }}  # https://your-dummy-app.vercel.app

jobs:
  generate-traffic:
    runs-on: ubuntu-latest
    timeout-minutes: 5
    steps:
      - name: Generate order traffic
        run: |
          echo "Generating traffic against $DUMMY_APP_URL"

          # Simulate normal orders
          for i in $(seq 1 10); do
            curl -s -o /dev/null -w "%{http_code}" \
              "$DUMMY_APP_URL/api/orders" \
              -X POST -H 'Content-Type: application/json' \
              -d "{\"items\":[{\"id\":\"SKU-$i\",\"qty\":$((RANDOM % 5 + 1))}]}"
            echo " - order $i sent"
            sleep 1
          done

          # Simulate some product browsing (generates info logs)
          for i in $(seq 1 5); do
            curl -s -o /dev/null "$DUMMY_APP_URL/api/products" || true
            sleep 0.5
          done

          # Simulate error scenarios (bad payloads, missing fields)
          curl -s -o /dev/null "$DUMMY_APP_URL/api/orders" \
            -X POST -H 'Content-Type: application/json' \
            -d '{"invalid": true}'

          curl -s -o /dev/null "$DUMMY_APP_URL/api/orders" \
            -X POST -H 'Content-Type: application/json' \
            -d '{"items":[]}'

          echo "Traffic generation complete"

      - name: Wait for pipeline processing
        run: |
          echo "Waiting 45s for pipeline to process, triage, and investigate..."
          sleep 45

      - name: Verify pipeline health
        run: |
          PIPELINE_URL="${{ vars.PIPELINE_URL }}"
          if [ -n "$PIPELINE_URL" ]; then
            STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$PIPELINE_URL/health" || echo "000")
            echo "Pipeline health check: $STATUS"
          else
            echo "PIPELINE_URL not set, skipping health check"
          fi
```

#### 5b. GitHub repo settings

Add these as **Repository Variables** (Settings > Secrets and variables > Actions > Variables):
- `DUMMY_APP_URL` — your Vercel dummy-app URL
- `PIPELINE_URL` — your Cloud Run pipeline URL (optional, for health check)

---

## Environment Variables Reference

### Pipeline (Cloud Run)

| Variable | Value | Source |
|----------|-------|--------|
| `OPENROUTER_API_KEY` | API key | Secret Manager |
| `DISCORD_WEBHOOK_URL` | Webhook URL | Secret Manager |
| `FIRESTORE_ENABLED` | `true` | Env var |
| `CORS_ORIGINS` | `https://your-dashboard.vercel.app` | Env var |
| `REPO_URL` | `https://github.com/FonseLULW/HackathonW2026.git` | Env var |
| `KNOWN_LOG_DB_PATH` | `/data/known_patterns.db` | Env var |
| `REPO_PATH` | `/repo` | Env var |

### Dashboard (Vercel)

| Variable | Value | Build-time? |
|----------|-------|-------------|
| `NEXT_PUBLIC_WS_URL` | `wss://snooplog-pipeline-xxx.run.app/ws` | Yes |
| `NEXT_PUBLIC_FIREBASE_API_KEY` | Firebase web API key | Yes |
| `NEXT_PUBLIC_FIREBASE_PROJECT_ID` | GCP project ID | Yes |

### Dummy App (Vercel)

| Variable | Value | Build-time? |
|----------|-------|-------------|
| `PIPELINE_URL` | `https://snooplog-pipeline-xxx.run.app/api/ingest` | No (runtime) |

### GitHub Actions

| Variable | Value | Type |
|----------|-------|------|
| `DUMMY_APP_URL` | Vercel dummy-app URL | Repository variable |
| `PIPELINE_URL` | Cloud Run pipeline URL | Repository variable |

---

## Cost Analysis

| Service | Free Tier | Our Usage | Cost |
|---------|-----------|-----------|------|
| **Vercel** (dashboard) | 100GB bandwidth, unlimited deploys | Static + SSR | $0 |
| **Vercel** (dummy-app) | Same project, shared quota | Serverless functions | $0 |
| **Cloud Run** | 2M requests/mo, 360K vCPU-sec | ~120 requests/day (4 cron runs x 30 requests) | $0 |
| **Firestore** | 1GB storage, 50K reads/day, 20K writes/day | ~120 writes/day, <100 reads/day | $0 |
| **Artifact Registry** | 500MB free | ~200MB image | $0 |
| **Secret Manager** | 6 active versions free | 2 secrets | $0 |
| **GitHub Actions** | 2000 min/mo free | ~5 min/day (4 runs x ~1.5min) | $0 |
| **Total** | | | **$0** |

---

## Implementation Order

The work has no circular dependencies. Here is the suggested order, with parallelizable steps marked.

```
Phase 0: Firebase project + Firestore setup (manual, ~10 min)
    |
    ├── Phase 1: Pipeline Firestore integration (code, ~30 min)
    |     1a. Create pipeline/integrations/firestore.py
    |     1b. Wire into main.py startup
    |     1c. Add google-cloud-firestore to requirements.txt
    |
    ├── Phase 2: Dashboard historical data (code, ~30 min)  [parallel with Phase 1]
    |     2a. npm install firebase
    |     2b. Create lib/firebase.ts + lib/firestore-history.ts
    |     2c. Update live-data.tsx (load history + backoff fix)
    |     2d. Update disconnected state copy
    |
    v
Phase 3: Pipeline Dockerfile update (code, ~15 min)
    |     3a. Update Dockerfile (add git, repo clone at startup)
    |
    v
Phase 4: Deploy pipeline to Cloud Run (infra, ~15 min)
    |     Build image, push to Artifact Registry, deploy
    |     Note the Cloud Run URL — needed for next steps
    |
    ├── Phase 5: Deploy to Vercel (infra, ~10 min)  [parallel]
    |     5a. Dashboard — set env vars, deploy
    |     5b. Dummy app — set env vars, deploy
    |
    └── Phase 6: GitHub Actions workflow (code, ~10 min)  [parallel]
          6a. Create .github/workflows/traffic-gen.yml
          6b. Set repository variables
          6c. Trigger manual run to verify
```

**Total estimated effort: ~2 hours**

---

## Post-Deployment Checklist

- [ ] Firestore collections are being populated (check Firebase console)
- [ ] Dashboard loads historical data on page load (without pipeline running)
- [ ] Dashboard shows "live stream offline" gracefully (not an error)
- [ ] Dashboard WebSocket retry backs off (not hammering every 1.5s)
- [ ] Pipeline scales to zero after ~5 min of inactivity
- [ ] GitHub Actions cron runs successfully (check Actions tab)
- [ ] After cron run, new logs/incidents appear in Firestore
- [ ] After cron run, dashboard shows fresh data on next page load
- [ ] Discord notifications still fire during pipeline runs
- [ ] Pipeline cold start is under 15s (check Cloud Run logs)

---

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Cloud Run cold start slow (git clone) | First request after scale-to-zero takes ~10-15s | Use `--depth=1` clone. Dummy-app fetch is fire-and-forget so users aren't blocked. |
| Firestore write quota hit | Logs stop persisting | 20K writes/day is plenty for 120 writes/day usage. Not a real risk. |
| WebSocket on Cloud Run drops | Dashboard loses live stream mid-demo | Dashboard reconnects automatically. For live demos, pipeline stays warm due to active WebSocket. |
| Vercel serverless timeout | Dummy-app log POST fails silently | Fire-and-forget pattern means the app works regardless. Logs are best-effort. |
| SQLite on ephemeral Cloud Run | Pattern memory lost on redeploy | Acceptable — patterns have 1h TTL anyway. Pipeline re-learns quickly. |
