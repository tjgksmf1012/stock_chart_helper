"""Signal outcome tracking persisted in PostgreSQL."""

from __future__ import annotations

from datetime import date, datetime, timedelta
import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from ...core.database import AsyncSessionLocal
from ...models.outcome import SignalOutcome
from ...services.data_fetcher import get_data_fetcher
from ...services.kis_client import get_kis_client

router = APIRouter(prefix="/outcomes", tags=["outcomes"])
logger = logging.getLogger(__name__)


class OutcomeRecord(BaseModel):
    symbol_code: str
    symbol_name: str
    pattern_type: str
    timeframe: str
    signal_date: str
    entry_price: float
    target_price: float | None = None
    stop_price: float | None = None
    outcome: str = Field(default="pending", description="win | loss | stopped_out | pending | cancelled")
    exit_price: float | None = None
    exit_date: str | None = None
    notes: str | None = None
    p_up_at_signal: float | None = None
    composite_score_at_signal: float | None = None
    textbook_similarity_at_signal: float | None = None
    trade_readiness_at_signal: float | None = None


class OutcomeUpdate(BaseModel):
    outcome: str = Field(description="win | loss | stopped_out | cancelled")
    exit_price: float | None = None
    exit_date: str | None = None
    notes: str | None = None


class OutcomeEvaluationItem(BaseModel):
    id: int
    symbol_code: str
    symbol_name: str
    outcome: str
    close: float
    target_price: float | None = None
    stop_price: float | None = None
    reason: str


class OutcomeEvaluationResponse(BaseModel):
    status: str
    checked: int
    updated: int
    skipped: int
    items: list[OutcomeEvaluationItem]


def _serialize(record: SignalOutcome) -> dict:
    return {
        "id": record.id,
        "symbol_code": record.symbol_code,
        "symbol_name": record.symbol_name,
        "pattern_type": record.pattern_type,
        "timeframe": record.timeframe,
        "signal_date": record.signal_date,
        "entry_price": record.entry_price,
        "target_price": record.target_price,
        "stop_price": record.stop_price,
        "outcome": record.outcome,
        "exit_price": record.exit_price,
        "exit_date": record.exit_date,
        "notes": record.notes,
        "p_up_at_signal": record.p_up_at_signal,
        "composite_score_at_signal": record.composite_score_at_signal,
        "textbook_similarity_at_signal": record.textbook_similarity_at_signal,
        "trade_readiness_at_signal": record.trade_readiness_at_signal,
        "recorded_at": record.recorded_at.isoformat() if record.recorded_at else None,
        "updated_at": record.updated_at.isoformat() if record.updated_at else None,
    }


async def _latest_close(symbol: str) -> float | None:
    kis = get_kis_client()
    if kis.configured:
        try:
            kis_data = await kis.fetch_current_price(symbol)
            if kis_data and kis_data.get("close"):
                return float(kis_data["close"])
        except Exception:
            pass

    try:
        fetcher = get_data_fetcher()
        end = date.today()
        start = end - timedelta(days=7)
        hist = await fetcher.get_stock_ohlcv(symbol, start, end)
        if not hist.empty:
            return float(hist["close"].iloc[-1])
    except Exception:
        pass

    return None


@router.post("", status_code=201)
async def record_outcome(record: OutcomeRecord) -> dict:
    """Create a new outcome record in PostgreSQL."""
    async with AsyncSessionLocal() as session:
        entry = SignalOutcome(**record.model_dump(), recorded_at=datetime.now())
        session.add(entry)
        await session.flush()
        total_records = await session.scalar(select(func.count()).select_from(SignalOutcome))
        await session.commit()
        return {"status": "ok", "id": entry.id, "total_records": int(total_records or 0)}


@router.get("")
async def list_outcomes() -> list[dict]:
    """Return all outcome records, newest first."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(SignalOutcome).order_by(SignalOutcome.recorded_at.desc(), SignalOutcome.id.desc())
        )
        return [_serialize(record) for record in result.scalars().all()]


@router.post("/evaluate-pending")
async def evaluate_pending_outcomes() -> OutcomeEvaluationResponse:
    """Close pending records when the latest price has reached target or stop."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(SignalOutcome).where(SignalOutcome.outcome == "pending").order_by(SignalOutcome.recorded_at.asc())
        )
        pending = result.scalars().all()
        items: list[OutcomeEvaluationItem] = []
        checked = 0
        skipped = 0

        for record in pending:
            symbol = record.symbol_code
            if not symbol:
                skipped += 1
                continue

            close = await _latest_close(symbol)
            if close is None or close <= 0:
                skipped += 1
                continue

            checked += 1
            next_outcome: str | None = None
            reason = ""
            if record.target_price is not None and close >= record.target_price:
                next_outcome = "win"
                reason = "latest price reached target"
            elif record.stop_price is not None and close <= record.stop_price:
                next_outcome = "stopped_out"
                reason = "latest price reached stop"

            if not next_outcome:
                continue

            record.outcome = next_outcome
            record.exit_price = close
            record.exit_date = date.today().isoformat()
            record.notes = "auto_evaluated"
            record.updated_at = datetime.now()
            items.append(
                OutcomeEvaluationItem(
                    id=record.id,
                    symbol_code=symbol,
                    symbol_name=record.symbol_name,
                    outcome=next_outcome,
                    close=close,
                    target_price=record.target_price,
                    stop_price=record.stop_price,
                    reason=reason,
                )
            )

        if items:
            await session.commit()

    return OutcomeEvaluationResponse(
        status="ok",
        checked=checked,
        updated=len(items),
        skipped=skipped,
        items=items,
    )


async def run_scheduled_outcome_evaluation() -> None:
    """Run the same pending evaluation from APScheduler."""
    result = await evaluate_pending_outcomes()
    logger.info(
        "scheduled outcome evaluation finished",
        extra={
            "checked": result.checked,
            "updated": result.updated,
            "skipped": result.skipped,
        },
    )


@router.get("/summary")
async def outcomes_summary() -> dict:
    """Aggregate statistics: overall win-rate and per-pattern breakdown."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(SignalOutcome))
        records = result.scalars().all()

    completed = [record for record in records if record.outcome not in ("pending", "cancelled")]
    wins = [record for record in completed if record.outcome == "win"]

    by_pattern: dict[str, dict[str, int]] = {}
    for record in completed:
        bucket = by_pattern.setdefault(record.pattern_type or "unknown", {"wins": 0, "total": 0})
        bucket["total"] += 1
        if record.outcome == "win":
            bucket["wins"] += 1

    return {
        "total_records": len(records),
        "completed": len(completed),
        "wins": len(wins),
        "win_rate": round(len(wins) / max(len(completed), 1), 3),
        "pending": len([record for record in records if record.outcome == "pending"]),
        "cancelled": len([record for record in records if record.outcome == "cancelled"]),
        "by_pattern": {
            key: {**value, "win_rate": round(value["wins"] / max(value["total"], 1), 3)}
            for key, value in sorted(by_pattern.items(), key=lambda item: -item[1]["total"])
        },
    }


@router.patch("/{outcome_id}")
async def update_outcome(outcome_id: int, update: OutcomeUpdate) -> dict:
    """Mark a previously-recorded signal as won/lost/stopped/cancelled."""
    async with AsyncSessionLocal() as session:
        record = await session.get(SignalOutcome, outcome_id)
        if not record:
            raise HTTPException(status_code=404, detail=f"Outcome {outcome_id} not found")

        patch = {key: value for key, value in update.model_dump().items() if value is not None}
        for key, value in patch.items():
            setattr(record, key, value)
        record.updated_at = datetime.now()
        await session.commit()
        return {"status": "ok", "id": outcome_id}


@router.delete("/{outcome_id}")
async def delete_outcome(outcome_id: int) -> dict:
    """Remove an outcome record."""
    async with AsyncSessionLocal() as session:
        record = await session.get(SignalOutcome, outcome_id)
        if not record:
            raise HTTPException(status_code=404, detail=f"Outcome {outcome_id} not found")
        await session.delete(record)
        await session.commit()
        return {"status": "ok", "deleted_id": outcome_id}
