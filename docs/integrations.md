# SnoopLog Integrations

How to connect your app's logs to the SnoopLog pipeline.

---

## API Endpoints

The pipeline exposes two ingestion endpoints:

| Endpoint | Content-Type | Input |
|---|---|---|
| `POST /api/ingest` | `application/json` | Single JSON object or array of objects |
| `POST /api/ingest/raw` | `text/plain` | One log line per line |

**Response** (both endpoints):
```json
{
  "accepted": 3,
  "results": [
    {"id": "abc123...", "score": 0.72, "filtered": false},
    {"id": "def456...", "score": 0.05, "filtered": false},
    {"id": "ghi789...", "score": 0.00, "filtered": true}
  ]
}
```

**Structured JSON format** (recommended):
```json
{
  "timestamp": "2026-03-14T10:00:00.000Z",
  "level": "error",
  "service": "my-app",
  "message": "Connection refused to database",
  "metadata": {
    "host": "db-primary",
    "port": 5432
  }
}
```

The parser also handles plain text matching `TIMESTAMP LEVEL [SERVICE] MESSAGE`, and falls back to treating the entire line as the message with `level=unknown`.

---

## 1. CLI (`snooplog watch`)

Pipe logs from any source into the pipeline. Handles batching, retries, and connection failures gracefully.

### Setup

```bash
# One-time: create a config file
python -m pipeline.cli init
# Prompts for endpoint URL and app name, writes .snooplog.yml
```

### Usage

```bash
# Pipe from docker logs
docker logs -f my-app | python -m pipeline.cli watch

# Pipe from a log file
tail -f /var/log/app.log | python -m pipeline.cli watch

# Override config with flags
python -m pipeline.cli watch --endpoint http://snooplog.example.com:3001 --source my-app

# Tail a file directly (starts from end, follows new lines)
python -m pipeline.cli watch --file /var/log/app.log

# Send as raw text instead of JSON
cat /var/log/syslog | python -m pipeline.cli watch --raw
```

### How it works

1. Reads lines from stdin (or `--file`)
2. Tries to parse each line as JSON; if it fails, wraps it as `{"source": "...", "message": "...", "level": "info"}`
3. Batches up to 50 logs or flushes every 2 seconds (whichever comes first)
4. POSTs to `/api/ingest` (or `/api/ingest/raw` with `--raw`)
5. Prints a compact status line: `^ 50 logs | total: 200 | ! 3 high, 12 medium`
6. Connection failures are logged to stderr but never crash your app

### Config file (`.snooplog.yml`)

```yaml
endpoint: http://localhost:3001
source: my-app
```

---

## 2. Docker Sidecar (log-forwarder)

For containerized apps. The log-forwarder container tails a shared log file and forwards to the pipeline. No code changes needed in your app.

### How it works

Your app writes logs to a file. The forwarder container mounts the same volume, tails the file, and POSTs batches to the pipeline.

### docker-compose.yml

```yaml
services:
  my-app:
    build: ./my-app
    volumes:
      - app-logs:/app/logs    # your app writes here

  log-forwarder:
    build: ./log-forwarder
    environment:
      - PIPELINE_URL=http://pipeline:3001/api/ingest
      - LOG_FILE=/logs/app.log
      - SOURCE=my-app
      - BATCH_SIZE=10
      - FLUSH_INTERVAL=2.0
    volumes:
      - app-logs:/logs:ro     # reads from same volume
    depends_on:
      - pipeline

volumes:
  app-logs:
```

### Environment variables

| Variable | Default | Description |
|---|---|---|
| `PIPELINE_URL` | `http://pipeline:3001/api/ingest` | Pipeline ingestion endpoint |
| `LOG_FILE` | `/logs/app.log` | Path to the log file to tail |
| `SOURCE` | `dummy-app` | Source name attached to each log |
| `BATCH_SIZE` | `10` | Max logs per batch |
| `FLUSH_INTERVAL` | `2.0` | Max seconds between flushes |

---

## 3. Direct HTTP (webhook / curl)

POST logs directly from your app or CI/CD pipeline. No agent needed.

### Single log

```bash
curl -X POST http://localhost:3001/api/ingest \
  -H "Content-Type: application/json" \
  -d '{
    "level": "error",
    "service": "deploy-bot",
    "message": "Deployment failed: timeout waiting for health check",
    "metadata": {"env": "production", "commit": "abc123"}
  }'
```

### Batch of logs

```bash
curl -X POST http://localhost:3001/api/ingest \
  -H "Content-Type: application/json" \
  -d '[
    {"level": "info", "service": "my-app", "message": "Server started"},
    {"level": "error", "service": "my-app", "message": "DB connection failed"}
  ]'
```

### Raw text

```bash
curl -X POST http://localhost:3001/api/ingest/raw \
  -H "Content-Type: text/plain" \
  -d '2026-03-14T10:00:00Z ERROR [my-app] Connection refused
2026-03-14T10:00:01Z INFO [my-app] Retrying in 5s'
```

### From a script (Python)

```python
import httpx

logs = [
    {"level": "error", "service": "my-app", "message": "Something broke"},
    {"level": "info", "service": "my-app", "message": "Recovered"},
]

resp = httpx.post("http://localhost:3001/api/ingest", json=logs)
print(resp.json())
# {"accepted": 2, "results": [{"id": "...", "score": 0.7, "filtered": false}, ...]}
```

### From a script (Node.js)

```javascript
const resp = await fetch("http://localhost:3001/api/ingest", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify([
    { level: "error", service: "my-app", message: "Unhandled exception" },
  ]),
});
const data = await resp.json();
console.log(data);
```

---

## 4. Test Corpus

A pre-built set of 30 logs for testing the full pipeline without a running app.

```bash
# Start the pipeline
python -m uvicorn pipeline.main:app --port 3001

# In another terminal, send the test corpus
python tests/send_test_logs.py
# or specify a custom endpoint
python tests/send_test_logs.py http://snooplog.example.com:3001
```

The corpus (`tests/test_logs.jsonl`) covers: normal info, debug noise, health checks, static assets, k8s probes, warnings (slow queries, connection pools), errors (connection refused, stack traces, OOM), and fatal crashes.

---

## What gets filtered

These logs are still accepted and emitted to the dashboard (for stats), but scored at 0.0 and marked `filtered: true`:

| Rule | Example |
|---|---|
| Debug level | `SQL query executed in 12ms` |
| Health checks | `GET /health 200 1ms`, `readiness probe succeeded` |
| Static assets | `GET /static/style.css 200 2ms` |
| k8s probes | `kube-probe/1.28`, `GoogleHC/1.0` |

---

## Scoring tiers

Every non-filtered log gets an anomaly score (0.0 normal to 1.0 anomalous) and a tier:

| Tier | Score | What happens |
|---|---|---|
| LOW | < 0.3 | Archived, no LLM call |
| MEDIUM | 0.3 - 0.7 | Sent to cheap model (Flash/Haiku) |
| HIGH | > 0.7 | Sent to reasoning model (Sonnet/GPT-4o) |
