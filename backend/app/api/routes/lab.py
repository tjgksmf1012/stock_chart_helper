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
from ...services.collected_signals import parse_collected_records
from ...services.lab_signals import apply_drift_demotions, collect_recent_signals, eligible_strategy_ids
from ...strategies.registry import make_strategy

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/lab", tags=["lab"])

_LAB_DIR = Path(__file__).resolve().parents[3] / "data" / "lab"

_VERDICT_ORDER = {"pass": 0, "watch": 1, "fail": 2}

_SIGNALS_CACHE_KEY = "lab:live_signals:v5"  # v5: 시장 체제 게이트 (실험① 채택)
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


async def _paper_state_by_id(reports: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """전략별 {drift, realized_ev_pct} — 신호 게이트의 드리프트 자동 강등 재료."""
    ci_low_by_id = {
        r["strategy"]: (r["ci_95"][0] if isinstance(r.get("ci_95"), list) and r["ci_95"] else None)
        for r in reports if r.get("strategy")
    }
    async with AsyncSessionLocal() as session:
        rows = (await session.execute(select(LabPaperTrade))).scalars().all()
    closed = [
        {"strategy_id": t.strategy_id, "status": "closed", "net_return_pct": t.net_return_pct}
        for t in rows if t.status != "open"
    ]
    realized = realized_summary_by_strategy(closed)
    out: dict[str, dict[str, Any]] = {}
    for sid in set(realized) | set(ci_low_by_id):
        ev = realized.get(sid, {}).get("ev_pct")
        n = int(realized.get(sid, {}).get("n", 0))
        out[sid] = {"drift": drift_status(ev, n, ci_low_by_id.get(sid)), "realized_ev_pct": ev}
    return out


async def _compute_live_signals() -> dict[str, Any]:
    from ...lab.universe import fetch_current_universe_biased
    from ...services.data_fetcher import get_data_fetcher

    reports = load_latest_reports(_LAB_DIR)
    # 실측(종이매매)이 백테스트에서 이탈한 전략은 여기서 자동 강등된다
    # (이탈+실측 흑자=관찰 강등, 이탈+실측 손실=제외). 판정 카드의 백테스트
    # 리포트 자체는 바꾸지 않는다.
    try:
        paper_state = await _paper_state_by_id(reports)
    except Exception as exc:  # 실측 조회 실패가 신호 게이트 전체를 죽이면 안 된다
        logger.warning("실측 상태 조회 실패 — 강등 없이 진행: %s", exc)
        paper_state = {}
    reports, demotions = apply_drift_demotions(reports, paper_state)

    verdict_by_id = {r["strategy"]: r.get("verdict") for r in reports if r.get("strategy")}
    label_by_id = {r["strategy"]: r.get("label", r["strategy"]) for r in reports if r.get("strategy")}
    ev_by_id = {r["strategy"]: r.get("ev_pct") for r in reports if r.get("strategy")}
    eligible = eligible_strategy_ids(reports)
    if not eligible:
        return {
            "generated_at": datetime.now(UTC).replace(tzinfo=None).isoformat(),
            "eligible_strategies": [],
            "signals": [],
            "demotions": demotions,
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

    # 시장 체제 게이트 (실험① 채택, 2026-07-19) — 백테스트와 같은 규칙을 라이브에도.
    # KOSPI가 200일선 아래인 날짜의 신호는 발행하지 않는다. 지수 조회 실패 시엔
    # 게이트 없이 진행하되 응답에 사실대로 기록한다 (신호 게이트 생존 우선).
    from ...lab.regime_gate import DEFAULT_MA_WINDOW, RegimeGatedStrategy, build_regime_lookup, fetch_kospi_bars

    regime_lookup = None
    regime_info: dict[str, Any] = {"enabled": False, "ok_today": None}
    try:
        index_bars = await asyncio.to_thread(fetch_kospi_bars)
        regime_lookup = build_regime_lookup(index_bars, ma_window=DEFAULT_MA_WINDOW)
        regime_info = {"enabled": True, "ok_today": regime_lookup(date.today())}
    except Exception as exc:
        logger.warning("체제 게이트: 지수 조회 실패 — 게이트 없이 진행: %s", exc)

    as_of = date.today()
    all_signals: list[dict[str, Any]] = []
    for strategy_id in eligible:
        try:
            strategy = make_strategy(strategy_id)
        except KeyError:
            continue
        if regime_lookup is not None:
            strategy = RegimeGatedStrategy(strategy, regime_lookup)
        signals = collect_recent_signals(strategy, bars_by_code, as_of=as_of, lookback_days=_SIGNAL_RECENT_DAYS)
        for sig in signals:
            sig["verdict"] = verdict_by_id.get(strategy_id)
            sig["strategy_label"] = label_by_id.get(strategy_id, sig["strategy_id"])
        all_signals.extend(signals)

    all_signals.sort(key=lambda s: (_VERDICT_ORDER.get(s.get("verdict"), 3), s["signal_date"]), reverse=False)

    # 종목명 부착 — 코드만 보여주면 매일 읽는 화면의 가독성이 나쁘다. 실패해도 무해.
    # symbols DB는 로컬 모드에서 비어 있으므로 유니버스 캐시(name 포함)를 쓴다.
    try:
        universe_df = await fetcher.get_universe()
        if "name" in universe_df.columns:
            name_by_code = dict(zip(universe_df["code"].astype(str), universe_df["name"]))
            for sig in all_signals:
                sig["name"] = name_by_code.get(sig["code"])
    except Exception as exc:
        logger.warning("신호 종목명 조회 실패 (코드만 표시): %s", exc)

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
            {
                "strategy_id": sid,
                "label": label_by_id.get(sid, sid),
                "verdict": verdict_by_id.get(sid),
                # 오늘의 최우선 랭킹 재료 — 검증 기대값 (상승확률 랭킹 금지 원칙)
                "ev_pct": ev_by_id.get(sid),
            }
            for sid in eligible
        ],
        "universe_size": len(bars_by_code),
        "signals": all_signals,
        "demotions": demotions,
        "regime_gate": regime_info,
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


_OUTLOOK_HORIZONS = (
    (1, "내일"),
    (5, "1주"),
    (20, "1개월"),
    (60, "3개월"),
)
_OUTLOOK_CACHE_PREFIX = "lab:outlook:v1"
_OUTLOOK_TTL = 1800


@router.get("/outlook/{symbol_code}")
async def get_symbol_outlook(symbol_code: str) -> dict[str, Any]:
    """확률적 전망 — 점 예측이 아니라 "80% 구간 + 그 구간의 실측 적중률".

    기간별(1/5/20/60일) 선행수익률 분위수(최근 2년 분포)와, 같은 방식 구간이
    과거에 실제로 몇 %를 맞췄는지(walk-forward coverage)를 함께 반환한다.
    검증 통과 전략의 최근 신호가 이 종목에 있으면 조건부 기대값도 얹는다.
    """
    from ...lab.outlook import forward_return_quantiles, interval_coverage
    from ...services.data_fetcher import get_data_fetcher

    cache_key = f"{_OUTLOOK_CACHE_PREFIX}:{symbol_code}"
    cached = await cache_get(cache_key)
    if isinstance(cached, dict):
        return cached

    try:
        bars = await get_data_fetcher().get_stock_ohlcv_by_timeframe(symbol_code, "1d", lookback_days=1200)
    except Exception as exc:
        logger.warning("outlook 시세 실패 %s: %s", symbol_code, exc)
        bars = None
    if bars is None or len(bars) < 150:
        raise HTTPException(status_code=404, detail="전망을 계산할 시세 이력이 부족합니다")

    closes = [float(c) for c in bars["close"]]
    horizons: list[dict[str, Any]] = []
    for days, label in _OUTLOOK_HORIZONS:
        # 분위수는 최근 2년 분포로 (오래된 체제 섞임 방지), 적중률은 전체 이력으로 검증
        quantiles = forward_return_quantiles(closes[-(504 + days):], horizon=days)
        coverage = interval_coverage(closes, horizon=days, lookback=252)
        if quantiles is None:
            continue
        horizons.append({
            "horizon_days": days,
            "label": label,
            **{k: round(v, 4) for k, v in quantiles.items()},
            "coverage": coverage,  # None이면 검증 표본 부족 — 프론트에 그대로 노출
        })

    # 검증 통과 전략의 조건부 기대값 (이 종목에 최근 신호가 있을 때만)
    conditional = None
    signals_cache = await cache_get(_SIGNALS_CACHE_KEY)
    if isinstance(signals_cache, dict):
        matching = [s for s in signals_cache.get("signals", []) if s.get("code") == symbol_code]
        if matching:
            sig = matching[0]
            report = next(
                (r for r in load_latest_reports(_LAB_DIR) if r.get("strategy") == sig.get("strategy_id")),
                None,
            )
            if report:
                conditional = {
                    "strategy_id": sig["strategy_id"],
                    "strategy_label": sig.get("strategy_label", sig["strategy_id"]),
                    "signal_date": sig.get("signal_date"),
                    "holding_days": sig.get("max_holding_days"),
                    "ev_pct": report.get("ev_pct"),
                    "ci_95": report.get("ci_95"),
                    "verdict": report.get("verdict"),
                }

    result = {
        "symbol_code": symbol_code,
        "generated_at": datetime.now(UTC).replace(tzinfo=None).isoformat(),
        "horizons": horizons,
        "conditional_signal": conditional,
        "note": (
            "점 예측이 아닙니다 — 과거 분포 기반 80% 구간이며, '실측 적중률'은 같은 방식의 "
            "구간이 과거에 실제로 맞은 비율입니다. 80%에서 크게 벗어나면 지금 분포가 "
            "과거와 다르다는 경고로 읽으세요."
        ),
    }
    await cache_set(cache_key, result, ttl=_OUTLOOK_TTL)
    return result


async def run_scheduled_paper_trade_evaluation() -> None:
    """APScheduler에서 종이매매 청산 평가를 돌린다 (장마감 후)."""
    try:
        result = await evaluate_paper_trades()
        logger.info("scheduled paper-trade eval: checked=%s closed=%s", result["open_checked"], result["closed"])
    except Exception as exc:
        logger.warning("scheduled paper-trade eval 실패: %s", exc)


def _collected_signals_url() -> str:
    """설정에서 수집 신호 JSONL의 raw URL을 읽는다 (빈 값 = 동기화 비활성)."""
    from ...core.config import get_settings

    return get_settings().collected_signals_url.strip()


async def sync_collected_signals(url: str | None = None) -> int:
    """GitHub Actions가 커밋한 수집 신호(JSONL)를 받아 종이매매 DB에 동기화한다.

    컴퓨터를 며칠 꺼뒀어도, 켜는 순간 그동안 클라우드가 모아둔 신호가 실측
    표본으로 합류한다. 중복은 기존 dedupe 경로가 걸러낸다. 실패는 무해(로그만).
    """
    if url is None:
        url = _collected_signals_url()
    if not url:
        return 0
    try:
        import httpx

        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            response = await client.get(url)
            response.raise_for_status()
        records = parse_collected_records(response.text)
        recorded = await _record_paper_trades(records)
        if recorded:
            logger.info("수집 신호 동기화: %s건 중 신규 %s건 기록", len(records), recorded)
        return recorded
    except Exception as exc:
        logger.warning("수집 신호 동기화 실패 (무해 — 다음 기회에 재시도): %s", exc)
        return 0


async def run_startup_lab_sync() -> None:
    """앱 시작 시 랩 실측 따라잡기 — 수집 신호 합류 후 청산 소급 평가.

    로컬 데스크톱 모드는 스케줄러가 꺼져 있어(enable_scheduler=false) 16:25/16:30
    잡이 돌지 않는다 — 대신 켜는 순간 이 함수가 공백을 메운다. 실패는 무해.
    """
    try:
        await sync_collected_signals()
    except Exception as exc:
        logger.warning("시작 시 수집 동기화 실패: %s", exc)
    try:
        result = await evaluate_paper_trades()
        if result.get("closed"):
            logger.info("시작 시 청산 소급: %s건 확인, %s건 청산", result.get("open_checked"), result.get("closed"))
    except Exception as exc:
        logger.warning("시작 시 청산 평가 실패: %s", exc)


async def run_scheduled_signal_computation() -> None:
    """APScheduler에서 장마감 후 신호를 계산·기록한다.

    사용자가 오늘 탭을 열지 않는 날에도 종이매매(실측 표본)가 매일 쌓이게 하는
    잡 — 드리프트 감시의 재료가 사용 빈도와 무관하게 누적된다. 캐시도 채워져
    다음 방문 시 신호가 즉시 뜬다. 강등 로직 포함 전체 파이프라인을 재사용.
    """
    try:
        result = await _compute_and_cache_signals()
        logger.info(
            "scheduled signal computation: signals=%s recorded=%s",
            len(result.get("signals", [])), result.get("recorded_paper_trades"),
        )
    except Exception as exc:
        logger.warning("scheduled signal computation 실패: %s", exc)


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
