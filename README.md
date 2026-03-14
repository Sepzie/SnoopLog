# SnoopLog

AI log intelligence pipeline: ingest logs → ML anomaly scoring → tiered LLM cascade → agent investigates your codebase → incident report delivered to Discord.

**HackTheBreak 2026 | March 13-15**

## Team

- Clayton Hunter
- Madhav Ramdev
- Sepehr Zohoori Rad
- Fonse Clarito

## Quick Start (Local Dev)

### Prerequisites

- Python 3.12+
- Node.js 20+
- Docker (for full stack)

### Pipeline (FastAPI backend)

```bash
# Create and activate virtual environment
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS/Linux
source .venv/bin/activate

# Install dependencies
pip install -r pipeline/requirements.txt

# Run the pipeline
uvicorn pipeline.main:app --host 0.0.0.0 --port 3001 --reload
```

Test it:

```bash
# Health check
curl http://localhost:3001/health

# Send a test log
curl -X POST http://localhost:3001/api/ingest \
  -H "Content-Type: application/json" \
  -d '{"level": "error", "message": "FATAL: too many connections for role postgres", "source": "dummy-app"}'
```

### Dummy App (Node.js)

```bash
cd dummy-app
npm install
node server.js
# Runs on http://localhost:3000
```

### Full Stack (Docker Compose)

```bash
# Copy and fill in env vars
cp .env.example .env

# Start everything
docker compose up --build
```

This starts all 7 services: Caddy (TLS proxy), pipeline, dummy-app, log-forwarder, traffic-gen, repo-init, repo-sync.

## Project Structure

```
shared/              Pydantic models, event bus, log buffer (shared contract)
pipeline/            FastAPI backend — ingestion, ML scoring, LLM cascade, agent
  ingestion/         Log parsing, filtering, scoring (Person 1)
  ml/                IsolationForest anomaly scorer (Person 1)
  llm/               Tier routing, triage, investigation (Person 2)
  agent/             Agent tools: read_file, grep, git_blame, etc. (Person 2)
  integrations/      Discord webhook (Person 4)
dashboard/           Next.js frontend on Vercel (Person 3)
dummy-app/           Next.js e-commerce app with chaos modes (Person 4)
log-forwarder/       Sidecar: tails logs → POSTs to pipeline (Person 4)
traffic-gen/         Simulated user traffic (Person 4)
cli/                 SnoopLog CLI tool (Person 1)
docs/blueprint/      PRD, diagrams, per-person specs
```

## Architecture

```
Log sources → Ingestion (FastAPI) → Pre-filter → ML scorer (IsolationForest)
                                                        ↓
                                                  Tier routing:
                                              <0.3: archive
                                            0.3-0.7: cheap model (Flash/Haiku)
                                              >0.7: reasoning model (Sonnet/GPT-4o)
                                                        ↓
                                                  Agent framework
                                                (read_file, grep, git_blame)
                                                        ↓
                                              Incident report → Discord + Dashboard
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check |
| POST | `/api/ingest` | Ingest JSON logs |
| POST | `/api/ingest/raw` | Ingest plain-text logs |
| WS | `/ws` | WebSocket for real-time events |


## Environment Variables

See [.env.example](.env.example) for all required variables.
