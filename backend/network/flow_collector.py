"""
psutil-based network flow capture (spec section 5.1) — NOT YET BUILT.

Plan: poll `psutil.net_connections(kind='inet')` on a 1-2 second timer,
diff snapshots against the previous poll to find new/closed
connections, attribute each to its owning process via `pid`. Capture:
source/destination IP + port, protocol, connection status, timestamp,
and the owning process name (e.g. "your Chrome process" is more useful
to a user than a bare IP).

Aggregate into 60-second-window feature vectors: connection count,
unique destination count, unique port count, failed/reset ratio,
cyclical time-of-day encoding (sin/cos of the hour), one-hot protocol —
a different feature set from `feature_engineering.py`'s
CICIDS2017-column-oriented one (see that file's docstring).

Connection metadata only — never packet payloads/content
(spec section 14, non-negotiable).

Build order: spec section 15, step 8, alongside `isolation_forest.py`'s
rework to match this feature set.
"""
from __future__ import annotations

from typing import Iterator


def collect_flows() -> Iterator[dict]:
    """Would yield one windowed feature-vector dict every ~60 seconds. Not yet implemented."""
    raise NotImplementedError("Flow capture is not yet implemented — see this file's module docstring for the plan.")
