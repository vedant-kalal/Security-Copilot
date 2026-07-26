"""
GET /runs, GET /runs/{run_id} — run history for the UI (history.py).

Not part of the original spec (sections 1-15) — added so past
investigations are actually browsable from the small history UI
(index.html) instead of only ever existing as terminal scrollback or a
one-off markdown file.
"""
from __future__ import annotations

from fastapi import APIRouter, Query

from exceptions import NotFoundError
from history import get_run, list_runs

router = APIRouter()


@router.get("/runs", tags=["History"])
async def get_runs(limit: int = Query(default=50, ge=1, le=200)) -> list[dict]:
    """Summary list — newest first — for the history sidebar."""
    return list_runs(limit=limit)


@router.get("/runs/{run_id}", tags=["History"])
async def get_run_detail(run_id: str) -> dict:
    """Full detail for one run — every tool call, screenshot path, verdict."""
    run = get_run(run_id)
    if run is None:
        raise NotFoundError(f"Run {run_id} not found")
    return run
