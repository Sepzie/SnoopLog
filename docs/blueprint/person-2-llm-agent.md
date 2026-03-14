# Person 2: LLM Cascade + Agent Framework - Implementation Spec

## InteliLog | HackTheBreak 2026

---

## Your role

You own the intelligence layer. You receive scored log events from Person 1 and decide what to do with them: send medium-anomaly logs through a cheap model for quick triage, and high-anomaly logs (or escalated medium logs) through a reasoning model with agent capabilities that can investigate the codebase. Your output is structured incident reports that Person 3 displays and Person 4 delivers.

This is the hardest track - the agent framework, prompt engineering, and routing logic are the core of what makes InteliLog novel.

---

## Deliverables

1. **Tier router** - routes scored logs to the correct LLM tier
2. **Cheap model triage** - fast yes/no escalation decision
3. **Reasoning model investigation** - deep analysis with agent tool use
4. **Agent framework** - lightweight tool-use loop for codebase exploration
5. **Report generator** - structures the agent's findings into an incident report

---

## 1. Tier router

Listen for scored events from Person 1 and route them:

```python
from events.bus import pipeline


async def consume_scored_logs() -> None:
    queue = pipeline.subscribe("log:scored")

    while True:
        log_event = await queue.get()

        if log_event["pipeline"]["filtered"]:
            continue  # Skip filtered logs

        tier = log_event["pipeline"]["tier"]

        if tier == "low":
            # Archive only - no LLM call
            await pipeline.publish("log:archived", log_event)
        elif tier == "medium":
            await add_to_batch(log_event)
        elif tier == "high":
            await investigate_reasoning_model(log_event)
```

### Log batching (important for cost)

Don't send every single medium log individually. Batch logs from the same source within a 30-second window and send them as a group to the cheap model. This dramatically reduces API calls.

```python
import asyncio

batch_buffer: dict[str, dict] = {}  # source -> {logs: [], flush_task: Task | None}


async def add_to_batch(log_event: dict) -> None:
    key = log_event["source"]
    if key not in batch_buffer:
        batch_buffer[key] = {"logs": [], "flush_task": None}

    batch = batch_buffer[key]
    batch["logs"].append(log_event)

    # Flush after 30s or 20 logs, whichever comes first
    if len(batch["logs"]) >= 20:
        await flush_batch(key)
    elif batch["flush_task"] is None:
        batch["flush_task"] = asyncio.create_task(_flush_later(key, 30))


async def _flush_later(key: str, delay_seconds: int) -> None:
    await asyncio.sleep(delay_seconds)
    await flush_batch(key)


async def flush_batch(key: str) -> None:
    batch = batch_buffer.get(key)
    if not batch or not batch["logs"]:
        return

    logs = batch["logs"][:]
    batch["logs"].clear()

    task = batch.get("flush_task")
    if task and not task.done():
        task.cancel()
    batch["flush_task"] = None

    await triage_cheap_model(logs)
```

For high-tier logs, send immediately - no batching.

---

## 2. Cheap model triage

Use a fast, cheap model (Gemini Flash or Haiku via OpenRouter) to make a quick escalation decision.

### OpenRouter API call

```python
import json
import os

import httpx

from events.bus import pipeline

OPENROUTER_API_KEY = os.environ["OPENROUTER_API_KEY"]
CHEAP_MODEL = "google/gemini-flash-1.5"  # or "anthropic/claude-3-haiku"


async def triage_cheap_model(log_events: list[dict] | dict) -> None:
    logs = log_events if isinstance(log_events, list) else [log_events]

    payload = {
        "model": CHEAP_MODEL,
        "messages": [
            {"role": "system", "content": TRIAGE_SYSTEM_PROMPT},
            {"role": "user", "content": format_logs_for_triage(logs)},
        ],
        "response_format": {"type": "json_object"},
        "max_tokens": 300,
    }

    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json",
            },
            json=payload,
        )
        response.raise_for_status()

    data = response.json()
    decision = json.loads(data["choices"][0]["message"]["content"])

    if decision.get("escalate"):
        # Forward to reasoning model with context from cheap model
        for log in logs:
            log["pipeline"]["tier_model"] = CHEAP_MODEL
            await investigate_reasoning_model(log, decision.get("reason"))
    else:
        # Log the triage decision and move on
        for log in logs:
            log["pipeline"]["tier_model"] = CHEAP_MODEL
            await pipeline.publish("log:triaged", {**log, "triage": decision})
```

### Triage system prompt

```python
TRIAGE_SYSTEM_PROMPT = """You are a log triage system. You receive application logs that have been flagged as potentially anomalous by an ML model.

Your job is to quickly decide: should this be escalated to a detailed investigation, or is it a false alarm?

Respond ONLY with JSON in this exact format:
{
  "escalate": true or false,
  "reason": "One sentence explaining your decision",
  "urgency": "low", "medium", or "high"
}

Escalate if you see:
- Database connection errors or pool exhaustion
- Memory/resource exhaustion indicators
- Authentication/authorization failures in unusual patterns
- Stack traces indicating unhandled exceptions
- Error rates that suggest cascading failures
- Any pattern that could indicate data loss or corruption

Do NOT escalate:
- Single transient errors (one timeout, one 404)
- Expected errors (rate limiting, validation failures)
- Informational warnings with no impact
- Logs that look like normal operation noise"""
```

---

## 3. Reasoning model investigation

This is where the real magic happens. The reasoning model gets the anomalous log(s), context, and access to agent tools.

### Investigation loop

```python
import json
import time

import httpx

from events.bus import pipeline

REASONING_MODEL = "anthropic/claude-sonnet-4"  # or "openai/gpt-4o"


async def investigate_reasoning_model(log_event: dict, triage_context: str | None = None) -> None:
    messages = [
        {"role": "system", "content": INVESTIGATION_SYSTEM_PROMPT},
        {"role": "user", "content": format_log_for_investigation(log_event, triage_context)},
    ]

    tools = get_agent_tools()
    iteration = 0
    max_iterations = 10
    timeout_seconds = 60
    started = time.time()

    async with httpx.AsyncClient(timeout=60) as client:
        while iteration < max_iterations and (time.time() - started) < timeout_seconds:
            response = await client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": REASONING_MODEL,
                    "messages": messages,
                    "tools": tools,
                    "max_tokens": 2000,
                },
            )
            response.raise_for_status()

            data = response.json()
            choice = data["choices"][0]
            message = choice["message"]

            # If the model wants to use tools
            if choice.get("finish_reason") == "tool_calls" or message.get("tool_calls"):
                messages.append(message)

                for tool_call in message.get("tool_calls", []):
                    result = await execute_agent_tool(tool_call)
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tool_call["id"],
                            "content": result,
                        }
                    )

                    # Emit for dashboard (Person 3 can show agent reasoning in real-time)
                    await pipeline.publish(
                        "agent:tool_call",
                        {
                            "logId": log_event["id"],
                            "tool": tool_call["function"]["name"],
                            "args": json.loads(tool_call["function"]["arguments"]),
                            "result": result[:500],  # Truncate for dashboard
                        },
                    )

                iteration += 1
                continue

            # Model is done investigating - parse the report
            report = parse_investigation_report(message.get("content", ""))
            log_event["incident"] = report
            await pipeline.publish("incident:created", log_event)
            return

    # Timeout or max iterations - emit partial report
    log_event["incident"] = {
        "report": "Investigation timed out or reached max iterations",
        "severity": "unknown",
        "root_cause": None,
        "code_refs": [],
        "suggested_fix": None,
    }
    await pipeline.publish("incident:created", log_event)
```

### Investigation system prompt

```python
INVESTIGATION_SYSTEM_PROMPT = """You are an expert SRE investigating a production incident. You have access to tools that let you explore the application's source code.

Your goal: determine the root cause of the anomalous log event and produce a clear incident report.

Investigation strategy:
1. Read the log message carefully. Identify keywords, service names, file paths, error codes.
2. Use grep_code to search for relevant patterns in the codebase.
3. Use read_file to examine suspicious files.
4. Use git_blame to check recent changes to those files.
5. Use search_logs to find related log entries around the same time.

When you have enough evidence, write your final report in this JSON format:
{
  "report": "2-3 sentence summary of what happened",
  "root_cause": "The specific cause, with evidence",
  "severity": "low" | "medium" | "high" | "critical",
  "code_refs": [
    {
      "file": "path/to/file.ts",
      "line": 42,
      "blame_author": "author name",
      "blame_date": "2026-03-13",
      "blame_commit": "abc1234"
    }
  ],
  "suggested_fix": "Specific actionable recommendation"
}

Be concise. Developers will read this at 3 AM. Lead with what matters."""
```

---

## 4. Agent framework - tool definitions

### Tool definitions (OpenAI function calling format, used by OpenRouter)

```python
def get_agent_tools() -> list[dict]:
    return [
        {
            "type": "function",
            "function": {
                "name": "read_file",
                "description": "Read the contents of a file from the application source code. Returns the file content with line numbers.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "File path relative to the repo root (e.g., 'src/db/pool.ts')",
                        },
                        "start_line": {
                            "type": "integer",
                            "description": "Optional: start reading from this line number",
                        },
                        "end_line": {
                            "type": "integer",
                            "description": "Optional: stop reading at this line number",
                        },
                    },
                    "required": ["path"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "grep_code",
                "description": "Search for a pattern in the codebase. Returns matching lines with file paths and line numbers.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "pattern": {
                            "type": "string",
                            "description": "Search pattern (supports regex)",
                        },
                        "file_glob": {
                            "type": "string",
                            "description": "Optional: restrict search to files matching this glob (e.g., '*.py', 'src/**/*.ts')",
                        },
                    },
                    "required": ["pattern"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "git_blame",
                "description": "Show git blame for a file, revealing who changed each line and when.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "File path relative to repo root",
                        },
                        "start_line": {"type": "integer", "description": "Optional: start line"},
                        "end_line": {"type": "integer", "description": "Optional: end line"},
                    },
                    "required": ["path"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "git_log",
                "description": "Show recent git commits, optionally filtered to a specific file.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Optional: file path to filter commits",
                        },
                        "n": {
                            "type": "integer",
                            "description": "Number of recent commits to show (default 10)",
                        },
                    },
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "list_files",
                "description": "List files and directories in the codebase.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Directory path relative to repo root (default: root)",
                        },
                    },
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "search_logs",
                "description": "Search recent logs for a pattern. Useful for finding related errors around the same time.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "pattern": {
                            "type": "string",
                            "description": "Search pattern to match against log messages",
                        },
                        "minutes": {
                            "type": "integer",
                            "description": "How many minutes back to search (default: 5)",
                        },
                    },
                    "required": ["pattern"],
                },
            },
        },
    ]
```

### Tool execution

All tools run against the mounted repo volume (`/repo`) with strict sandboxing.

```python
import json
import os
import subprocess
from pathlib import Path

REPO_PATH = Path(os.environ.get("REPO_PATH", "/repo")).resolve()
MAX_OUTPUT = 5000  # Truncate tool output to keep context manageable


def sanitize_path(input_path: str) -> Path:
    # SECURITY: Prevent path traversal
    resolved = (REPO_PATH / input_path).resolve()
    if not str(resolved).startswith(str(REPO_PATH)):
        raise ValueError("Path traversal detected")
    return resolved


async def execute_agent_tool(tool_call: dict) -> str:
    name = tool_call["function"]["name"]
    args = json.loads(tool_call["function"]["arguments"])

    try:
        if name == "read_file":
            file_path = sanitize_path(args["path"])
            content = file_path.read_text(encoding="utf-8")
            lines = content.splitlines()
            start = max(1, int(args.get("start_line", 1)))
            end = int(args.get("end_line", len(lines)))
            numbered = "\n".join(f"{i + 1}: {line}" for i, line in enumerate(lines[start - 1:end], start - 1))
            return truncate(numbered)

        if name == "grep_code":
            pattern = args["pattern"]
            file_glob = args.get("file_glob")
            command = ["rg", "-n", "--hidden", "--glob", "!.git", pattern, str(REPO_PATH)]
            if file_glob:
                command.extend(["-g", file_glob])
            result = subprocess.run(command, capture_output=True, text=True, timeout=10, check=False)
            output = result.stdout or ""
            return truncate(output.replace(str(REPO_PATH) + "/", "").replace(str(REPO_PATH) + "\\", ""))

        if name == "git_blame":
            file_path = sanitize_path(args["path"])
            command = ["git", "-C", str(REPO_PATH), "blame", "--date=short"]
            if args.get("start_line") and args.get("end_line"):
                command.extend(["-L", f"{args['start_line']},{args['end_line']}"])
            command.append(str(file_path))
            result = subprocess.run(command, capture_output=True, text=True, timeout=10, check=False)
            return truncate(result.stdout)

        if name == "git_log":
            n = int(args.get("n", 10))
            command = [
                "git", "-C", str(REPO_PATH), "log", "--oneline", "--date=short",
                "--format=%h %ad %an %s", "-n", str(n),
            ]
            if args.get("path"):
                command.extend(["--", args["path"]])
            result = subprocess.run(command, capture_output=True, text=True, timeout=10, check=False)
            return truncate(result.stdout)

        if name == "list_files":
            rel_path = args.get("path", ".")
            dir_path = sanitize_path(rel_path)
            command = [
                "rg", "--files", str(dir_path),
                "-g", "!.git", "-g", "!venv", "-g", "!__pycache__",
            ]
            result = subprocess.run(command, capture_output=True, text=True, timeout=5, check=False)
            lines = (result.stdout or "").splitlines()[:50]
            return truncate("\n".join(lines).replace(str(REPO_PATH) + "/", "").replace(str(REPO_PATH) + "\\", ""))

        if name == "search_logs":
            # Search the in-memory log buffer (maintained by Person 1)
            minutes = int(args.get("minutes", 5))
            since_ms = current_time_ms() - (minutes * 60 * 1000)
            matches = [
                entry for entry in log_buffer
                if parse_iso_ts(entry["timestamp"]) > since_ms
                and (args["pattern"] in entry["message"] or args["pattern"] in entry["raw"])
            ][-20:]  # Last 20 matches
            return truncate(json.dumps(matches, indent=2))

        return f"Unknown tool: {name}"

    except Exception as err:
        return f"Tool error: {err}"


def truncate(text: str) -> str:
    return text[:MAX_OUTPUT] + "\n... (truncated)" if len(text) > MAX_OUTPUT else text
```

---

## 5. Report generator

Parse the model's final response into the structured incident report format.

```python
import json


def parse_investigation_report(content: str) -> dict:
    try:
        # Try to parse as JSON directly
        data = json.loads(content)
        return {
            "report": data.get("report", content),
            "root_cause": data.get("root_cause"),
            "severity": data.get("severity", "unknown"),
            "code_refs": data.get("code_refs", []),
            "suggested_fix": data.get("suggested_fix"),
        }
    except Exception:
        # If not valid JSON, extract what we can
        return {
            "report": content,
            "root_cause": None,
            "severity": "unknown",
            "code_refs": [],
            "suggested_fix": None,
        }
```

---

## File structure

```
/pipeline
  /src
    /cascade
      router.py           # Tier routing logic
      batcher.py          # Log batching for cheap model
      triage.py           # Cheap model triage
      investigator.py     # Reasoning model investigation loop
    /agent
      tools.py            # Tool definitions
      executor.py         # Tool execution (sandboxed)
      prompts.py          # System prompts for both tiers
    /reports
      parser.py           # Parse model output into incident report
```

---

## Coordination with other tracks

- **Person 1** emits `log:scored` events. Subscribe to these.
- **Person 3** listens for `agent:tool_call` (real-time agent reasoning) and `incident:created` (final reports).
- **Person 4** provides the repo volume and the Discord webhook format.

You need Person 1's event bus working to start receiving real data, but you can develop and test against hardcoded log events independently.

---

## Testing strategy

### Test with hardcoded events first

Don't wait for Person 1. Create test fixtures:

```python
test_events = {
    "healthy_log": {
        "id": "test-1",
        "level": "info",
        "message": "GET /api/products 200 12ms",
        "pipeline": {"anomaly_score": 0.1, "tier": "low"},
    },
    "suspicious_log": {
        "id": "test-2",
        "level": "warn",
        "message": "Connection pool at 90% capacity",
        "pipeline": {"anomaly_score": 0.5, "tier": "medium"},
    },
    "critical_log": {
        "id": "test-3",
        "level": "error",
        "message": "FATAL: too many connections for role \"postgres\"",
        "pipeline": {"anomaly_score": 0.9, "tier": "high"},
    },
}
```

### Test the agent against the dummy app repo

Once Person 4 has the dummy app repo, clone it locally and point `REPO_PATH` at it. Trigger a fake critical log and verify the agent can find the relevant code.

---

## Priority order

1. Set up OpenRouter API calls with `httpx.AsyncClient`, verify you can hit both cheap and expensive models (30 min)
2. Implement tier router with event listener (30 min)
3. Write the triage system prompt and cheap model call (45 min)
4. Build the agent tool definitions and executor (1.5 hours)
5. Write the investigation system prompt (45 min)
6. Implement the investigation loop with tool use (1.5 hours)
7. Report parsing and event emission (30 min)
8. Test end-to-end against dummy app repo (remaining time)
