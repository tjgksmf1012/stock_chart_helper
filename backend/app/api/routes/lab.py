"""실험실 API — 랩 검증 리포트(data/lab/*.json)를 전략별 최신본으로 제공.

리포트는 scripts/run_lab.py가 생성한다. 이 API는 읽기 전용이며, 트레이드
목록(수천 건)은 목록 응답에서 제외해 payload를 가볍게 유지한다.
스펙(2026-07-12 트레이딩 랩) Phase 3: 검증을 통과하지 못한 전략의 신호는
추천에 쓰이지 않는다 — 그 판정의 원천 데이터가 이 엔드포인트다.
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException

from sqlalchemy import select

from ...core.database import AsyncSessionLocal
from ...core.redis import cache_get, cache_set
from ...lab.costs import CostModel
from ...models.lab_paper_trade import LabPaperTrade
from ...services.lab_paper_trading import (
    dedupe_key,
    drift_status,
    evaluate_paper_trade,
    new_paper_trade_signals,
    realized_summary_by_strategy,
)
from ...services.lab_signals import collect_recent_signals, eligible_strategy_ids
from ...strategies.registry import make_strategy

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/lab", tags=["lab"])

_LAB_DIR = Path(__file__).resolve().parents[3] / "data" / "lab"

_VERDICT_ORDER = {"pass": 0, "watch": 1, "fail": 2}

_SIGNALS_CACHE_KEY = "lab:live_signals:v1"
_SIGNALS_TTL = 1800  # 30분 — 일봉 신호라 자주 안 바뀜
_LIVE_UNIVERSE_TOP_N = 60
_LIVE_LOOKBACK_BARS = 420  # 252봉 전략 워밍업 여유
_SIGNAL_RECENT_DAYS = 5    # 최근 5영업일 내 신호만
_signals_lock: asyncio.Lock | None = None


def load_latest_reports(lab_dir: Path) -> list[dict[str, Any]]:
    """전략별 최신 리포트 (generated_at 기준). 깨진 파일은 건너뛴다."""
    latest: dict[str, dict[str, Any]] = {}
    if not lab_dir.exists():
        return []
    for path in lab_dir.glob("*.json"):
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("lab report 읽기 실패 (%s): %s", path.name, exc)
            continue
        strategy_id = raw.get("strategy")
        if not strategy_id:
            continue
        generated = str(raw.get("generated_at", ""))
        if strategy_id not in latest or generated > str(latest[strategy_id].get("generated_at", "")):
            latest[strategy_id] = raw
    return sorted(
        latest.values(),
        key=lambda r: (_VERDICT_ORDER.get(r.get("verdict"), 3), -(r.get("ev_pct") or 0.0)),
    )


def _without_trades(report: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in report.items() if k != "trades"}


@router.get("/reports")
async def list_lab_reports() -> dict[str, Any]:
    reports = load_latest_reports(_LAB_DIR)
    return {"reports": [_without_trades(r) for r in reports]}


@router.get("/reports/{strategy_id}")
async def get_lab_report(strategy_id: str, include_trades: bool = False) -> dict[str, Any]:
    for report in load_latest_reports(_LAB_DIR):
        if report.get("strategy") == strategy_id:
            return report if include_trades else _without_trades(report)
    raise HTTPException(status_code=404, detail=f"전략 리포트 없음: {strategy_id}")


_signals_task: asyncio.Task | None = None


async def _compute_and_cache_signals() -> dict[str, Any]:
    result = await _compute_live_signals()
    await cache_set(_SIGNALS_CACHE_KEY, result, ttl=_SIGNALS_TTL)
    return result


@router.get("/signals")
async def get_live_signals(refresh: bool = False) -> dict[str, Any]:
    """검증 통과(pass/watch) 전략의 최근 신호. 논블로킹 — 시세 로딩(최대 ~80초)이
    프론트 axios 타임아웃(20초)을 넘기므로, 즉시 반환하고 계산은 백그라운드로 돌린다.

    - 캐시 있음: status="ready" + 신호
    - 캐시 없음/refresh: 백그라운드 계산 시작, status="computing" + 빈 신호
      (프론트가 폴링하다가 ready가 되면 채운다)
    탈락(fail) 전략의 신호는 포함하지 않는다.
    """
    global _signals_task

    if not refresh:
        cached = await cache_get(_SIGNALS_CACHE_KEY)
        if isinstance(cached, dict):
            return {**cached, "status": "ready"}

    # 이미 계산 중이면 그 태스크를 재사용, 아니면 새로 시작
    if _signals_task is None or _signals_task.done():
        _signals_task = asyncio.create_task(_compute_and_cache_signals())

    return {
        "status": "computing",
        "generated_at": None,
        "eligible_strategies": [],
        "signals": [],
        "note": "현재 유니버스에서 신호를 계산하는 중입니다. 잠시 후 자동으로 채워집니다.",
    }


async def _compute_live_signals() -> dict[str, Any]:
    from ...lab.universe import fetch_current_universe_biased
    from ...services.data_fetcher import get_data_fetcher

    reports = load_latest_reports(_LAB_DIR)
    verdict_by_id = {r["strategy"]: r.get("verdict") for r in reports if r.get("strategy")}
    label_by_id = {r["strategy"]: r.get("label", r["strategy"]) for r in reports if r.get("strategy")}
    eligible = eligible_strategy_ids(reports)
    if not eligible:
        return {
            "generated_at": datetime.now(UTC).replace(tzinfo=None).isoformat(),
            "eligible_strategies": [],
            "signals": [],
            "note": "검증을 통과한 전략이 아직 없습니다. 실험실에서 전략 판정을 먼저 확인하세요.",
        }

    codes = await fetch_current_universe_biased(_LIVE_UNIVERSE_TOP_N)
    fetcher = get_data_fetcher()
    bars_by_code: dict[str, Any] = {}
    for code in codes:
        try:
            df = await fetcher.get_stock_ohlcv_by_timeframe(code, "1d", lookback_days=_LIVE_LOOKBACK_BARS)
            if df is not None and len(df) >= 60:
                bars_by_code[code] = df.reset_index(drop=True)
        except Exception as exc:
            logger.warning("live signals: 시세 실패 %s: %s", code, exc)

    as_of = date.today()
    all_signals: list[dict[str, Any]] = []
    for strategy_id in eligible:
        try:
            strategy = make_strategy(strategy_id)
        except KeyError:
            continue
        signals = collect_recent_signals(strategy, bars_by_code, as_of=as_of, lookback_days=_SIGNAL_RECENT_DAYS)
        for sig in signals:
            sig["verdict"] = verdict_by_id.get(strategy_id)
            sig["strategy_label"] = label_by_id.get(strategy_id, sig["strategy_id"])
        all_signals.extend(signals)

    all_signals.sort(key=lambda s: (_VERDICT_ORDER.get(s.get("verdict"), 3), s["signal_date"]), reverse=False)

    # 자동 종이매매: 새로 나온 신호를 open 상태로 기록 (중복은 무시). 실측 성적을
    # 쌓아 백테스트와의 드리프트를 감시하는 재료가 된다.
    recorded = 0
    try:
        recorded = await _record_paper_trades(all_signals)
    except Exception as exc:
        logger.warning("종이매매 기록 실패: %s", exc)

    return {
        "generated_at": datetime.now(UTC).replace(tzinfo=None).isoformat(),
        "eligible_strategies": [
            {"strategy_id": sid, "label": label_by_id.get(sid, sid), "verdict": verdict_by_id.get(sid)}
            for sid in eligible
        ],
        "universe_size": len(bars_by_code),
        "signals": all_signals,
        "recorded_paper_trades": recorded,
        # 라이브 유니버스는 현재 상장 종목이라 백테스트와 달리 생존 편향이 없다
        # (오늘 거래 가능한 종목에 대한 오늘의 신호이므로).
        "note": None,
    }


async def _record_paper_trades(signals: list[dict[str, Any]]) -> int:
    """새 신호를 open 종이매매로 기록. 이미 있는(전략+종목+신호일) 건 건너뛴다."""
    if not signals:
        return 0
    async with AsyncSessionLocal() as session:
        rows = (await session.execute(select(
            LabPaperTrade.strategy_id, LabPaperTrade.code, LabPaperTrade.signal_date
        ))).all()
        existing = {dedupe_key(r[0], r[1], r[2]) for r in rows}
        fresh = new_paper_trade_signals(signals, existing)
        for sig in fresh:
            session.add(LabPaperTrade(
                strategy_id=sig["strategy_id"], code=sig["code"], signal_date=sig["signal_date"],
                stop_price=float(sig["stop_price"]),
                target_price=sig.get("target_price"),
                max_holding_days=int(sig.get("max_holding_days", 40)),
                status="open", recorded_at=datetime.now(),
            ))
        if fresh:
            await session.commit()
        return len(fresh)


@router.post("/paper-trades/evaluate")
async def evaluate_paper_trades() -> dict[str, Any]:
    """열린 종이매매를 백테스트와 같은 규칙으로 청산 시도. 스케줄러/수동 호출용."""
    from ...services.data_fetcher import get_data_fetcher

    cost_model = CostModel()
    fetcher = get_data_fetcher()
    checked = 0
    closed = 0
    async with AsyncSessionLocal() as session:
        opens = (await session.execute(
            select(LabPaperTrade).where(LabPaperTrade.status == "open")
        )).scalars().all()

        # 종목별로 시세를 한 번만 로드 (여러 전략이 같은 종목을 열 수 있음)
        codes = sorted({t.code for t in opens})
        bars_by_code: dict[str, Any] = {}
        for code in codes:
            try:
                df = await fetcher.get_stock_ohlcv_by_timeframe(code, "1d", lookback_days=_LIVE_LOOKBACK_BARS)
                if df is not None and not df.empty:
                    bars_by_code[code] = df.reset_index(drop=True)
            except Exception as exc:
                logger.warning("종이매매 평가: 시세 실패 %s: %s", code, exc)

        for trade in opens:
            bars = bars_by_code.get(trade.code)
            if bars is None:
                continue
            checked += 1
            result = evaluate_paper_trade(
                {
                    "code": trade.code, "signal_date": trade.signal_date,
                    "stop_price": trade.stop_price, "target_price": trade.target_price,
                    "max_holding_days": trade.max_holding_days, "strategy_id": trade.strategy_id,
                },
                bars, cost_model,
            )
            if result is None:
                continue  # 아직 보유 중
            trade.status = "closed"
            trade.entry_date = result["entry_date"]
            trade.entry_price = result["entry_price"]
            trade.exit_date = result["exit_date"]
            trade.exit_price = result["exit_price"]
            trade.exit_reason = result["exit_reason"]
            trade.net_return_pct = result["net_return_pct"]
            trade.closed_at = datetime.now()
            closed += 1

        if closed:
            await session.commit()

    return {"status": "ok", "open_checked": checked, "closed": closed}


async def run_scheduled_paper_trade_evaluation() -> None:
    """APScheduler에서 종이매매 청산 평가를 돌린다 (장마감 후)."""
    try:
        result = await evaluate_paper_trades()
        logger.info("scheduled paper-trade eval: checked=%s closed=%s", result["open_checked"], result["closed"])
    except Exception as exc:
        logger.warning("scheduled paper-trade eval 실패: %s", exc)


@router.get("/paper-trades/summary")
async def paper_trades_summary() -> dict[str, Any]:
    """전략별 실측 종이매매 성적 + 백테스트 대비 드리프트 판정."""
    reports = load_latest_reports(_LAB_DIR)
    ci_low_by_id = {
        r["strategy"]: (r["ci_95"][0] if isinstance(r.get("ci_95"), list) and r["ci_95"] else None)
        for r in reports if r.get("strategy")
    }
    label_by_id = {r["strategy"]: r.get("label", r["strategy"]) for r in reports if r.get("strategy")}

    async with AsyncSessionLocal() as session:
        rows = (await session.execute(select(LabPaperTrade))).scalars().all()

    open_counts: dict[str, int] = {}
    closed_dicts: list[dict[str, Any]] = []
    for t in rows:
        if t.status == "open":
            open_counts[t.strategy_id] = open_counts.get(t.strategy_id, 0) + 1
        else:
            closed_dicts.append({
                "strategy_id": t.strategy_id, "status": "closed", "net_return_pct": t.net_return_pct,
            })

    realized = realized_summary_by_strategy(closed_dicts)
    strategies = []
    for strategy_id in sorted(set(list(realized) + list(open_counts) + list(ci_low_by_id))):
        stat = realized.get(strategy_id, {"n": 0, "ev_pct": None, "win_rate": None})
        ci_low = ci_low_by_id.get(strategy_id)
        strategies.append({
            "strategy_id": strategy_id,
            "label": label_by_id.get(strategy_id, strategy_id),
            "realized_n": stat["n"],
            "realized_ev_pct": stat["ev_pct"],
            "realized_win_rate": stat["win_rate"],
            "open_count": open_counts.get(strategy_id, 0),
            "backtest_ci_low": ci_low,
            "drift": drift_status(stat["ev_pct"], stat["n"], ci_low),
        })
    return {"strategies": strategies}
