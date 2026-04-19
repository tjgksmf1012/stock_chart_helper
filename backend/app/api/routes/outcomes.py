"""Signal outcome tracking — record whether a detected pattern played out as predicted."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ...core.redis import cache_get, cache_set

router = APIRouter(prefix="/outcomes", tags=["outcomes"])

_KEY = "outcomes:v1:records"
_TTL = 60 * 60 * 24 * 365 * 3  # 3 years


class OutcomeRecord(BaseModel):
    symbol_code: str
    symbol_name: str
    pattern_type: str
    timeframe: str
    signal_date: str
    entry_price: float
    target_price: float | None = None
    stop_price: float | None = None
    # outcome is set later via PATCH; "pending" on creation
    outcome: str = Field(default="pending", description="win | loss | stopped_out | pending | cancelled")
    exit_price: float | None = None
    exit_date: str | None = None
    notes: str | None = None
    # snapshot scores at the time the signal was recorded
    p_up_at_signal: float | None = None
    composite_score_at_signal: float | None = None
    textbook_similarity_at_signal: float | None = None
    trade_readiness_at_signal: float | None = None


class OutcomeUpdate(BaseModel):
    outcome: str = Field(description="win | loss | stopped_out | cancelled")
    exit_price: float | None = None
    exit_date: str | None = None
    notes: str | None = None


async def _load() -> list[dict[str, Any]]:
    return await cache_get(_KEY) or []


async def _save(records: list[dict[str, Any]]) -> None:
    await cache_set(_KEY, records, _TTL)


@router.post("", status_code=201)
async def record_outcome(record: OutcomeRecord) -> dict:
    """Create a new outcome record (outcome='pending' by default)."""
    records = await _load()
    entry: dict[str, Any] = {
        **record.model_dump(),
        "id": len(records),
        "recorded_at": datetime.now().isoformat(),
    }
    records.append(entry)
    await _save(records)
    return {"status": "ok", "id": entry["id"], "total_records": len(records)}


@router.get("")
async def list_outcomes() -> list[dict]:
    """Return all outcome records, newest first."""
    records = await _load()
    return list(reversed(records))


@router.patch("/{outcome_id}")
async def update_outcome(outcome_id: int, update: OutcomeUpdate) -> dict:
    """Mark a previously-recorded signal as won/lost/stopped/cancelled."""
    records = await _load()
    for record in records:
        if record.get("id") == outcome_id:
            patch = {k: v for k, v in update.model_dump().items() if v is not None}
            record.update(patch)
            record["updated_at"] = datetime.now().isoformat()
            await _save(records)
            return {"status": "ok", "id": outcome_id}
    raise HTTPException(status_code=404, detail=f"Outcome {outcome_id} not found")


@router.delete("/{outcome_id}")
async def delete_outcome(outcome_id: int) -> dict:
    """Remove an outcome record."""
    records = await _load()
    new_records = [r for r in records if r.get("id") != outcome_id]
    if len(new_records) == len(records):
        raise HTTPException(status_code=404, detail=f"Outcome {outcome_id} not found")
    await _save(new_records)
    return {"status": "ok", "deleted_id": outcome_id}


@router.get("/summary")
async def outcomes_summary() -> dict:
    """Aggregate statistics: overall win-rate and per-pattern breakdown."""
    records = await _load()
    completed = [r for r in records if r.get("outcome") not in ("pending", "cancelled")]
    wins = [r for r in completed if r.get("outcome") == "win"]

    by_pattern: dict[str, dict[str, int]] = {}
    for r in completed:
        pt = r.get("pattern_type", "unknown")
        bucket = by_pattern.setdefault(pt, {"wins": 0, "total": 0})
        bucket["total"] += 1
        if r.get("outcome") == "win":
            bucket["wins"] += 1

    return {
        "total_records": len(records),
        "completed": len(completed),
        "wins": len(wins),
        "win_rate": round(len(wins) / max(len(completed), 1), 3),
        "pending": len([r for r in records if r.get("outcome") == "pending"]),
        "cancelled": len([r for r in records if r.get("outcome") == "cancelled"]),
        "by_pattern": {
            k: {**v, "win_rate": round(v["wins"] / max(v["total"], 1), 3)}
            for k, v in sorted(by_pattern.items(), key=lambda x: -x[1]["total"])
        },
    }
