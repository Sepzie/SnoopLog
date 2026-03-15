"""Central config loader for SnoopLog.

Reads snooplog.yaml from the project root and exposes typed accessors.
The YAML file holds only high-level, user-facing settings (volume, sensitivity,
filters, snapshots).  All internal pipeline parameters live here as defaults.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

# Walk up from shared/ to find project root
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_CONFIG_PATH = _PROJECT_ROOT / "snooplog.yaml"

# ── Volume presets ────────────────────────────────────────────
# Maps the user-facing "volume" knob to an ML window_size.
_VOLUME_PRESETS: dict[str, int] = {
    "small": 5_000,
    "medium": 25_000,
    "large": 100_000,
}
_DEFAULT_VOLUME = "small"


def _load_raw() -> dict[str, Any]:
    """Load the raw YAML config dict. Returns empty dict if file missing."""
    if _CONFIG_PATH.exists():
        return yaml.safe_load(_CONFIG_PATH.read_text()) or {}
    return {}


@lru_cache(maxsize=1)
def get_config() -> dict[str, Any]:
    """Return the full config dict (cached after first call)."""
    return _load_raw()


def reload_config() -> dict[str, Any]:
    """Force-reload config from disk (clears cache)."""
    get_config.cache_clear()
    return get_config()


# ── Helpers ───────────────────────────────────────────────────

def _section(name: str) -> dict[str, Any]:
    return get_config().get(name, {}) or {}


# ── ML (internal defaults, window_size driven by volume preset) ──

def ml_n_trees() -> int:
    return 25

def ml_tree_height() -> int:
    return 6

def ml_window_size() -> int:
    volume = get_config().get("volume", _DEFAULT_VOLUME)
    return _VOLUME_PRESETS.get(volume, _VOLUME_PRESETS[_DEFAULT_VOLUME])

def ml_max_weight() -> float:
    return 0.4

def ml_snapshot_interval() -> int:
    return 1000


# ── Snapshots (backend + bucket from YAML, rest internal) ────

def snapshot_backend() -> str:
    return _section("snapshots").get("backend", "local")

def snapshot_local_dir() -> str:
    return "/data/snapshots"

def snapshot_gcs_bucket() -> str:
    return _section("snapshots").get("gcs_bucket", "")

def snapshot_gcs_prefix() -> str:
    return "snapshots"


# ── Features (internal defaults) ─────────────────────────────

def feat_error_window_maxlen() -> int:
    return 1000

def feat_secs_since_error_cap() -> float:
    return 300.0

def feat_error_burst_window() -> int:
    return 5


# ── Scoring (internal defaults) ──────────────────────────────

_LEVEL_BASE = {"fatal": 0.85, "error": 0.55, "warn": 0.25, "info": 0.05, "debug": 0.02, "unknown": 0.15}
_BOOSTS = {"critical_keywords": 0.25, "error_keywords": 0.15, "warn_keywords": 0.10, "stack_trace": 0.10, "long_message": 0.05}

def scoring_level_base() -> dict[str, float]:
    return _LEVEL_BASE

def scoring_boosts() -> dict[str, float]:
    return _BOOSTS

def scoring_long_message_threshold() -> int:
    return 200


# ── Tiers (from YAML "sensitivity" section) ──────────────────

def tier_high() -> float:
    return _section("sensitivity").get("high", 0.7)

def tier_medium() -> float:
    return _section("sensitivity").get("medium", 0.3)


# ── Filters (from YAML) ──────────────────────────────────────

def filter_debug_level() -> bool:
    return _section("filters").get("debug_level", True)

def filter_health_checks() -> bool:
    return _section("filters").get("health_checks", True)

def filter_static_assets() -> bool:
    return _section("filters").get("static_assets", True)

def filter_k8s_probes() -> bool:
    return _section("filters").get("k8s_probes", True)


# ── Buffer (internal default) ────────────────────────────────

def buffer_max_size() -> int:
    return 5000


# ── CLI (internal defaults) ──────────────────────────────────

def cli_default_endpoint() -> str:
    return "http://localhost:3001"

def cli_batch_size() -> int:
    return 50

def cli_flush_interval() -> float:
    return 2.0

def cli_http_timeout() -> int:
    return 5
