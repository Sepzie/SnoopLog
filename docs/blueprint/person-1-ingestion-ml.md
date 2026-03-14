# Person 1: Ingestion + ML Scoring + CLI

## SnoopLog | HackTheBreak 2026

---

## You own

Everything from raw log input to a scored log event, plus the CLI tool. You emit `log:scored` events that Person 2 and 3 consume.

## Deliverables

1. `POST /api/ingest` — accepts JSON logs, returns immediately
2. `POST /api/ingest/raw` — accepts plain text logs
3. Log parser — normalizes any format to shared Pydantic schema
4. Rule-based pre-filter — drops health checks, debug, static assets, k8s probes
5. ML scorer — IsolationForest via scikit-learn + heuristic fallback
6. CLI — `SnoopLog watch` and `SnoopLog init`
7. **Wire log buffer** — call `add_to_log_buffer()` after scoring so Person 2's `search_logs` tool works

---

## Ingestion flow

```
POST /api/ingest → parse → filter → score → emit("log:scored") → return 200
                                                ↓
                                    add_to_log_buffer()  ← IMPORTANT
```

The emit is **non-blocking** (via `asyncio.create_task` in the EventBus). The HTTP response returns immediately after scoring. The cascade runs in the background.

---

## Parser

Handle three input types:
- **Structured JSON dict** — extract timestamp/level/message/metadata directly
- **Text matching regex** — `TIMESTAMP LEVEL [SERVICE] MESSAGE`
- **Fallback** — entire line as message, level=unknown

---

## Pre-filter rules

| Rule | Match | Action |
|---|---|---|
| health-check | `/health`, `readiness`, `liveness` | drop |
| debug-level | level == debug | drop |
| static-assets | `.css`, `.js`, `.png`, etc. | drop |
| k8s-probes | `kube-probe`, `GoogleHC` | drop |

Filtered logs still get emitted (Person 3 needs them for stats) but marked `filtered=True`.

---

## ML scorer

**Training:** scikit-learn `IsolationForest`, serialized with `joblib`. Train on healthy logs from the dummy app.

**Features (8-dimensional vector):**
- Log level numeric (0-4)
- Message length
- New/unseen log template (binary)
- Error rate in last 60s
- Seconds since last error
- Shannon entropy of message
- Stack trace present (binary)
- Error burst count (last 5s)

**Heuristic fallback:** Works without a trained model. Scores based on level, message length, keywords (FATAL, ECONNREFUSED, traceback). This means the pipeline works from minute one while you train the real model later.

**Score normalization:** IsolationForest `score_samples()` returns negative values for anomalies. Normalize to 0.0 (normal) → 1.0 (anomalous). Assign tier: <0.3 low, 0.3-0.7 medium, >0.7 high.

---

## CLI tool

Built with `typer`. Two commands:

**`SnoopLog init`** — prompts for endpoint URL and app name, writes `.SnoopLog.yml`.

**`SnoopLog watch`** — reads stdin (or `--file`), batches logs, POSTs to `/api/ingest`. Prints compact summary showing high/medium counts. Handles connection failures silently (logging should never break the app).

```bash
# Usage
docker logs -f my-app | SnoopLog watch --endpoint https://SnoopLog.example.com --source my-app
tail -f /var/log/app.log | SnoopLog watch
```

**Note:** The CLI is shown in the demo as "how you'd integrate with your own app." The primary demo flow uses the Docker sidecar, not the CLI.

---

## Priority order

1. JSON ingestion endpoint + parser (45 min)
2. Wire event bus emission + log buffer (15 min)
3. Heuristic fallback scorer — end-to-end works immediately (30 min)
4. Pre-filters (30 min)
5. CLI `watch` command (1 hour)
6. Feature extraction (45 min)
7. Training script + train on dummy app logs (45 min)
8. Replace heuristic with real IsolationForest (30 min)
9. Raw text endpoint + CLI `init` (remaining time)
