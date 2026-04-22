from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from statistics import mean
from typing import Any

import pandas as pd
from sqlalchemy import delete, desc, func, select

from ..core.redis import cache_delete, cache_get, cache_set
from ..models.scan_history import ScanCandidateSnapshot, ScanRun
from .data_fetcher import get_data_fetcher
from .timeframe_service import resolve_daily_reference_date

SCAN_QUALITY_CACHE_PREFIX = "scan-quality-report:v1"
SCAN_HISTORY_RECENT_LIMIT = 10
QUALITY_FORWARD_BARS = 20
QUALITY_LOOKBACK_DAYS = 180


@dataclass
class CandidateForwardStats:
    close_return_pct: float
    max_runup_pct: float
    max_drawdown_pct: float
    positive_close: bool
    hit_3pct: bool
    hit_5pct: bool


def _parse_iso_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def _score_bucket(score: float) -> str:
    if score >= 0.75:
        return "0.75+"
    if score >= 0.60:
        return "0.60-0.74"
    if score >= 0.45:
        return "0.45-0.59"
    return "<0.45"


def _rate(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(numerator / denominator, 3)


def _safe_mean(values: list[float]) -> float:
    if not values:
        return 0.0
    return round(float(mean(values)), 4)


def _evaluate_forward_window(frame: pd.DataFrame, signal_day: date, signal_price: float, forward_bars: int) -> CandidateForwardStats | None:
    if frame.empty or signal_price <= 0:
        return None

    working = frame.copy()
    working["date"] = pd.to_datetime(working["date"], errors="coerce").dt.date
    working = working.dropna(subset=["date", "high", "low", "close"])
    future = working.loc[working["date"] > signal_day].sort_values("date").head(forward_bars)
    if future.empty:
        return None

    final_close = float(future["close"].iloc[-1])
    max_high = float(future["high"].max())
    min_low = float(future["low"].min())
    close_return_pct = (final_close - signal_price) / signal_price
    max_runup_pct = (max_high - signal_price) / signal_price
    max_drawdown_pct = (signal_price - min_low) / signal_price
    return CandidateForwardStats(
        close_return_pct=round(close_return_pct, 4),
        max_runup_pct=round(max_runup_pct, 4),
        max_drawdown_pct=round(max_drawdown_pct, 4),
        positive_close=close_return_pct > 0,
        hit_3pct=max_runup_pct >= 0.03,
        hit_5pct=max_runup_pct >= 0.05,
    )


async def persist_scan_history(
    *,
    timeframe: str,
    timeframe_label: str,
    source: str | None,
    status: str,
    candidate_source: str | None,
    reference_date: str | None,
    reference_reason: str | None,
    universe_size: int | None,
    candidate_count: int | None,
    started_at: datetime,
    finished_at: datetime,
    duration_ms: int | None,
    last_error: str | None,
    results: list[dict[str, Any]],
) -> int | None:
    from ..core.database import AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        run = ScanRun(
            timeframe=timeframe,
            timeframe_label=timeframe_label,
            source=source,
            status=status,
            candidate_source=candidate_source,
            reference_date=reference_date,
            reference_reason=reference_reason,
            universe_size=universe_size,
            candidate_count=candidate_count,
            result_count=len(results),
            duration_ms=duration_ms,
            started_at=started_at,
            finished_at=finished_at,
            last_error=last_error,
        )
        session.add(run)
        await session.flush()

        for index, row in enumerate(results, start=1):
            session.add(
                ScanCandidateSnapshot(
                    run_id=run.id,
                    rank=int(row.get("rank") or index),
                    symbol_code=str(row.get("code") or ""),
                    symbol_name=str(row.get("name") or row.get("code") or ""),
                    market=str(row.get("market") or "KRX"),
                    timeframe=str(row.get("timeframe") or timeframe),
                    timeframe_label=str(row.get("timeframe_label") or timeframe_label),
                    signal_date=str(row.get("reference_date") or reference_date or finished_at.date().isoformat()),
                    signal_price=float(row.get("signal_price")) if row.get("signal_price") is not None else None,
                    pattern_type=row.get("pattern_type"),
                    state=row.get("state"),
                    action_plan=row.get("action_plan"),
                    action_plan_label=row.get("action_plan_label"),
                    setup_stage=row.get("setup_stage"),
                    no_signal_flag=bool(row.get("no_signal_flag")),
                    p_up=float(row.get("p_up") or 0.0),
                    p_down=float(row.get("p_down") or 0.0),
                    confidence=float(row.get("confidence") or 0.0),
                    entry_score=float(row.get("entry_score") or 0.0),
                    composite_score=float(row.get("composite_score") or 0.0),
                    trade_readiness_score=float(row.get("trade_readiness_score") or 0.0),
                    entry_window_score=float(row.get("entry_window_score") or 0.0),
                    freshness_score=float(row.get("freshness_score") or 0.0),
                    reentry_score=float(row.get("reentry_score") or 0.0),
                    historical_edge_score=float(row.get("historical_edge_score") or 0.0),
                    data_quality=float(row.get("data_quality") or 0.0),
                    sample_reliability=float(row.get("sample_reliability") or 0.0),
                    reward_risk_ratio=float(row.get("reward_risk_ratio") or 0.0),
                    target_distance_pct=float(row.get("target_distance_pct") or 0.0),
                    stop_distance_pct=float(row.get("stop_distance_pct") or 0.0),
                    target_level=float(row.get("target_level")) if row.get("target_level") is not None else None,
                    invalidation_level=float(row.get("invalidation_level")) if row.get("invalidation_level") is not None else None,
                    trigger_level=float(row.get("trigger_level")) if row.get("trigger_level") is not None else None,
                    fetch_status=row.get("fetch_status"),
                    candidate_source=candidate_source,
                    reason_summary=row.get("reason_summary"),
                    recorded_at=finished_at,
                )
            )

        await session.commit()

    await cache_delete(f"{SCAN_QUALITY_CACHE_PREFIX}:{timeframe}:{QUALITY_LOOKBACK_DAYS}:{QUALITY_FORWARD_BARS}")
    return run.id


async def list_recent_scan_runs(limit: int = SCAN_HISTORY_RECENT_LIMIT, timeframe: str | None = None) -> list[dict[str, Any]]:
    from ..core.database import AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        stmt = select(ScanRun).order_by(desc(ScanRun.finished_at), desc(ScanRun.id)).limit(limit)
        if timeframe:
            stmt = stmt.where(ScanRun.timeframe == timeframe)
        rows = (await session.execute(stmt)).scalars().all()
        return [
            {
                "id": row.id,
                "timeframe": row.timeframe,
                "timeframe_label": row.timeframe_label,
                "source": row.source,
                "status": row.status,
                "candidate_source": row.candidate_source,
                "reference_date": row.reference_date,
                "reference_reason": row.reference_reason,
                "universe_size": row.universe_size,
                "candidate_count": row.candidate_count,
                "result_count": row.result_count,
                "duration_ms": row.duration_ms,
                "started_at": row.started_at.isoformat() if row.started_at else None,
                "finished_at": row.finished_at.isoformat() if row.finished_at else None,
                "last_error": row.last_error,
            }
            for row in rows
        ]


async def prune_scan_history(keep_days: int = 400) -> int:
    from ..core.database import AsyncSessionLocal

    cutoff = datetime.utcnow() - timedelta(days=keep_days)
    async with AsyncSessionLocal() as session:
        stmt = delete(ScanRun).where(ScanRun.finished_at.is_not(None), ScanRun.finished_at < cutoff)
        result = await session.execute(stmt)
        await session.commit()
        return int(result.rowcount or 0)


async def build_scan_quality_report(
    *,
    timeframe: str = "1d",
    lookback_days: int = QUALITY_LOOKBACK_DAYS,
    forward_bars: int = QUALITY_FORWARD_BARS,
) -> dict[str, Any]:
    cache_key = f"{SCAN_QUALITY_CACHE_PREFIX}:{timeframe}:{lookback_days}:{forward_bars}"
    cached = await cache_get(cache_key)
    if isinstance(cached, dict):
        return cached

    from ..core.database import AsyncSessionLocal

    reference_day, _ = resolve_daily_reference_date()
    earliest_day = reference_day - timedelta(days=lookback_days)
    async with AsyncSessionLocal() as session:
        run_count_stmt = select(func.count()).select_from(ScanRun).where(
            ScanRun.timeframe == timeframe,
            ScanRun.finished_at.is_not(None),
            ScanRun.finished_at >= datetime.combine(earliest_day, datetime.min.time()),
        )
        run_count = int((await session.execute(run_count_stmt)).scalar_one() or 0)

        candidate_stmt = (
            select(ScanCandidateSnapshot)
            .join(ScanRun, ScanRun.id == ScanCandidateSnapshot.run_id)
            .where(
                ScanRun.timeframe == timeframe,
                ScanRun.finished_at.is_not(None),
                ScanRun.finished_at >= datetime.combine(earliest_day, datetime.min.time()),
                ScanCandidateSnapshot.no_signal_flag.is_(False),
                ScanCandidateSnapshot.signal_price.is_not(None),
            )
            .order_by(ScanCandidateSnapshot.signal_date.desc(), ScanCandidateSnapshot.id.desc())
        )
        candidates = (await session.execute(candidate_stmt)).scalars().all()

    if not candidates:
        payload = {
            "generated_at": datetime.utcnow().isoformat(),
            "timeframe": timeframe,
            "lookback_days": lookback_days,
            "forward_bars": forward_bars,
            "run_count": run_count,
            "evaluated_count": 0,
            "latest_reference_date": None,
            "summary": {
                "avg_close_return_pct": 0.0,
                "avg_max_runup_pct": 0.0,
                "avg_max_drawdown_pct": 0.0,
                "positive_close_rate": 0.0,
                "hit_3pct_rate": 0.0,
                "hit_5pct_rate": 0.0,
            },
            "score_buckets": [],
            "action_plans": [],
            "notes": [
                "아직 저장된 스캔 이력이 충분하지 않아 품질 검증 리포트를 계산하지 못했습니다.",
                "scan history가 며칠 쌓이면 점수 구간별 실제 후속 수익률과 변동폭을 확인할 수 있습니다.",
            ],
        }
        await cache_set(cache_key, payload, ttl=3600)
        return payload

    fetcher = get_data_fetcher()
    symbols = sorted({row.symbol_code for row in candidates if row.symbol_code})
    symbol_frames: dict[str, pd.DataFrame] = {}
    for symbol in symbols:
        min_day = min((_parse_iso_date(item.signal_date) for item in candidates if item.symbol_code == symbol), default=None)
        if min_day is None:
            continue
        try:
            frame = await fetcher.get_stock_ohlcv(symbol, min_day, reference_day)
        except Exception:
            frame = pd.DataFrame()
        symbol_frames[symbol] = frame

    evaluated: list[tuple[ScanCandidateSnapshot, CandidateForwardStats]] = []
    for candidate in candidates:
        signal_day = _parse_iso_date(candidate.signal_date)
        signal_price = float(candidate.signal_price or 0.0)
        if signal_day is None or signal_price <= 0:
            continue
        stats = _evaluate_forward_window(symbol_frames.get(candidate.symbol_code, pd.DataFrame()), signal_day, signal_price, forward_bars)
        if stats is None:
            continue
        evaluated.append((candidate, stats))

    if not evaluated:
        payload = {
            "generated_at": datetime.utcnow().isoformat(),
            "timeframe": timeframe,
            "lookback_days": lookback_days,
            "forward_bars": forward_bars,
            "run_count": run_count,
            "evaluated_count": 0,
            "latest_reference_date": max((candidate.signal_date for candidate in candidates), default=None),
            "summary": {
                "avg_close_return_pct": 0.0,
                "avg_max_runup_pct": 0.0,
                "avg_max_drawdown_pct": 0.0,
                "positive_close_rate": 0.0,
                "hit_3pct_rate": 0.0,
                "hit_5pct_rate": 0.0,
            },
            "score_buckets": [],
            "action_plans": [],
            "notes": [
                "저장된 이력은 있지만 아직 평가 가능한 20봉 이후 데이터가 충분하지 않습니다.",
            ],
        }
        await cache_set(cache_key, payload, ttl=3600)
        return payload

    close_returns = [item.close_return_pct for _, item in evaluated]
    runups = [item.max_runup_pct for _, item in evaluated]
    drawdowns = [item.max_drawdown_pct for _, item in evaluated]

    bucket_rows: dict[str, list[CandidateForwardStats]] = defaultdict(list)
    action_rows: dict[str, list[CandidateForwardStats]] = defaultdict(list)
    for candidate, stats in evaluated:
        bucket_rows[_score_bucket(float(candidate.composite_score or 0.0))].append(stats)
        action_rows[str(candidate.action_plan or "unknown")].append(stats)

    def _serialize_group(items: list[CandidateForwardStats]) -> dict[str, Any]:
        total = len(items)
        return {
            "sample_count": total,
            "avg_close_return_pct": _safe_mean([item.close_return_pct for item in items]),
            "avg_max_runup_pct": _safe_mean([item.max_runup_pct for item in items]),
            "avg_max_drawdown_pct": _safe_mean([item.max_drawdown_pct for item in items]),
            "positive_close_rate": _rate(sum(1 for item in items if item.positive_close), total),
            "hit_3pct_rate": _rate(sum(1 for item in items if item.hit_3pct), total),
            "hit_5pct_rate": _rate(sum(1 for item in items if item.hit_5pct), total),
        }

    bucket_order = ["0.75+", "0.60-0.74", "0.45-0.59", "<0.45"]
    score_buckets = [
        {"bucket": bucket, **_serialize_group(bucket_rows[bucket])}
        for bucket in bucket_order
        if bucket_rows.get(bucket)
    ]
    action_plans = [
        {"action_plan": action_plan, **_serialize_group(items)}
        for action_plan, items in sorted(action_rows.items(), key=lambda pair: len(pair[1]), reverse=True)
    ]

    summary = {
        "avg_close_return_pct": _safe_mean(close_returns),
        "avg_max_runup_pct": _safe_mean(runups),
        "avg_max_drawdown_pct": _safe_mean(drawdowns),
        "positive_close_rate": _rate(sum(1 for _, item in evaluated if item.positive_close), len(evaluated)),
        "hit_3pct_rate": _rate(sum(1 for _, item in evaluated if item.hit_3pct), len(evaluated)),
        "hit_5pct_rate": _rate(sum(1 for _, item in evaluated if item.hit_5pct), len(evaluated)),
    }

    notes: list[str] = []
    top_bucket = next((item for item in score_buckets if item["bucket"] == "0.75+"), None)
    low_bucket = next((item for item in score_buckets if item["bucket"] == "<0.45"), None)
    if top_bucket and low_bucket:
        if top_bucket["avg_close_return_pct"] > low_bucket["avg_close_return_pct"]:
            notes.append("상위 composite score 구간이 저점수 구간보다 평균 후속 수익률이 높게 나타났습니다.")
        else:
            notes.append("현재 데이터에서는 상위 composite score 구간이 저점수 구간보다 뚜렷하게 우세하지 않습니다.")
    if len(evaluated) < 30:
        notes.append("표본 수가 아직 작아 통계 해석은 보수적으로 보는 편이 좋습니다.")

    payload = {
        "generated_at": datetime.utcnow().isoformat(),
        "timeframe": timeframe,
        "lookback_days": lookback_days,
        "forward_bars": forward_bars,
        "run_count": run_count,
        "evaluated_count": len(evaluated),
        "latest_reference_date": max((candidate.signal_date for candidate, _ in evaluated), default=None),
        "summary": summary,
        "score_buckets": score_buckets,
        "action_plans": action_plans,
        "notes": notes,
    }
    await cache_set(cache_key, payload, ttl=21600)
    return payload
