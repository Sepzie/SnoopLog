"""Feature extraction -- converts a LogEvent into an 8-dimensional dict for Half-Space Trees.

Features:
  level        - Log level numeric (0-4)
  msg_len      - Message length
  new_template - New/unseen log template (binary)
  err_rate_60s - Error count in last 60s
  secs_since_err - Seconds since last error (capped at 300)
  entropy      - Shannon entropy of message
  stack_trace  - Stack trace present (binary)
  err_burst_5s - Error burst count (last 5s)
"""

from __future__ import annotations

import math
import re
import time
from collections import Counter, deque

from shared.models import LogEvent

# --- Level mapping ---
_LEVEL_NUM = {"debug": 0, "info": 1, "warn": 2, "error": 3, "fatal": 4, "unknown": 2}

# --- Template tracking (normalize numbers/hex/uuids) ---
_TEMPLATE_RE = re.compile(r"\b[0-9a-f]{8,}\b|\b\d+\b", re.IGNORECASE)
_seen_templates: set[str] = set()

# --- Sliding windows for rate features ---
_error_timestamps: deque[float] = deque(maxlen=1000)

# --- Stack trace detection ---
_STACK_TRACE_RE = re.compile(r"(^\s+at\s+|Traceback|\.java:\d+|\.py.*line \d+|\.js:\d+)", re.MULTILINE)


def extract_features(event: LogEvent) -> dict[str, float]:
    """Extract 8 features from a LogEvent. Returns a dict for river."""
    now = time.time()
    msg = event.message

    # Level numeric
    level_num = _LEVEL_NUM.get(event.level.value, 2)

    # Message length
    msg_len = len(msg)

    # New/unseen template
    template = _TEMPLATE_RE.sub("<N>", msg)
    is_new_template = 1.0 if template not in _seen_templates else 0.0
    _seen_templates.add(template)

    # Error rate in last 60s
    cutoff_60 = now - 60
    while _error_timestamps and _error_timestamps[0] < cutoff_60:
        _error_timestamps.popleft()
    if event.level.value in ("error", "fatal"):
        _error_timestamps.append(now)
    error_rate_60s = sum(1 for t in _error_timestamps if t >= cutoff_60)

    # Seconds since last error (capped at 300)
    if _error_timestamps:
        secs_since_error = min(now - _error_timestamps[-1], 300.0)
    else:
        secs_since_error = 300.0

    # Shannon entropy
    entropy = _shannon_entropy(msg)

    # Stack trace present
    has_stack_trace = 1.0 if _STACK_TRACE_RE.search(msg) else 0.0

    # Error burst count (last 5s)
    cutoff_5 = now - 5
    burst_count = sum(1 for t in _error_timestamps if t >= cutoff_5)

    return {
        "level": float(level_num),
        "msg_len": float(msg_len),
        "new_template": is_new_template,
        "err_rate_60s": float(error_rate_60s),
        "secs_since_err": secs_since_error,
        "entropy": entropy,
        "stack_trace": has_stack_trace,
        "err_burst_5s": float(burst_count),
    }


def _shannon_entropy(text: str) -> float:
    """Calculate Shannon entropy of a string."""
    if not text:
        return 0.0
    counts = Counter(text)
    length = len(text)
    return -sum((c / length) * math.log2(c / length) for c in counts.values())


def reset_state():
    """Reset mutable state -- useful for testing."""
    _seen_templates.clear()
    _error_timestamps.clear()
