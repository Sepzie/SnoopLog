"""Half-Space Trees streaming anomaly scorer.

Uses river's HalfSpaceTrees -- an online variant of IsolationForest that
learns from every log event. No offline training step needed.

The model starts empty and ramps up its influence via a dynamic blend weight.
"""

from __future__ import annotations

import logging

from river.anomaly import HalfSpaceTrees

from shared.models import LogEvent

from .features import extract_features

logger = logging.getLogger("snooplog.ml")

# HST config
N_TREES = 25
TREE_HEIGHT = 6
WINDOW_SIZE = 10_000  # sliding window -- controls how fast it forgets

# Feature space boundaries -- HST needs these to partition effectively
FEATURE_LIMITS = {
    "level": (0, 4),            # debug=0 to fatal=4
    "msg_len": (0, 2000),       # typical log messages
    "new_template": (0, 1),     # binary
    "err_rate_60s": (0, 100),   # errors in last 60s
    "secs_since_err": (0, 300), # capped at 300
    "entropy": (0, 6),          # Shannon entropy range for text
    "stack_trace": (0, 1),      # binary
    "err_burst_5s": (0, 50),    # errors in last 5s
}


class AnomalyScorer:
    """Streaming anomaly scorer using Half-Space Trees."""

    def __init__(self, window_size: int = WINDOW_SIZE):
        self._window_size = window_size
        self._model = HalfSpaceTrees(
            n_trees=N_TREES,
            height=TREE_HEIGHT,
            window_size=window_size,
            limits=FEATURE_LIMITS,
            seed=42,
        )
        self._logs_seen: int = 0

    @property
    def logs_seen(self) -> int:
        return self._logs_seen

    @property
    def ml_weight(self) -> float:
        """Dynamic blend weight -- ramps from 0 to 0.4 over first window_size logs."""
        return min(0.4, self._logs_seen / self._window_size * 0.4)

    def score(self, event: LogEvent) -> float:
        """Score a log event and learn from it.

        Returns 0.0 (normal) to 1.0 (anomalous).
        """
        features = extract_features(event)

        # Score first, then learn (so we score against the existing baseline)
        raw = self._model.score_one(features)
        self._model.learn_one(features)
        self._logs_seen += 1

        # river's score_one returns 0.0 (normal) to 1.0 (anomalous) already
        return round(raw, 3)


# Singleton
scorer = AnomalyScorer()
