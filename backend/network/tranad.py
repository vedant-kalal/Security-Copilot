"""
TranAD — temporal/sequence anomaly scoring (spec section 5.3), stretch
goal. NOT YET BUILT — build only after `isolation_forest.py`'s spec-5.2
rework is fully working end to end (spec section 15, step 12).

Official implementation: https://github.com/imperial-qore/TranAD
Paper: https://arxiv.org/abs/2201.07284

Runs on the same windowed feature vectors as Isolation Forest but
scores the *sequence*, catching temporal patterns (beaconing, slow
exfiltration) a single-flow score misses. Unsupervised, trained mostly
on normal traffic — same bootstrap-on-CICIDS2017-then-personalize
approach as Isolation Forest (see security-copilot-hybrid-addendum
memory). A flow escalates if EITHER Isolation Forest or TranAD flags it.
"""
from __future__ import annotations

from typing import Sequence


def score_sequence(window_features: Sequence[list[float]]) -> float:
    """Would return a 0..1 temporal anomaly score for a sequence of feature vectors. Not yet implemented."""
    raise NotImplementedError(
        "TranAD is not yet implemented — build after Isolation Forest is stable (spec section 15, step 12)."
    )
