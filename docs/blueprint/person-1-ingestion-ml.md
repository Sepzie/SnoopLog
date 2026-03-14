# Person 1: Ingestion + ML Scoring - Implementation Spec

## InteliLog | HackTheBreak 2026

---

## Your role

You own everything from raw log input to a scored log event. By the time a log leaves your system, it has been parsed into the shared JSON schema, passed through rule-based filters, and assigned an anomaly score between 0.0 and 1.0. You feed Person 2 (LLM cascade).

---

## Deliverables

1. **Log ingestion server** - HTTP endpoint that accepts logs in multiple formats
2. **Log parser** - normalizes raw logs into the shared JSON schema
3. **Rule-based pre-filter** - drops known noise before ML scoring
4. **ML anomaly scorer** - isolation forest model that scores each log
5. **Event bus publisher** - pushes scored logs to the internal pub/sub (for Person 2 and Person 3)

---

## 1. Log ingestion server

### HTTP endpoint

```
POST /api/ingest
Content-Type: application/json

{
  "source": "dummy-ecommerce-api",
  "logs": [
    {
      "timestamp": "2026-03-14T03:22:15.123Z",
      "level": "error",
      "message": "ECONNREFUSED - Connection refused to postgres:5432",
      "metadata": { "service": "order-service" }
    }
  ]
}
```

Also accept single log objects (not just arrays) for convenience.

### Stdin/pipe mode (stretch goal)

A lightweight CLI that tails a log file or accepts piped input:

```bash
tail -f /var/log/app.log | python -m intelilog_pipe --endpoint http://localhost:3001/api/ingest
```

For the hackathon, the dummy app will POST logs directly via HTTP, so this is a stretch goal.

### Raw text ingestion

Accept raw text logs (one per line) and attempt to parse them:

```
POST /api/ingest/raw
Content-Type: text/plain

2026-03-14T03:22:15.123Z ERROR [order-service] ECONNREFUSED...
2026-03-14T03:22:16.456Z INFO [health-check] OK
```

---

## 2. Log parser

Normalize incoming logs into the shared schema regardless of input format. Enforce the schema with Pydantic models before emitting to downstream systems.

### Parsing strategy

```python
import json
import re
import uuid
from datetime import datetime, timezone

from models import LogEvent, PipelineState

LOG_RE = re.compile(
    r"^(\d{4}-\d{2}-\d{2}T[\d:.]+Z?)\s+(DEBUG|INFO|WARN|ERROR|FATAL)\s+\[([^\]]+)\]\s+(.+)$"
)


def parse_log(raw: str | dict) -> LogEvent:
    # If already structured JSON with required fields, pass through
    if isinstance(raw, dict) and raw.get("timestamp") and raw.get("level") and raw.get("message"):
        return LogEvent(
            id=str(uuid.uuid4()),
            timestamp=raw["timestamp"],
            level=raw["level"].lower(),
            message=raw["message"],
            source=raw.get("source", raw.get("metadata", {}).get("service", "unknown")),
            raw=json.dumps(raw),
            metadata=raw.get("metadata", {}),
            pipeline=PipelineState(anomaly_score=None, tier=None, filtered=False, filter_reason=None),
        )

    text = raw if isinstance(raw, str) else json.dumps(raw)
    match = LOG_RE.match(text)

    if match:
        return LogEvent(
            id=str(uuid.uuid4()),
            timestamp=match.group(1),
            level=match.group(2).lower(),
            message=match.group(4),
            source=match.group(3),
            raw=text,
            metadata={},
            pipeline=PipelineState(anomaly_score=None, tier=None, filtered=False, filter_reason=None),
        )

    # Fallback: treat entire line as message
    return LogEvent(
        id=str(uuid.uuid4()),
        timestamp=datetime.now(timezone.utc).isoformat(),
        level="unknown",
        message=text,
        source="unknown",
        raw=text,
        metadata={},
        pipeline=PipelineState(anomaly_score=None, tier=None, filtered=False, filter_reason=None),
    )
```

---

## 3. Rule-based pre-filter

Before spending any compute on ML scoring, drop logs that are known noise.

### Default filter rules

```python
import re

FILTER_RULES = [
    {
        "name": "health-check",
        "match": lambda log: re.search(r"health[-_]?check|/health|readiness|liveness", log.message, re.I),
        "action": "drop",
    },
    {
        "name": "debug-level",
        "match": lambda log: log.level == "debug",
        "action": "drop",
    },
    {
        "name": "static-assets",
        "match": lambda log: re.search(r"\.(css|js|png|jpg|ico|svg|woff)", log.message, re.I),
        "action": "drop",
    },
    {
        "name": "kubernetes-probes",
        "match": lambda log: re.search(r"kube-probe|GoogleHC", log.message, re.I),
        "action": "drop",
    },
]
```

When a log is filtered, set `pipeline.filtered = true` and `pipeline.filter_reason = rule["name"]`. Still emit the event (Person 3 needs it for the dashboard stats) but mark it so Person 2 skips it.

---

## 4. ML anomaly scorer

### Architecture choice

Train and run inference directly in Python with scikit-learn `IsolationForest`.

### Feature extraction

Each log event is converted into a numeric feature vector before scoring:

```python
# Features extracted from each log + recent context window
features = [
    level_to_numeric(log.level),         # 0=debug, 1=info, 2=warn, 3=error, 4=fatal
    len(log.message),                    # Message length (unusual length = suspicious)
    1 if is_new_pattern(log.message) else 0,  # Never-before-seen log pattern
    error_rate_last_minute(),            # Rolling error count in last 60s
    time_since_last_error(),             # Seconds since previous error
    message_entropy(log.message),        # Shannon entropy of message text
    1 if stack_trace_present(log) else 0,  # Contains stack trace
    burst_detector(),                    # Rapid succession of same log pattern
]
```

#### Pattern tracking

Keep a rolling set of seen log "templates" (messages with numbers/IDs stripped out). A log whose template has never been seen before gets `is_new_pattern = 1`, which heavily influences the anomaly score.

```python
import re


def extract_template(message: str) -> str:
    template = re.sub(r"\b[0-9a-f]{8,}\b", "<ID>", message, flags=re.I)  # hex IDs
    template = re.sub(r"\b\d+\b", "<NUM>", template)  # numbers
    template = re.sub(r"\b\d{4}-\d{2}-\d{2}T[^\s]+", "<TS>", template)  # timestamps
    return template.strip()
```

### Training script (Python)

```python
# train_model.py - run once to generate the model artifact
import json
import joblib
import numpy as np
from sklearn.ensemble import IsolationForest

# Load healthy logs and extract features
with open("healthy_logs.json", "r", encoding="utf-8") as f:
    logs = json.load(f)

features = np.array([extract_features(log) for log in logs], dtype=np.float32)

# Train isolation forest
model = IsolationForest(
    n_estimators=100,
    contamination=0.05,  # Expect ~5% of "healthy" logs to look unusual
    random_state=42,
)
model.fit(features)

# Persist model for runtime scoring
joblib.dump(model, "anomaly_scorer.joblib")

# Save baseline config (feature means/stds + score range for normalization)
healthy_scores = model.score_samples(features)
config = {
    "feature_names": ["level", "msg_len", "new_pattern", "error_rate", "time_since_error", "entropy", "stack_trace", "burst"],
    "feature_means": features.mean(axis=0).tolist(),
    "feature_stds": features.std(axis=0).tolist(),
    "score_min": float(healthy_scores.min()),
    "score_max": float(healthy_scores.max()),
}
with open("baseline_config.json", "w", encoding="utf-8") as f:
    json.dump(config, f)
```

### Inference in Python

```python
import json
import joblib


class AnomalyScorer:
    def __init__(self, model_path: str, baseline_path: str):
        self.model = joblib.load(model_path)
        with open(baseline_path, "r", encoding="utf-8") as f:
            self.baseline = json.load(f)

    def score_log(self, features: list[float]) -> float:
        # IsolationForest score_samples: higher = more normal, lower = more anomalous
        raw_score = float(self.model.score_samples([features])[0])

        # Normalize to 0.0 (normal) to 1.0 (anomalous)
        lo = float(self.baseline["score_min"])
        hi = float(self.baseline["score_max"])
        if hi <= lo:
            return 0.0

        normalized = (hi - raw_score) / (hi - lo)
        return max(0.0, min(1.0, normalized))
```

### Tier assignment

```python
def assign_tier(score: float) -> str:
    if score < 0.3:
        return "low"
    if score <= 0.7:
        return "medium"
    return "high"
```

---

## 5. Event emitter

After scoring, emit the completed log event to an internal event bus. For the hackathon, use an in-process async pub/sub built on `asyncio` queues.

```python
import asyncio
from collections import defaultdict


class PipelineBus:
    def __init__(self):
        self._subscribers: dict[str, list[asyncio.Queue]] = defaultdict(list)

    def subscribe(self, topic: str) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=500)
        self._subscribers[topic].append(q)
        return q

    async def publish(self, topic: str, payload: dict) -> None:
        for queue in self._subscribers.get(topic, []):
            await queue.put(payload)


pipeline = PipelineBus()

# After scoring
log_event.pipeline.anomaly_score = score
log_event.pipeline.tier = assign_tier(score)
await pipeline.publish("log:scored", log_event.model_dump())

# Person 2 listens for non-filtered, non-low logs
# Person 3 listens for ALL logs (including filtered) for dashboard stats
```

If using separate processes/containers, replace the in-process bus with Redis pub/sub or a WebSocket broadcast service.

---

## File structure

```
/pipeline
  /src
    /ingestion
      main.py            # FastAPI endpoints for log ingestion
      parser.py          # Log parsing and normalization
      filters.py         # Rule-based pre-filter
      schemas.py         # Pydantic models for shared contract
    /scoring
      scorer.py          # scikit-learn inference wrapper
      features.py        # Feature extraction from logs
      patterns.py        # Template extraction and tracking
    /events
      bus.py             # Internal asyncio pub/sub
    app.py               # Main entry point, wires everything together
  /models
    anomaly_scorer.joblib  # Pre-trained model
    baseline_config.json   # Feature normalization config
  /training
    train_model.py       # Python training script
    generate_healthy.py  # Generate healthy logs from dummy app
  requirements.txt
  Dockerfile
```

---

## Testing strategy

### Unit tests

- Parser correctly handles structured JSON, raw text, and malformed input
- Filter rules match expected patterns
- Feature extraction produces correct dimensionality
- Scorer returns values in [0, 1] range

### Integration test

1. Start ingestion server
2. POST a batch of known-healthy logs -> all should score < 0.3
3. POST a batch of known-anomalous logs (error bursts, stack traces, new patterns) -> should score > 0.7
4. Verify events are emitted with correct schema

### Quick smoke test for demo

```bash
# Send a healthy log
curl -X POST http://localhost:3001/api/ingest \
  -H "Content-Type: application/json" \
  -d '{"source":"test","logs":[{"timestamp":"2026-03-14T10:00:00Z","level":"info","message":"GET /api/products 200 12ms"}]}'

# Send an anomalous log
curl -X POST http://localhost:3001/api/ingest \
  -H "Content-Type: application/json" \
  -d '{"source":"test","logs":[{"timestamp":"2026-03-14T10:00:01Z","level":"error","message":"FATAL: too many connections for role \"postgres\" - connection pool exhausted after 500 retries"}]}'
```

---

## Coordination with other tracks

- **Person 2** consumes your `log:scored` events for logs where `tier` is `medium` or `high`.
- **Person 3** consumes ALL events (including filtered/low) for dashboard stats.
- **Person 4** will POST logs from the dummy app to your ingestion endpoint.

Agree on the event bus mechanism (`asyncio` pub/sub, Redis, or WebSocket broadcast) with Person 2 early on.

---

## Priority order

1. Get the HTTP ingestion endpoint accepting JSON logs (30 min)
2. Get the parser normalizing to shared schema with Pydantic (30 min)
3. Wire up the internal event bus so Person 2 and 3 can start receiving data (15 min)
4. Implement rule-based filters (30 min)
5. Set up the scikit-learn scorer and load a dummy model (1 hour)
6. Write the Python training script and train on healthy logs from Person 4's dummy app (1 hour)
7. Integrate real scoring into the pipeline (30 min)
8. Polish feature extraction (remaining time)

