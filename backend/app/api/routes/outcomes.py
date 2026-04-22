"""Signal outcome tracking persisted in PostgreSQL."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
import logging

import pandas as pd
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from ...core.database import AsyncSessionLocal
from ...models.outcome import SignalOutcome
from ...services.data_fetcher import get_data_fetcher
from ...services.kis_client import get_kis_client

router = APIRouter(prefix="/outcomes", tags=["outcomes"])
logger = logging.getLogger(__name__)

DEFAULT_INTENT = "breakout_wait"
RECENT_INTRADAY_LOOKBACK_DAYS = 7


class OutcomeRecord(BaseModel):
    symbol_code: str
    symbol_name: str
    pattern_type: str
    timeframe: str
    signal_date: str
    entry_price: float
    target_price: float | None = None
    stop_price: float | None = None
    intent: str | None = Field(default=DEFAULT_INTENT, description="observe | breakout_wait | pullback_candidate | invalidation_watch")
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
    high: float | None = None
    low: float | None = None
    evaluation_basis: str = "latest_close"
    target_price: float | None = None
    stop_price: float | None = None
    reason: str


class OutcomeEvaluationResponse(BaseModel):
    status: str
    checked: int
    updated: int
    skipped: int
    items: list[OutcomeEvaluationItem]


@dataclass
class PriceEvent:
    when: datetime
    high: float
    low: float
    close: float
    basis: str


@dataclass
class PricePathSnapshot:
    events: list[PriceEvent]
    latest_close: float | None
    highest_high: float | None
    lowest_low: float | None
    basis: str


@dataclass
class EvaluationDecision:
    outcome: str
    reason: str
    exit_price: float
    exit_date: str
    evaluation_basis: str
    observed_high: float | None
    observed_low: float | None


def _normalize_intent(intent: str | None) -> str:
    value = (intent or DEFAULT_INTENT).strip().lower()
    allowed = {"observe", "breakout_wait", "pullback_candidate", "invalidation_watch"}
    return value if value in allowed else DEFAULT_INTENT


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
        "intent": _normalize_intent(record.intent),
        "outcome": record.outcome,
        "exit_price": record.exit_price,
        "exit_date": record.exit_date,
        "notes": record.notes,
        "p_up_at_signal": record.p_up_at_signal,
        "composite_score_at_signal": record.composite_score_at_signal,
        "textbook_similarity_at_signal": record.textbook_similarity_at_signal,
        "trade_readiness_at_signal": record.trade_readiness_at_signal,
        "evaluation_basis": record.evaluation_basis,
        "observed_high": record.observed_high,
        "observed_low": record.observed_low,
        "recorded_at": record.recorded_at.isoformat() if record.recorded_at else None,
        "updated_at": record.updated_at.isoformat() if record.updated_at else None,
    }


def _parse_signal_date(value: str) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def _days_between(start: str | None, end: str | None) -> int | None:
    if not start or not end:
        return None
    try:
        return max((date.fromisoformat(end[:10]) - date.fromisoformat(start[:10])).days, 0)
    except ValueError:
        return None


def _frame_events(frame: pd.DataFrame, *, timestamp_column: str, basis: str) -> list[PriceEvent]:
    if frame.empty or timestamp_column not in frame.columns:
        return []

    ordered = frame.copy()
    ordered[timestamp_column] = pd.to_datetime(ordered[timestamp_column], errors="coerce")
    ordered = ordered.dropna(subset=[timestamp_column, "high", "low", "close"]).sort_values(timestamp_column)
    events: list[PriceEvent] = []
    for row in ordered.itertuples(index=False):
        when = getattr(row, timestamp_column)
        if when is None or pd.isna(when):
            continue
        if isinstance(when, pd.Timestamp):
            when = when.to_pydatetime()
        events.append(
            PriceEvent(
                when=when,
                high=float(getattr(row, "high")),
                low=float(getattr(row, "low")),
                close=float(getattr(row, "close")),
                basis=basis,
            )
        )
    return events


def _latest_close_from_events(events: list[PriceEvent]) -> float | None:
    if not events:
        return None
    return float(events[-1].close)


def _price_extremes(events: list[PriceEvent]) -> tuple[float | None, float | None]:
    if not events:
        return None, None
    return max(event.high for event in events), min(event.low for event in events)


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


async def _load_price_path(symbol: str, signal_day: date, timeframe: str) -> PricePathSnapshot:
    fetcher = get_data_fetcher()
    today = date.today()
    daily_df = await fetcher.get_stock_ohlcv(symbol, signal_day, today)
    daily_events = _frame_events(daily_df, timestamp_column="date", basis="daily_high_low")

    recent_start = max(signal_day, today - timedelta(days=RECENT_INTRADAY_LOOKBACK_DAYS - 1))
    intraday_events: list[PriceEvent] = []
    if recent_start <= today:
        try:
            intraday_df = await fetcher.get_stock_intraday_ohlcv(
                symbol,
                "1m",
                days=max(1, (today - recent_start).days + 1),
            )
            if not intraday_df.empty and "datetime" in intraday_df.columns:
                intraday_df = intraday_df.copy()
                intraday_df["datetime"] = pd.to_datetime(intraday_df["datetime"], errors="coerce")
                intraday_df = intraday_df.loc[intraday_df["datetime"].dt.date >= recent_start]
                intraday_events = _frame_events(intraday_df, timestamp_column="datetime", basis="intraday_high_low")
        except Exception:
            intraday_events = []

    if intraday_events:
        daily_events = [event for event in daily_events if event.when.date() < recent_start]

    events = sorted([*daily_events, *intraday_events], key=lambda event: event.when)
    latest_close = _latest_close_from_events(events)
    highest_high, lowest_low = _price_extremes(events)
    basis = "intraday_high_low" if intraday_events else "daily_high_low"
    return PricePathSnapshot(
        events=events,
        latest_close=latest_close,
        highest_high=highest_high,
        lowest_low=lowest_low,
        basis=basis,
    )


def _normalize_cutoff(recorded_at: datetime | None) -> datetime | None:
    if recorded_at is None:
        return None
    if recorded_at.tzinfo is not None:
        return recorded_at.astimezone().replace(tzinfo=None)
    return recorded_at


async def _load_price_path_since_signal(
    symbol: str,
    signal_day: date,
    timeframe: str,
    recorded_at: datetime | None,
) -> PricePathSnapshot:
    snapshot = await _load_price_path(symbol, signal_day, timeframe)
    cutoff = _normalize_cutoff(recorded_at)
    if cutoff is None:
        return snapshot

    filtered_events = [
        event
        for event in snapshot.events
        if (
            (event.basis == "intraday_high_low" and event.when > cutoff)
            or (event.basis != "intraday_high_low" and event.when.date() > cutoff.date())
        )
    ]
    latest_close = _latest_close_from_events(filtered_events)
    highest_high, lowest_low = _price_extremes(filtered_events)
    basis = filtered_events[-1].basis if filtered_events else snapshot.basis
    return PricePathSnapshot(
        events=filtered_events,
        latest_close=latest_close,
        highest_high=highest_high,
        lowest_low=lowest_low,
        basis=basis,
    )


def _decide_outcome_from_events(
    *,
    events: list[PriceEvent],
    target_price: float | None,
    stop_price: float | None,
) -> EvaluationDecision | None:
    if not events:
        return None

    highest_high, lowest_low = _price_extremes(events)
    for event in events:
        target_hit = target_price is not None and event.high >= target_price
        stop_hit = stop_price is not None and event.low <= stop_price

        if target_hit and stop_hit:
            return EvaluationDecision(
                outcome="stopped_out",
                reason=f"같은 바에서 목표가와 무효화가를 모두 터치해 보수적으로 손절 처리 ({event.when.date().isoformat()})",
                exit_price=float(stop_price or event.close),
                exit_date=event.when.date().isoformat(),
                evaluation_basis=event.basis,
                observed_high=highest_high,
                observed_low=lowest_low,
            )
        if target_hit:
            return EvaluationDecision(
                outcome="win",
                reason=f"고가가 목표가에 먼저 닿음 ({event.when.date().isoformat()})",
                exit_price=float(target_price or event.close),
                exit_date=event.when.date().isoformat(),
                evaluation_basis=event.basis,
                observed_high=highest_high,
                observed_low=lowest_low,
            )
        if stop_hit:
            return EvaluationDecision(
                outcome="stopped_out",
                reason=f"저가가 무효화가에 먼저 닿음 ({event.when.date().isoformat()})",
                exit_price=float(stop_price or event.close),
                exit_date=event.when.date().isoformat(),
                evaluation_basis=event.basis,
                observed_high=highest_high,
                observed_low=lowest_low,
            )
    return None


def _fallback_close_decision(
    *,
    close: float | None,
    target_price: float | None,
    stop_price: float | None,
) -> EvaluationDecision | None:
    if close is None or close <= 0:
        return None
    if target_price is not None and close >= target_price:
        return EvaluationDecision(
            outcome="win",
            reason="최신 종가가 목표가 이상",
            exit_price=close,
            exit_date=date.today().isoformat(),
            evaluation_basis="latest_close",
            observed_high=close,
            observed_low=close,
        )
    if stop_price is not None and close <= stop_price:
        return EvaluationDecision(
            outcome="stopped_out",
            reason="최신 종가가 무효화가 이하",
            exit_price=close,
            exit_date=date.today().isoformat(),
            evaluation_basis="latest_close",
            observed_high=close,
            observed_low=close,
        )
    return None


@router.post("", status_code=201)
async def record_outcome(record: OutcomeRecord) -> dict:
    """Create a new outcome record in PostgreSQL."""
    async with AsyncSessionLocal() as session:
        entry = SignalOutcome(
            **record.model_dump(),
            intent=_normalize_intent(record.intent),
            recorded_at=datetime.now(),
        )
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
    """Close pending records when target or stop was touched after the signal date."""
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
            signal_day = _parse_signal_date(record.signal_date)
            if not symbol or signal_day is None:
                skipped += 1
                continue

            checked += 1
            snapshot = await _load_price_path_since_signal(symbol, signal_day, record.timeframe, record.recorded_at)
            decision = _decide_outcome_from_events(
                events=snapshot.events,
                target_price=record.target_price,
                stop_price=record.stop_price,
            )
            if decision is None:
                latest_close = snapshot.latest_close
                if latest_close is None:
                    latest_close = await _latest_close(symbol)
                decision = _fallback_close_decision(
                    close=latest_close,
                    target_price=record.target_price,
                    stop_price=record.stop_price,
                )

            if decision is None:
                continue

            record.outcome = decision.outcome
            record.exit_price = decision.exit_price
            record.exit_date = decision.exit_date
            record.notes = f"auto_evaluated:{decision.evaluation_basis}"
            record.evaluation_basis = decision.evaluation_basis
            record.observed_high = decision.observed_high
            record.observed_low = decision.observed_low
            record.updated_at = datetime.now()
            items.append(
                OutcomeEvaluationItem(
                    id=record.id,
                    symbol_code=symbol,
                    symbol_name=record.symbol_name,
                    outcome=decision.outcome,
                    close=snapshot.latest_close or decision.exit_price,
                    high=decision.observed_high,
                    low=decision.observed_low,
                    evaluation_basis=decision.evaluation_basis,
                    target_price=record.target_price,
                    stop_price=record.stop_price,
                    reason=decision.reason,
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
    hold_days = [days for record in completed if (days := _days_between(record.signal_date, record.exit_date)) is not None]

    by_pattern: dict[str, dict[str, int]] = {}
    by_intent: dict[str, dict[str, int]] = {}
    for record in completed:
        bucket = by_pattern.setdefault(record.pattern_type or "unknown", {"wins": 0, "total": 0})
        bucket["total"] += 1
        if record.outcome == "win":
            bucket["wins"] += 1
        intent_bucket = by_intent.setdefault(_normalize_intent(record.intent), {"wins": 0, "total": 0})
        intent_bucket["total"] += 1
        if record.outcome == "win":
            intent_bucket["wins"] += 1

    return {
        "total_records": len(records),
        "completed": len(completed),
        "wins": len(wins),
        "win_rate": round(len(wins) / max(len(completed), 1), 3),
        "avg_hold_days": round(sum(hold_days) / len(hold_days), 2) if hold_days else 0.0,
        "pending": len([record for record in records if record.outcome == "pending"]),
        "cancelled": len([record for record in records if record.outcome == "cancelled"]),
        "by_pattern": {
            key: {**value, "win_rate": round(value["wins"] / max(value["total"], 1), 3)}
            for key, value in sorted(by_pattern.items(), key=lambda item: -item[1]["total"])
        },
        "by_intent": {
            key: {**value, "win_rate": round(value["wins"] / max(value["total"], 1), 3)}
            for key, value in sorted(by_intent.items(), key=lambda item: -item[1]["total"])
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
        if update.outcome in {"win", "loss", "stopped_out", "cancelled"} and not record.evaluation_basis:
            record.evaluation_basis = "manual"
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
