# Person 4: Integrations + Deployment + Dummy App - Implementation Spec

## InteliLog | HackTheBreak 2026

---

## Your role

You own three critical things: the output integrations (getting incident reports to Discord), the deployment infrastructure (Docker Compose on GCP), and the dummy app that generates realistic logs for the demo. You also own the demo script - making sure the end-to-end experience works flawlessly during judging. This role is underrated but make-or-break: if the demo does not work live, nothing else matters.

---

## Deliverables

1. **Dummy e-commerce app** - Next.js API with triggerable failures and structured logging
2. **Discord webhook integration** - formatted incident reports delivered to a channel
3. **Docker Compose setup** - full stack containerized and runnable
4. **GCP deployment** - everything running on Compute Engine or Cloud Run
5. **Demo script** - reliable, rehearsed sequence for judging

---

## 1. Dummy e-commerce app

A simple Next.js API that simulates an e-commerce backend. It produces structured JSON logs to stdout, which Docker captures and routes to InteliLog.

### Project setup

```bash
npx create-next-app@latest dummy-app --ts --app --tailwind
cd dummy-app
```

### Logger utility

```typescript
// lib/logger.ts
type LogLevel = 'debug' | 'info' | 'warn' | 'error' | 'fatal';

export function log(level: LogLevel, service: string, message: string, meta?: object) {
  const entry = {
    timestamp: new Date().toISOString(),
    level,
    service,
    message,
    ...meta && { metadata: meta }
  };
  // Write to stdout as JSON - Docker captures this
  process.stdout.write(JSON.stringify(entry) + '\n');
}
```

### API endpoints

```typescript
// app/api/products/route.ts
import { log } from '@/lib/logger';

const products = [
  { id: 1, name: 'Mechanical Keyboard', price: 149.99 },
  { id: 2, name: 'USB-C Hub', price: 49.99 },
  { id: 3, name: 'Monitor Arm', price: 89.99 },
];

export async function GET() {
  const start = Date.now();
  log('info', 'product-service', `GET /api/products 200 ${Date.now() - start}ms`);
  return Response.json(products);
}
```

```typescript
// app/api/orders/route.ts
import { log } from '@/lib/logger';
import { chaosState } from '@/lib/chaos';

export async function POST(req: Request) {
  const body = await req.json();
  const start = Date.now();

  // Check for active chaos modes
  if (chaosState.dbLeak) {
    log('warn', 'order-service', `Connection pool at ${chaosState.poolUsage}% capacity`);
    chaosState.poolUsage = Math.min(100, chaosState.poolUsage + 5);

    if (chaosState.poolUsage >= 95) {
      log('error', 'order-service', 'FATAL: too many connections for role "postgres" - connection pool exhausted after 500 retries', {
        pool_size: 20,
        active_connections: 20,
        waiting_queries: 47
      });
      return Response.json({ error: 'Service unavailable' }, { status: 503 });
    }
  }

  if (chaosState.slowQuery) {
    const delay = 3000 + Math.random() * 5000;
    await new Promise(r => setTimeout(r, delay));
    log('warn', 'order-service', `Slow query detected: INSERT INTO orders took ${delay.toFixed(0)}ms`, {
      query_time_ms: delay,
      threshold_ms: 1000
    });
  }

  if (chaosState.authFail && Math.random() > 0.5) {
    log('error', 'auth-service', 'JWT verification failed: token signature invalid', {
      user_id: body.user_id,
      endpoint: '/api/orders'
    });
    return Response.json({ error: 'Unauthorized' }, { status: 401 });
  }

  log('info', 'order-service', `POST /api/orders 201 ${Date.now() - start}ms`, {
    order_id: crypto.randomUUID(),
    items: body.items?.length || 0
  });

  return Response.json({ order_id: crypto.randomUUID(), status: 'created' }, { status: 201 });
}
```

```typescript
// app/api/health/route.ts
import { log } from '@/lib/logger';

export async function GET() {
  log('debug', 'health-check', 'GET /api/health 200');
  return Response.json({ status: 'ok' });
}
```

### Chaos system

```typescript
// lib/chaos.ts
export const chaosState = {
  dbLeak: false,
  poolUsage: 30,     // Starts at 30% (normal)
  memoryLeak: false,
  memoryUsageMB: 128,
  slowQuery: false,
  authFail: false,
};

export function activateChaos(mode: string) {
  switch (mode) {
    case 'db-leak':
      chaosState.dbLeak = true;
      chaosState.poolUsage = 30;
      break;
    case 'memory':
      chaosState.memoryLeak = true;
      // Allocate memory gradually
      const leak: Buffer[] = [];
      const interval = setInterval(() => {
        leak.push(Buffer.alloc(1024 * 1024 * 10)); // 10MB
        chaosState.memoryUsageMB += 10;
      }, 2000);
      setTimeout(() => clearInterval(interval), 60000); // Stop after 60s
      break;
    case 'slow-query':
      chaosState.slowQuery = true;
      break;
    case 'auth-fail':
      chaosState.authFail = true;
      break;
    case 'reset':
      chaosState.dbLeak = false;
      chaosState.poolUsage = 30;
      chaosState.memoryLeak = false;
      chaosState.memoryUsageMB = 128;
      chaosState.slowQuery = false;
      chaosState.authFail = false;
      break;
  }
}
```

```typescript
// app/api/chaos/[mode]/route.ts
import { activateChaos, chaosState } from '@/lib/chaos';
import { log } from '@/lib/logger';

export async function POST(req: Request, { params }: { params: { mode: string } }) {
  const mode = params.mode;
  activateChaos(mode);
  log('info', 'chaos-controller', `Chaos mode activated: ${mode}`);
  return Response.json({ mode, state: chaosState });
}
```

### Traffic generator

A script that simulates normal traffic to the dummy app, creating a baseline of healthy logs:

```typescript
// scripts/traffic.ts
const BASE_URL = process.env.DUMMY_APP_URL || 'http://localhost:3000';

async function generateTraffic() {
  while (true) {
    // Normal operations
    await fetch(`${BASE_URL}/api/products`);
    await sleep(randomBetween(500, 2000));

    await fetch(`${BASE_URL}/api/orders`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        user_id: `user-${Math.floor(Math.random() * 100)}`,
        items: [{ product_id: 1, qty: 1 }]
      })
    });
    await sleep(randomBetween(1000, 3000));

    // Health checks (frequent)
    await fetch(`${BASE_URL}/api/health`);
    await sleep(randomBetween(200, 500));
  }
}

function sleep(ms: number) {
  return new Promise(r => setTimeout(r, ms));
}

function randomBetween(min: number, max: number) {
  return Math.floor(Math.random() * (max - min) + min);
}

generateTraffic().catch(console.error);
```

### Log forwarding to InteliLog

The dummy app writes JSON logs to stdout. A sidecar process reads stdout and POSTs to InteliLog:

```typescript
// scripts/log-forwarder.ts
import { createInterface } from 'readline';

const INTELILOG_URL = process.env.INTELILOG_URL || 'http://localhost:3001/api/ingest';
const BATCH_SIZE = 10;
const FLUSH_INTERVAL = 2000;

let batch: any[] = [];

const rl = createInterface({ input: process.stdin });

rl.on('line', (line) => {
  try {
    const log = JSON.parse(line);
    batch.push(log);
    if (batch.length >= BATCH_SIZE) flush();
  } catch {
    // Not JSON, skip
  }
});

setInterval(flush, FLUSH_INTERVAL);

async function flush() {
  if (batch.length === 0) return;
  const logs = batch.splice(0);
  try {
    await fetch(INTELILOG_URL, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ source: 'dummy-ecommerce-api', logs })
    });
  } catch (err) {
    console.error('Failed to forward logs:', err);
  }
}
```

In Docker, pipe the app's stdout through the forwarder:

```dockerfile
CMD ["sh", "-c", "node server.js 2>&1 | node scripts/log-forwarder.js"]
```

---

## 2. Discord webhook integration

### Setup

Create a Discord webhook URL in a channel dedicated to InteliLog alerts.

### Formatting incident reports

```python
# integrations/discord.py
import os

import httpx

DISCORD_WEBHOOK_URL = os.environ["DISCORD_WEBHOOK_URL"]


async def send_incident_to_discord(incident: dict) -> None:
    severity_badge = {
        "critical": "[CRITICAL]",
        "high": "[HIGH]",
        "medium": "[MEDIUM]",
        "low": "[LOW]",
    }

    embed = {
        "title": f"{severity_badge.get(incident['incident']['severity'], '[UNKNOWN]')} Incident: {incident['incident']['severity'].upper()}",
        "description": incident["incident"]["report"],
        "color": {
            "critical": 0xFF0000,
            "high": 0xFF6600,
            "medium": 0xFFAA00,
            "low": 0x00CC00,
        }.get(incident["incident"]["severity"], 0x999999),
        "fields": [
            {
                "name": "Root cause",
                "value": incident["incident"].get("root_cause") or "Still investigating...",
                "inline": False,
            },
            {
                "name": "Source",
                "value": f"`{incident['source']}` at {incident['timestamp']}",
                "inline": True,
            },
            {
                "name": "Anomaly score",
                "value": f"{incident['pipeline']['anomaly_score']:.2f}",
                "inline": True,
            },
        ],
        "timestamp": incident["timestamp"],
    }

    # Add code references if present
    if incident["incident"].get("code_refs"):
        refs = "\n".join(
            f"`{ref['file']}:{ref['line']}` - {ref['blame_author']} ({ref['blame_date']})"
            for ref in incident["incident"]["code_refs"]
        )
        embed["fields"].append(
            {
                "name": "Code references",
                "value": refs,
                "inline": False,
            }
        )

    # Add suggested fix
    if incident["incident"].get("suggested_fix"):
        embed["fields"].append(
            {
                "name": "Suggested fix",
                "value": incident["incident"]["suggested_fix"],
                "inline": False,
            }
        )

    async with httpx.AsyncClient(timeout=15) as client:
        await client.post(DISCORD_WEBHOOK_URL, json={"embeds": [embed]})
```

### Wire it up

```python
from events.bus import pipeline


async def discord_listener() -> None:
    queue = pipeline.subscribe("incident:created")

    while True:
        log_event = await queue.get()
        try:
            await send_incident_to_discord(log_event)
        except Exception as err:
            print(f"Discord webhook failed: {err}")
```

---

## 3. Docker Compose setup

### docker-compose.yml

```yaml
version: '3.8'

services:
  # The InteliLog pipeline (Person 1 + Person 2)
  pipeline:
    build: ./pipeline
    ports:
      - "3001:3001"
    environment:
      - OPENROUTER_API_KEY=${OPENROUTER_API_KEY}
      - DISCORD_WEBHOOK_URL=${DISCORD_WEBHOOK_URL}
      - REPO_PATH=/repo
      - PYTHONUNBUFFERED=1
    volumes:
      - repo-data:/repo:ro
    networks:
      - intelilog
    depends_on:
      - repo-init

  # Agent container (isolated, restricted)
  # If agent runs in same process as pipeline, this is not needed.
  # Include if you want stricter isolation for the agent's file access.

  # Dummy e-commerce app
  dummy-app:
    build: ./dummy-app
    ports:
      - "3000:3000"
    environment:
      - INTELILOG_URL=http://pipeline:3001/api/ingest
    networks:
      - intelilog
    depends_on:
      - pipeline

  # Traffic generator (simulates users)
  traffic-gen:
    build:
      context: ./dummy-app
      dockerfile: Dockerfile.traffic
    environment:
      - DUMMY_APP_URL=http://dummy-app:3000
    networks:
      - intelilog
    depends_on:
      - dummy-app

  # Init container: clones the dummy app repo for agent access
  repo-init:
    image: alpine/git
    command: >
      sh -c "
        if [ ! -d /repo/.git ]; then
          git clone --depth 1 https://github.com/YOUR_TEAM/dummy-app.git /repo
        fi
      "
    volumes:
      - repo-data:/repo

volumes:
  repo-data:

networks:
  intelilog:
    driver: bridge
```

### Pipeline Dockerfile

```dockerfile
# pipeline/Dockerfile
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy pre-trained ML model
COPY models/ ./models/

COPY src/ ./src/

# Non-root user for security
RUN adduser --disabled-password --gecos "" intelilog
USER intelilog

EXPOSE 3001
CMD ["python", "-m", "uvicorn", "src.app:app", "--host", "0.0.0.0", "--port", "3001"]
```

### Dummy app Dockerfile

```dockerfile
# dummy-app/Dockerfile
FROM node:20-slim

WORKDIR /app
COPY package*.json ./
RUN npm ci --production
COPY . .
RUN npm run build

EXPOSE 3000
# Pipe stdout through the log forwarder
CMD ["sh", "-c", "node .next/standalone/server.js 2>&1 | node scripts/log-forwarder.js"]
```

### Agent security (applied to pipeline container)

If the agent tools run inside the pipeline container (simplest approach for hackathon), enforce restrictions via the volume mount:

- Repo volume is mounted **read-only** (`:ro`)
- Pipeline runs as non-root user `intelilog`
- The `subprocess.run(..., timeout=...)` calls in the agent executor prevent hangs
- No network access beyond what the pipeline needs (OpenRouter API)

For stricter isolation (stretch goal), run agent tools in a separate container with:
```yaml
agent:
  user: "1000:1000"
  read_only: true
  security_opt:
    - no-new-privileges:true
  cap_drop:
    - ALL
  volumes:
    - repo-data:/repo:ro
```

---

## 4. GCP deployment

### Option A: Compute Engine (simplest)

```bash
# Create a VM
gcloud compute instances create intelilog-demo \
  --zone=us-west1-b \
  --machine-type=e2-medium \
  --image-family=ubuntu-2404-lts-amd64 \
  --image-project=ubuntu-os-cloud \
  --boot-disk-size=30GB \
  --tags=http-server,https-server

# SSH in and set up
gcloud compute ssh intelilog-demo

# Install Docker
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER

# Clone the repo
git clone https://github.com/YOUR_TEAM/intelilog.git
cd intelilog

# Set environment variables
echo "OPENROUTER_API_KEY=your-key" >> .env
echo "DISCORD_WEBHOOK_URL=your-webhook" >> .env

# Launch
docker compose up -d
```

Open firewall rules for ports 3001 (pipeline API/WebSocket) and 3000 (dummy app, optional).

```bash
gcloud compute firewall-rules create intelilog-allow \
  --allow tcp:3001,tcp:3000 \
  --target-tags=http-server
```

### Option B: Cloud Run (stretch goal)

Cloud Run is trickier with Docker Compose (multiple services). If you go this route, deploy the pipeline as a Cloud Run service and the dummy app as another, with the repo volume as a mounted Cloud Storage bucket.

For the hackathon, Compute Engine is faster to get working.

### Dashboard (Vercel)

The dashboard deploys separately to Vercel. Set the environment variable:

```
NEXT_PUBLIC_WS_URL=ws://<GCP_EXTERNAL_IP>:3001/ws
```

---

## 5. Demo script

This is the most important deliverable for judging. Rehearse this multiple times.

### Pre-demo checklist

- [ ] Docker Compose stack running on GCP
- [ ] Dashboard live on Vercel, connected to WebSocket
- [ ] Discord channel open and visible
- [ ] Traffic generator running (healthy logs flowing)
- [ ] All chaos modes reset

### Demo sequence (5-7 minutes)

**[0:00] Introduction** (1 min)
"InteliLog is an AI-powered log intelligence pipeline. Traditional monitoring tells you something is wrong. InteliLog tells you what went wrong, why, and where in your code it happened."

**[1:00] Show healthy state** (1 min)
Dashboard visible. Logs streaming in. All green. Stats show logs being filtered (health checks) and scored low. "Right now the system is healthy. Our ML model scores every log, and the cascade is saving money by not sending anything to an LLM."

**[2:00] Trigger chaos** (30 sec)
```bash
curl -X POST http://<GCP_IP>:3000/api/chaos/db-leak
```
"We just triggered a database connection leak in our demo app."

**[2:30] Watch the cascade** (2 min)
Dashboard shows anomaly scores climbing. First warnings hit the cheap model. "Watch the triage - the cheap model is seeing elevated warnings but has not escalated yet." Then errors spike. High-anomaly logs go straight to the reasoning model. Agent activity feed lights up - "The AI is now investigating. It is reading the source code, checking git blame, searching for related errors."

**[4:30] Incident report arrives** (1 min)
Report appears on dashboard AND in Discord simultaneously. Walk through it: "Here is the root cause analysis. The AI found the exact file and line that caused the issue, who committed it, and is suggesting a fix."

**[5:30] Architecture walkthrough** (1-2 min)
Brief explanation of the tiered cascade, ML scoring, agent sandboxing. "The key insight is cost efficiency - 90% of logs never touch an LLM. Only the truly anomalous ones trigger an investigation."

**[6:30] Q&A**

### Backup plan

If the live demo fails, have screenshots and a screen recording ready. Record a successful run the night before as insurance.

```bash
# Record terminal session (optional)
asciinema rec demo.cast
```

---

## File structure

```
/
  docker-compose.yml
  .env.example
  /pipeline             # Person 1 + 2's Python/FastAPI code
  /dummy-app
    /app
      /api
        /products/route.ts
        /orders/route.ts
        /health/route.ts
        /chaos/[mode]/route.ts
    /lib
      logger.ts
      chaos.ts
    /scripts
      traffic.ts
      log-forwarder.ts
    Dockerfile
    Dockerfile.traffic
  /dashboard            # Person 3's code (deployed to Vercel separately)
```

---

## Coordination with other tracks

- **Person 1** needs your dummy app producing logs ASAP so they can train the ML model on healthy logs and test ingestion.
- **Person 2** needs the repo-init volume working so the agent can read the dummy app's source code.
- **Person 3** needs the GCP IP address and WebSocket port for the Vercel environment variable.
- You need everyone's Dockerfiles to build the compose stack.

Get the dummy app producing logs first - that unblocks Person 1 immediately.

---

## Priority order

1. Scaffold the dummy app with logger, products endpoint, and health check (45 min)
2. Add chaos endpoints (db-leak first, it is the best demo) (30 min)
3. Get the log forwarder working (30 min)
4. Set up Discord webhook and send a test message (30 min)
5. Write docker-compose.yml and get the stack running locally (1.5 hours)
6. Deploy to GCP Compute Engine (1 hour)
7. Write and test the traffic generator (30 min)
8. Write the demo script and rehearse (30 min)
9. Record backup demo video (remaining time)
