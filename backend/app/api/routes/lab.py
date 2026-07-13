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

from ...core.redis import cache_get, cache_set
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


def _get_signals_lock() -> asyncio.Lock:
    global _signals_lock
    if _signals_lock is None:
        _signals_lock = asyncio.Lock()
    return _signals_lock


@router.get("/signals")
async def get_live_signals(refresh: bool = False) -> dict[str, Any]:
    """검증 통과(pass/watch) 전략이 최근 며칠 내 낸 신호만 모아서 반환.

    탈락(fail) 전략의 신호는 포함하지 않는다. 시세 로딩이 무거워 30분 캐시하고,
    동시 요청은 락으로 직렬화한다.
    """
    if not refresh:
        cached = await cache_get(_SIGNALS_CACHE_KEY)
        if isinstance(cached, dict):
            return cached

    lock = _get_signals_lock()
    async with lock:
        if not refresh:
            cached = await cache_get(_SIGNALS_CACHE_KEY)
            if isinstance(cached, dict):
                return cached
        result = await _compute_live_signals()
        await cache_set(_SIGNALS_CACHE_KEY, result, ttl=_SIGNALS_TTL)
        return result


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
    return {
        "generated_at": datetime.now(UTC).replace(tzinfo=None).isoformat(),
        "eligible_strategies": [
            {"strategy_id": sid, "label": label_by_id.get(sid, sid), "verdict": verdict_by_id.get(sid)}
            for sid in eligible
        ],
        "universe_size": len(bars_by_code),
        "signals": all_signals,
        # 라이브 유니버스는 현재 상장 종목이라 백테스트와 달리 생존 편향이 없다
        # (오늘 거래 가능한 종목에 대한 오늘의 신호이므로).
        "note": None,
    }
