"""
Market scanner for dashboard and screener results.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from ..api.schemas import SymbolInfo
from ..core.config import get_settings
from ..core.redis import cache_delete, cache_get, cache_set
from .analysis_service import analyze_symbol_dataframe
from .data_fetcher import get_data_fetcher
from .timeframe_service import DEFAULT_TIMEFRAME, timeframe_label

logger = logging.getLogger(__name__)
settings = get_settings()

FALLBACK_CODES: list[tuple[str, str, str]] = [
    ("005930", "삼성전자", "KOSPI"),
    ("000660", "SK하이닉스", "KOSPI"),
    ("207940", "삼성바이오로직스", "KOSPI"),
    ("005380", "현대차", "KOSPI"),
    ("000270", "기아", "KOSPI"),
    ("035420", "NAVER", "KOSPI"),
    ("051910", "LG화학", "KOSPI"),
    ("006400", "삼성SDI", "KOSPI"),
    ("035720", "카카오", "KOSPI"),
    ("068270", "셀트리온", "KOSPI"),
    ("247540", "에코프로비엠", "KOSDAQ"),
    ("086520", "에코프로", "KOSDAQ"),
    ("091990", "셀트리온헬스케어", "KOSDAQ"),
    ("041510", "에스엠", "KOSDAQ"),
    ("263750", "펄어비스", "KOSDAQ"),
]

ANCHOR_TIMEFRAMES: dict[str, list[str]] = {
    "1mo": ["1wk"],
    "1wk": ["1mo", "1d"],
    "1d": ["1wk", "1mo"],
    "60m": ["1d", "1wk"],
    "30m": ["60m", "1d"],
    "15m": ["60m", "1d"],
    "1m": ["15m", "60m"],
}

_scan_lock = asyncio.Lock()
_scan_tasks: dict[str, asyncio.Task] = {}
_scan_status: dict[str, dict[str, Any]] = {}
_KST = ZoneInfo("Asia/Seoul")


def _full_scan_cache_key(timeframe: str) -> str:
    return f"scanner:v8:full_results:{timeframe}"


def _single_scan_cache_key(timeframe: str, code: str, allow_live_intraday: bool = True) -> str:
    mode = "live" if allow_live_intraday else "budget"
    return f"scan:v8:result:{timeframe}:{code}:{mode}"


def _utc_now_iso() -> str:
    return datetime.utcnow().isoformat()


def _kst_now() -> datetime:
    return datetime.now(_KST)


def _status_template(timeframe: str) -> dict[str, Any]:
    return {
        "timeframe": timeframe,
        "timeframe_label": timeframe_label(timeframe),
        "status": "idle",
        "is_running": False,
        "source": None,
        "candidate_source": None,
        "candidate_count": None,
        "intraday_live_candidate_limit": None,
        "intraday_live_candidate_count": None,
        "intraday_live_phase": None,
        "cached_result_count": 0,
        "universe_size": None,
        "last_started_at": None,
        "last_finished_at": None,
        "last_error": None,
        "duration_ms": None,
    }


def _update_scan_status(timeframe: str, **kwargs: Any) -> None:
    status = _scan_status.setdefault(timeframe, _status_template(timeframe))
    status.update(kwargs)


def _direction_score(row: dict[str, Any]) -> float:
    return float(row.get("p_up", 0.5)) - float(row.get("p_down", 0.5))


def _direction_label(score: float) -> str:
    if score >= 0.08:
        return "상승"
    if score <= -0.08:
        return "하락"
    return "중립"


def _wyckoff_label(phase: str) -> str:
    labels = {
        "accumulation": "accumulation",
        "markup": "markup",
        "distribution": "distribution",
        "markdown": "markdown",
        "neutral": "neutral",
    }
    return labels.get(phase, phase or "neutral")


def _intraday_session_label(phase: str) -> str:
    labels = {
        "open_drive": "open_drive",
        "midday": "midday",
        "closing_drive": "closing_drive",
        "regular_session": "regular_session",
        "off_hours": "off_hours",
        "neutral": "neutral",
    }
    return labels.get(phase, phase or "neutral")


def _live_intraday_phase(now: datetime | None = None) -> str:
    current = now or _kst_now()
    if current.weekday() >= 5:
        return "off_hours"
    minutes = current.hour * 60 + current.minute
    if minutes < 9 * 60 or minutes >= 15 * 60 + 30:
        return "off_hours"
    if minutes < 9 * 60 + 30:
        return "open_drive"
    if minutes < 11 * 60 + 20:
        return "regular_session"
    if minutes < 13 * 60 + 20:
        return "midday"
    if minutes < 15 * 60:
        return "closing_drive"
    return "off_hours"


def _effective_live_intraday_limit(timeframe: str, candidate_count: int, now: datetime | None = None) -> tuple[int, str]:
    phase = _live_intraday_phase(now)
    base_limit = settings.intraday_live_candidate_limit
    phase_multiplier = {
        "open_drive": 1.0,
        "regular_session": 0.85,
        "midday": 0.45,
        "closing_drive": 0.9,
        "off_hours": 0.0,
    }
    timeframe_multiplier = {
        "1m": 0.45,
        "15m": 1.0,
        "30m": 0.75,
        "60m": 0.65,
    }
    limit = int(round(base_limit * phase_multiplier.get(phase, 0.6) * timeframe_multiplier.get(timeframe, 1.0)))
    if phase != "off_hours":
        limit = max(2, limit)
    limit = min(candidate_count, max(0, limit))
    return limit, phase


def _live_intraday_priority(row: dict[str, Any], timeframe: str) -> float:
    setup_stage = str(row.get("setup_stage") or "")
    action_plan = str(row.get("action_plan") or "watch")
    stage_bonus = {
        "confirmed": 0.12,
        "trigger_ready": 0.11,
        "breakout_watch": 0.08,
        "late_base": 0.07,
        "early_trigger_watch": 0.04,
        "base_building": -0.02,
    }.get(setup_stage, 0.0)
    timeframe_bias = {
        "1m": 0.06,
        "15m": 0.05,
        "30m": 0.03,
        "60m": 0.02,
    }.get(timeframe, 0.0)
    action_bonus = {
        "ready_now": 0.08,
        "watch": 0.03,
        "recheck": -0.03,
        "cooling": -0.14,
    }.get(action_plan, 0.0)
    return (
        0.22 * float(row.get("entry_score", 0.0))
        + 0.18 * float(row.get("entry_window_score", 0.0))
        + 0.12 * float(row.get("freshness_score", 0.0))
        + 0.08 * float(row.get("reentry_score", 0.0))
        + 0.18 * float(row.get("completion_proximity", 0.0))
        + 0.14 * float(row.get("liquidity_score", 0.0))
        + 0.10 * float(row.get("confidence", 0.0))
        + 0.10 * float(row.get("recency_score", 0.0))
        + 0.06 * float(row.get("historical_edge_score", 0.0))
        + 0.06 * float(row.get("trend_alignment_score", 0.0))
        + 0.05 * float(row.get("data_quality", 0.0))
        + 0.08 * float(row.get("action_priority_score", 0.0))
        + stage_bonus
        + timeframe_bias
        + action_bonus
    )


def _live_intraday_reason(row: dict[str, Any], timeframe: str, phase: str) -> str:
    reasons: list[str] = []
    if float(row.get("entry_score", 0.0)) >= 0.72:
        reasons.append("진입 적합도")
    if float(row.get("completion_proximity", 0.0)) >= 0.68:
        reasons.append("완성 임박도")
    if float(row.get("liquidity_score", 0.0)) >= 0.72:
        reasons.append("유동성")
    if float(row.get("recency_score", 0.0)) >= 0.62:
        reasons.append("신호 최신성")
    if str(row.get("setup_stage") or "") in {"trigger_ready", "confirmed", "breakout_watch"}:
        reasons.append("세팅 단계")
    if float(row.get("historical_edge_score", 0.0)) >= 0.58:
        reasons.append("과거 edge")

    if not reasons:
        reasons.append("종합 우선순위")

    phase_prefix = {
        "open_drive": "장초반 확대",
        "regular_session": "장중 선별",
        "midday": "점심장 축소",
        "closing_drive": "마감 전 확대",
        "off_hours": "장외 절약",
    }.get(phase, "분봉 선별")

    return f"{phase_prefix} live 후보: {', '.join(reasons[:3])}"


def _non_live_intraday_reason(
    row: dict[str, Any],
    timeframe: str,
    phase: str,
    live_limit: int,
) -> str:
    if phase == "off_hours" or live_limit <= 0:
        return "Off-hours budget mode keeps intraday analysis on stored/public data unless a fresh live refresh is truly needed."

    reasons: list[str] = []
    if phase == "midday":
        reasons.append("midday throttle keeps live KIS usage tight")
    elif phase == "regular_session":
        reasons.append("regular-session budget mode reserves live slots for stronger setups")
    elif phase == "closing_drive":
        reasons.append("closing-drive live slots are focused on trigger-ready names")
    elif phase == "open_drive":
        reasons.append("open-drive live slots are limited to the sharpest opening setups")

    setup_stage = str(row.get("setup_stage") or "")
    if setup_stage in {"base_building", "early_trigger_watch", "neutral"}:
        reasons.append("setup is still early")

    if float(row.get("completion_proximity", 0.0)) < 0.62:
        reasons.append("completion proximity is below the live threshold")
    if float(row.get("entry_window_score", 0.0)) < 0.55:
        reasons.append("entry window is not attractive enough yet")
    if float(row.get("entry_score", 0.0)) < 0.68:
        reasons.append("entry quality is not strong enough for live priority")
    if float(row.get("liquidity_score", 0.0)) < 0.62:
        reasons.append("liquidity is lighter than the current live cohort")
    if float(row.get("recency_score", 0.0)) < 0.55:
        reasons.append("signal freshness is lagging")
    if float(row.get("freshness_score", 0.0)) < 0.5:
        reasons.append("pattern freshness is below the live cutoff")
    if float(row.get("reentry_score", 0.0)) < 0.35:
        reasons.append("re-entry structure is still weak")

    fetch_status = str(row.get("fetch_status") or "")
    if fetch_status == "scanner_store_only":
        reasons.append("recent stored intraday bars already cover this symbol")
    elif fetch_status == "scanner_public_only":
        reasons.append("public intraday data is sufficient for budget mode")
    elif fetch_status == "scanner_public_augmented":
        reasons.append("stored and public bars were blended to avoid an extra live call")
    elif fetch_status == "kis_cooldown":
        reasons.append("KIS cooldown is active after a recent failure")

    if not reasons:
        reasons.append("live priority score fell below the current session cutoff")

    return f"Budget/store path: {', '.join(reasons[:3])}."


def _intraday_collection_mode(row: dict[str, Any]) -> str:
    if row.get("live_intraday_candidate"):
        return "live"

    fetch_status = str(row.get("fetch_status") or "")
    if fetch_status in {"stored_recent", "stored_fallback", "scanner_store_only"}:
        return "stored"
    if fetch_status in {"scanner_public_only", "yahoo_rate_limited", "intraday_rate_limited", "kis_not_configured"}:
        return "public"
    if fetch_status in {"scanner_public_augmented", "live_augmented_by_store"}:
        return "mixed"
    if fetch_status == "kis_cooldown":
        return "cooldown"
    return "budget"


def _formation_quality_from_row(row: dict[str, Any]) -> float:
    return float(
        row.get("formation_quality")
        or (
            0.28 * float(row.get("leg_balance_fit", 0.0))
            + 0.28 * float(row.get("reversal_energy_fit", 0.0))
            + 0.22 * float(row.get("breakout_quality_fit", 0.0))
            + 0.22 * float(row.get("retest_quality_fit", 0.0))
        )
    )


def _setup_stage(row: dict[str, Any]) -> str:
    state = row.get("state")
    completion = float(row.get("completion_proximity", 0.0))
    formation_quality = _formation_quality_from_row(row)
    confluence = float(row.get("confluence_score", 0.5))

    if state == "confirmed":
        return "confirmed"
    if state == "armed":
        if formation_quality >= 0.62 and confluence >= 0.62:
            return "trigger_ready"
        return "breakout_watch"
    if state == "forming":
        if completion >= 0.72 and formation_quality >= 0.55 and confluence >= 0.58:
            return "late_base"
        if completion >= 0.52 and formation_quality >= 0.45:
            return "early_trigger_watch"
        return "base_building"
    return "neutral"


def _apply_setup_metadata(row: dict[str, Any]) -> dict[str, Any]:
    formation_quality = round(_formation_quality_from_row(row), 3)
    row["formation_quality"] = formation_quality
    row["setup_stage"] = _setup_stage({**row, "formation_quality": formation_quality})
    action_plan = str(row.get("action_plan") or "watch")
    action_priority = float(row.get("action_priority_score", 0.0))

    if row["setup_stage"] == "late_base":
        row["scenario_text"] = (
            f"{row.get('timeframe_label', row.get('timeframe', ''))} forming setup with supportive higher-timeframe context. "
            "Track it like a pre-breakout candidate, not a finished signal."
        )
        row["composite_score"] = round(float(row.get("composite_score", 0.0)) + 0.06, 3)
    elif row["setup_stage"] == "early_trigger_watch":
        row["scenario_text"] = (
            f"{row.get('timeframe_label', row.get('timeframe', ''))} is still building. "
            "The structure is improving, but it needs more confirmation before acting like a full breakout setup."
        )
        row["composite_score"] = round(float(row.get("composite_score", 0.0)) + 0.03, 3)
    elif row["setup_stage"] == "base_building":
        row["composite_score"] = round(float(row.get("composite_score", 0.0)) - 0.03, 3)

    entry_window_score = float(row.get("entry_window_score", 0.0))
    entry_window_label = str(row.get("entry_window_label") or "")
    if entry_window_label == "초기 돌파":
        row["composite_score"] = round(float(row.get("composite_score", 0.0)) + 0.05, 3)
    elif entry_window_label in {"트리거 대기", "기준선 접근"}:
        row["composite_score"] = round(float(row.get("composite_score", 0.0)) + 0.03, 3)
    elif entry_window_label == "확장 추격":
        row["composite_score"] = round(float(row.get("composite_score", 0.0)) - 0.07, 3)
    elif entry_window_label in {"목표 근접", "관망"}:
        row["composite_score"] = round(float(row.get("composite_score", 0.0)) - 0.10, 3)
    elif entry_window_score < 0.3:
        row["composite_score"] = round(float(row.get("composite_score", 0.0)) - 0.04, 3)

    freshness_score = float(row.get("freshness_score", 0.0))
    freshness_label = str(row.get("freshness_label") or "")
    if freshness_label == "신선":
        row["composite_score"] = round(float(row.get("composite_score", 0.0)) + 0.06, 3)
    elif freshness_label == "진행중":
        row["composite_score"] = round(float(row.get("composite_score", 0.0)) + 0.03, 3)
    elif freshness_label == "재기초 관찰":
        row["composite_score"] = round(float(row.get("composite_score", 0.0)) - 0.02, 3)
        row["scenario_text"] = (
            f"{row.get('scenario_text', '')} The prior target may already be spent, so treat this as a rebuild watch instead of a fresh trigger."
        ).strip()
    elif freshness_label in {"종료 패턴", "무효 만료"}:
        row["composite_score"] = round(float(row.get("composite_score", 0.0)) - 0.18, 3)
    elif freshness_score < 0.35:
        row["composite_score"] = round(float(row.get("composite_score", 0.0)) - 0.06, 3)

    reentry_score = float(row.get("reentry_score", 0.0))
    reentry_label = str(row.get("reentry_label") or "")
    reentry_case_label = str(row.get("reentry_case_label") or "")
    reentry_profile_label = str(row.get("reentry_profile_label") or "")
    reentry_structure_label = reentry_case_label or reentry_profile_label or "재진입 구조"
    if reentry_label == "재돌파 대기":
        row["composite_score"] = round(float(row.get("composite_score", 0.0)) + 0.05, 3)
        row["scenario_text"] = (
            f"{row.get('scenario_text', '')} {reentry_structure_label}로 읽히며, 기준선 부근 재정비 후 다시 확장될 수 있습니다."
        ).strip()
    elif reentry_label == "재축적 관찰":
        row["composite_score"] = round(float(row.get("composite_score", 0.0)) + 0.02, 3)
        row["scenario_text"] = (
            f"{row.get('scenario_text', '')} {reentry_structure_label}가 진행 중이라 박스 유지 여부가 중요합니다."
        ).strip()
    elif reentry_label == "실패 후 복구 관찰":
        row["composite_score"] = round(float(row.get("composite_score", 0.0)) - 0.03, 3)
        row["scenario_text"] = (
            f"{row.get('scenario_text', '')} {reentry_structure_label}지만 이전 실패 이력이 있어 더 깔끔한 회복 확인이 필요합니다."
        ).strip()
    elif reentry_label == "재진입 비선호":
        row["composite_score"] = round(float(row.get("composite_score", 0.0)) - 0.12, 3)
    elif reentry_score < 0.30:
        row["composite_score"] = round(float(row.get("composite_score", 0.0)) - 0.04, 3)

    phase = str(row.get("wyckoff_phase") or "neutral")
    if phase == "accumulation":
        row["composite_score"] = round(float(row.get("composite_score", 0.0)) + 0.04, 3)
        row["scenario_text"] = f"{row.get('scenario_text', '')} Wyckoff accumulation context supports a base-building read.".strip()
    elif phase == "markup":
        row["composite_score"] = round(float(row.get("composite_score", 0.0)) + 0.02, 3)
    elif phase == "distribution":
        row["composite_score"] = round(float(row.get("composite_score", 0.0)) - 0.03, 3)
    elif phase == "markdown":
        row["composite_score"] = round(float(row.get("composite_score", 0.0)) - 0.06, 3)

    intraday_phase = str(row.get("intraday_session_phase") or "neutral")
    intraday_score = float(row.get("intraday_session_score", 0.5))
    if intraday_phase == "closing_drive" and intraday_score >= 0.75:
        row["composite_score"] = round(float(row.get("composite_score", 0.0)) + 0.03, 3)
    elif intraday_phase == "midday" and intraday_score <= 0.45:
        row["composite_score"] = round(float(row.get("composite_score", 0.0)) - 0.03, 3)
    elif intraday_phase == "off_hours":
        row["composite_score"] = round(float(row.get("composite_score", 0.0)) - 0.02, 3)

    action_adjustment = {
        "ready_now": 0.08,
        "watch": 0.03,
        "recheck": -0.04,
        "cooling": -0.16,
    }.get(action_plan, 0.0)
    row["composite_score"] = round(
        float(row.get("composite_score", 0.0)) + action_adjustment + 0.06 * max(-0.5, min(0.5, action_priority - 0.5)),
        3,
    )
    if action_plan in {"cooling", "recheck"} and row.get("action_plan_summary"):
        row["scenario_text"] = str(row["action_plan_summary"])

    return row


def _confluence_anchor_weights(timeframe: str) -> list[tuple[str, float]]:
    anchors = ANCHOR_TIMEFRAMES.get(timeframe, [])
    if len(anchors) == 2:
        return [(anchors[0], 0.6), (anchors[1], 0.4)]
    if len(anchors) == 1:
        return [(anchors[0], 1.0)]
    return []


async def _get_cached_count(timeframe: str) -> int:
    cached = await cache_get(_full_scan_cache_key(timeframe))
    return len(cached) if isinstance(cached, list) else 0


async def get_scan_status(timeframe: str = DEFAULT_TIMEFRAME) -> dict[str, Any]:
    status = dict(_scan_status.get(timeframe) or _status_template(timeframe))
    status["cached_result_count"] = max(status.get("cached_result_count", 0), await _get_cached_count(timeframe))
    return status


async def _fetch_universe_codes(limit: int = 100) -> list[tuple[str, str, str]]:
    fetcher = get_data_fetcher()
    universe = await fetcher.get_universe()
    universe_names = (
        {
            str(row["code"]): row.get("name", row["code"]) or row["code"]
            for _, row in universe.iterrows()
        }
        if not universe.empty
        else {}
    )

    try:
        from pykrx import stock as krx

        today = datetime.today().strftime("%Y%m%d")
        rows: list[tuple[str, str, str, float]] = []

        for market in ("KOSPI", "KOSDAQ"):
            cap_df = await asyncio.to_thread(krx.get_market_cap, today, today, market=market)
            if cap_df is None or cap_df.empty:
                continue
            for code, row in cap_df.iterrows():
                market_cap = float(row.get("시가총액", 0)) / 1e8
                if market_cap < settings.min_market_cap_billion:
                    continue
                code_str = str(code)
                rows.append((code_str, universe_names.get(code_str, code_str), market, market_cap))

        if rows:
            rows.sort(key=lambda item: item[3], reverse=True)
            return [(code, name, market) for code, name, market, _ in rows[:limit]]
    except Exception as exc:
        logger.warning("Bulk market-cap universe fetch failed: %s", exc)

    logger.warning("Falling back to static scanner universe")
    return FALLBACK_CODES[:limit]


async def _build_confluence(
    code: str,
    name: str,
    market: str,
    timeframe: str,
    primary_row: dict[str, Any],
    force_refresh: bool,
    allow_live_intraday: bool,
) -> dict[str, Any]:
    weights = _confluence_anchor_weights(timeframe)
    if not weights:
        own_direction = _direction_label(_direction_score(primary_row))
        return {
            "confluence_score": 0.5,
            "confluence_summary": f"{timeframe_label(timeframe)} 단독 신호 기준입니다.",
            "scenario_text": f"{timeframe_label(timeframe)} 기준 {own_direction} 시나리오를 단독으로 해석한 결과입니다.",
            "composite_score": round(
                0.52 * float(primary_row.get("entry_score", 0.0))
                + 0.14 * float(primary_row.get("sample_reliability", 0.0))
                + 0.10 * float(primary_row.get("historical_edge_score", 0.0))
                + 0.14 * float(primary_row.get("headroom_score", 0.0))
                + 0.10 * float(primary_row.get("trend_alignment_score", 0.0))
                + 0.06 * float(primary_row.get("intraday_session_score", 0.5))
                + 0.12 * min(1.0, float(primary_row.get("reward_risk_ratio", 0.0)) / 2.5)
                + 0.12 * float(primary_row.get("data_quality", 0.0))
                + 0.06 * float(primary_row.get("recency_score", 0.0)),
                3,
            ),
        }

    primary_direction = _direction_score(primary_row)
    agreement_parts: list[str] = []
    weighted_score = 0.0
    weighted_total = 0.0

    for anchor_timeframe, weight in weights:
        anchor_row = await _analyze_one(
            code,
            name,
            market,
            anchor_timeframe,
            force_refresh=force_refresh,
            include_confluence=False,
            allow_live_intraday=allow_live_intraday,
        )
        weighted_total += weight
        if not anchor_row:
            weighted_score += 0.45 * weight
            agreement_parts.append(f"{timeframe_label(anchor_timeframe)} 데이터 없음")
            continue

        anchor_direction = _direction_score(anchor_row)
        if anchor_row.get("no_signal_flag"):
            anchor_score = 0.50
        elif primary_direction * anchor_direction > 0.02:
            anchor_score = 0.92 if abs(anchor_direction) >= 0.15 else 0.78
        elif primary_direction * anchor_direction < -0.02:
            anchor_score = 0.10 if abs(anchor_direction) >= 0.15 else 0.24
        else:
            anchor_score = 0.56

        weighted_score += anchor_score * weight
        agreement_parts.append(f"{timeframe_label(anchor_timeframe)} {_direction_label(anchor_direction)}")

    confluence_score = weighted_score / weighted_total if weighted_total else 0.5
    own_direction = _direction_label(primary_direction)

    if confluence_score >= 0.74:
        scenario_text = (
            f"{timeframe_label(timeframe)} 신호와 상위 타임프레임 방향이 비슷해 {own_direction} 추세 추종형으로 보기 좋습니다."
        )
    elif confluence_score >= 0.56:
        scenario_text = (
            f"{timeframe_label(timeframe)} 신호는 유지되지만 상위 축 정렬은 절반 정도입니다. 무효화 기준을 우선 보는 편이 좋습니다."
        )
    else:
        scenario_text = (
            f"{timeframe_label(timeframe)} 신호와 주변 타임프레임이 엇갈립니다. 추세 매매보다 짧은 트리거 확인용으로 보는 편이 낫습니다."
        )

    composite_score = (
        0.34 * float(primary_row.get("entry_score", 0.0))
        + 0.18 * confluence_score
        + 0.12 * float(primary_row.get("sample_reliability", 0.0))
        + 0.10 * float(primary_row.get("historical_edge_score", 0.0))
        + 0.12 * float(primary_row.get("headroom_score", 0.0))
        + 0.10 * float(primary_row.get("trend_alignment_score", 0.0))
        + 0.08 * float(primary_row.get("wyckoff_score", 0.0))
        + 0.06 * float(primary_row.get("intraday_session_score", 0.5))
        + 0.10 * min(1.0, float(primary_row.get("reward_risk_ratio", 0.0)) / 2.5)
        + 0.10 * float(primary_row.get("data_quality", 0.0))
        + 0.08 * float(primary_row.get("recency_score", 0.0))
        + 0.06 * float(primary_row.get("completion_proximity", 0.0))
    )

    return {
        "confluence_score": round(confluence_score, 3),
        "confluence_summary": " / ".join(agreement_parts),
        "scenario_text": scenario_text,
        "composite_score": round(composite_score, 3),
    }


async def _analyze_one(
    code: str,
    name: str,
    market: str,
    timeframe: str,
    force_refresh: bool = False,
    include_confluence: bool = True,
    allow_live_intraday: bool = True,
) -> dict[str, Any] | None:
    fetcher = get_data_fetcher()
    cache_key = _single_scan_cache_key(timeframe, code, allow_live_intraday=allow_live_intraday)
    if not force_refresh:
        cached = await cache_get(cache_key)
        if cached:
            return cached

    try:
        df = await fetcher.get_stock_ohlcv_by_timeframe(
            code,
            timeframe,
            allow_live_intraday=allow_live_intraday,
        )
        if df.empty:
            return None

        symbol = SymbolInfo(
            code=code,
            name=name,
            market=market,
            sector=None,
            market_cap=await fetcher.get_market_cap(code),
            is_in_universe=True,
        )
        analysis = await analyze_symbol_dataframe(symbol, timeframe, df)
        result: dict[str, Any] = {
            "code": code,
            "name": name,
            "market": market,
            "timeframe": timeframe,
            "timeframe_label": analysis.timeframe_label,
            "pattern_type": analysis.patterns[0].pattern_type if analysis.patterns else None,
            "state": analysis.patterns[0].state if analysis.patterns else None,
            "setup_stage": "neutral",
            "p_up": analysis.p_up,
            "p_down": analysis.p_down,
            "textbook_similarity": analysis.textbook_similarity,
            "formation_quality": (
                0.28 * analysis.patterns[0].leg_balance_fit
                + 0.28 * analysis.patterns[0].reversal_energy_fit
                + 0.22 * analysis.patterns[0].breakout_quality_fit
                + 0.22 * analysis.patterns[0].retest_quality_fit
            ) if analysis.patterns else 0.0,
            "leg_balance_fit": analysis.patterns[0].leg_balance_fit if analysis.patterns else 0.0,
            "reversal_energy_fit": analysis.patterns[0].reversal_energy_fit if analysis.patterns else 0.0,
            "breakout_quality_fit": analysis.patterns[0].breakout_quality_fit if analysis.patterns else 0.0,
            "retest_quality_fit": analysis.patterns[0].retest_quality_fit if analysis.patterns else 0.0,
            "confidence": analysis.confidence,
            "entry_score": analysis.entry_score,
            "reward_risk_ratio": analysis.reward_risk_ratio,
            "headroom_score": analysis.headroom_score,
            "target_distance_pct": analysis.target_distance_pct,
            "stop_distance_pct": analysis.stop_distance_pct,
            "avg_mfe_pct": analysis.avg_mfe_pct,
            "avg_mae_pct": analysis.avg_mae_pct,
            "avg_bars_to_outcome": analysis.avg_bars_to_outcome,
            "historical_edge_score": analysis.historical_edge_score,
            "trend_alignment_score": analysis.trend_alignment_score,
            "trend_direction": analysis.trend_direction,
            "trend_warning": analysis.trend_warning,
            "wyckoff_phase": analysis.wyckoff_phase,
            "wyckoff_score": analysis.wyckoff_score,
            "wyckoff_note": analysis.wyckoff_note,
            "intraday_session_phase": analysis.intraday_session_phase,
            "intraday_session_score": analysis.intraday_session_score,
            "intraday_session_note": analysis.intraday_session_note,
            "action_plan": analysis.action_plan,
            "action_plan_label": analysis.action_plan_label,
            "action_plan_summary": analysis.action_plan_summary,
            "action_priority_score": analysis.action_priority_score,
            "risk_flags": analysis.risk_flags,
            "confirmation_checklist": analysis.confirmation_checklist,
            "next_trigger": analysis.next_trigger,
            "trade_readiness_score": analysis.trade_readiness_score,
            "trade_readiness_label": analysis.trade_readiness_label,
            "trade_readiness_summary": analysis.trade_readiness_summary,
            "entry_window_score": analysis.entry_window_score,
            "entry_window_label": analysis.entry_window_label,
            "entry_window_summary": analysis.entry_window_summary,
            "freshness_score": analysis.freshness_score,
            "freshness_label": analysis.freshness_label,
            "freshness_summary": analysis.freshness_summary,
            "reentry_score": analysis.reentry_score,
            "reentry_label": analysis.reentry_label,
            "reentry_summary": analysis.reentry_summary,
            "reentry_case": analysis.reentry_case,
            "reentry_case_label": analysis.reentry_case_label,
            "reentry_profile_key": analysis.reentry_profile_key,
            "reentry_profile_label": analysis.reentry_profile_label,
            "reentry_profile_summary": analysis.reentry_profile_summary,
            "reentry_trigger": analysis.reentry_trigger,
            "reentry_compression_score": analysis.reentry_compression_score,
            "reentry_volume_recovery_score": analysis.reentry_volume_recovery_score,
            "reentry_trigger_hold_score": analysis.reentry_trigger_hold_score,
            "reentry_wick_absorption_score": analysis.reentry_wick_absorption_score,
            "reentry_failure_burden_score": analysis.reentry_failure_burden_score,
            "reentry_factors": [factor.model_dump() for factor in analysis.reentry_factors],
            "score_factors": [factor.model_dump() for factor in analysis.score_factors],
            "active_setup_score": analysis.active_setup_score,
            "active_setup_label": analysis.active_setup_label,
            "active_setup_summary": analysis.active_setup_summary,
            "active_pattern_count": analysis.active_pattern_count,
            "completed_pattern_count": analysis.completed_pattern_count,
            "no_signal_flag": analysis.no_signal_flag,
            "reason_summary": analysis.reason_summary,
            "completion_proximity": analysis.completion_proximity,
            "recency_score": analysis.recency_score,
            "data_source": analysis.data_source,
            "data_quality": analysis.data_quality,
            "source_note": analysis.source_note,
            "fetch_status": analysis.fetch_status,
            "fetch_status_label": analysis.fetch_status_label,
            "fetch_message": analysis.fetch_message,
            "liquidity_score": analysis.liquidity_score,
            "avg_turnover_billion": analysis.avg_turnover_billion,
            "sample_size": analysis.sample_size,
            "empirical_win_rate": analysis.empirical_win_rate,
            "sample_reliability": analysis.sample_reliability,
            "stats_timeframe": analysis.stats_timeframe,
            "available_bars": analysis.available_bars,
        }

        if include_confluence:
            result.update(
                await _build_confluence(
                    code,
                    name,
                    market,
                    timeframe,
                    result,
                    force_refresh,
                    allow_live_intraday,
                )
            )
        else:
            result.update(
                {
                    "confluence_score": 0.5,
                    "confluence_summary": f"{timeframe_label(timeframe)} 단독 분석",
                    "scenario_text": f"{timeframe_label(timeframe)} 신호만 기준으로 계산한 보조 결과입니다.",
                    "composite_score": round(
                        0.60 * float(result["entry_score"])
                        + 0.16 * float(result["sample_reliability"])
                        + 0.10 * float(result["historical_edge_score"])
                        + 0.14 * float(result["headroom_score"])
                        + 0.10 * float(result["trend_alignment_score"])
                        + 0.08 * float(result.get("wyckoff_score", 0.0))
                        + 0.06 * float(result.get("intraday_session_score", 0.5))
                        + 0.10 * min(1.0, float(result["reward_risk_ratio"]) / 2.5),
                        3,
                    ),
                }
            )

        result = _apply_setup_metadata(result)
        if timeframe in {"1m", "15m", "30m", "60m"}:
            result["live_intraday_priority_score"] = round(_live_intraday_priority(result, timeframe), 3)
            result["live_intraday_candidate"] = False
            result["live_intraday_reason"] = ""
            result["non_live_intraday_reason"] = ""
            result["intraday_collection_mode"] = "budget"
        await cache_set(cache_key, result, ttl=1800)
        return result
    except Exception as exc:
        logger.warning("Scan failed for %s (%s): %s", code, timeframe, exc)
        return None


async def _select_candidates(limit: int, timeframe: str) -> tuple[list[tuple[str, str, str]], str, set[str], str]:
    if timeframe in {"1d", "1wk", "1mo"}:
        return await _fetch_universe_codes(limit), "krx_universe", set(), "neutral"

    seed_limit = max(settings.intraday_seed_limit, limit * settings.intraday_seed_multiplier)
    daily_candidates = await get_scan_results("1d")
    daily_candidates = [
        row
        for row in daily_candidates
        if row.get("entry_score", 0) >= 0.45
        and row.get("confidence", 0) >= 0.30
        and row.get("action_plan") != "cooling"
    ]
    daily_candidates.sort(
        key=lambda row: (
            row.get("composite_score", 0),
            row.get("historical_edge_score", 0),
            row.get("sample_reliability", 0),
            row.get("entry_score", 0),
            row.get("data_quality", 0),
            row.get("liquidity_score", 0),
        ),
        reverse=True,
    )

    if daily_candidates:
        selected_rows = daily_candidates[:seed_limit]
        selected = [(row["code"], row["name"], row.get("market", "KRX")) for row in selected_rows]
        live_limit, live_phase = _effective_live_intraday_limit(timeframe, len(selected_rows))
        live_priority_rows = sorted(
            selected_rows,
            key=lambda row: (
                _live_intraday_priority(row, timeframe),
                row.get("composite_score", 0.0),
                row.get("historical_edge_score", 0.0),
            ),
            reverse=True,
        )
        live_codes = {str(row["code"]) for row in live_priority_rows[:live_limit]}
        return selected, "daily_seed", live_codes, live_phase

    fallback = await _fetch_universe_codes(seed_limit)
    live_limit, live_phase = _effective_live_intraday_limit(timeframe, len(fallback))
    live_codes = {code for code, _, _ in fallback[:live_limit]}
    return fallback, "krx_universe_fallback", live_codes, live_phase


async def run_scan(
    timeframe: str = DEFAULT_TIMEFRAME,
    limit: int = 100,
    batch_size: int = 10,
    force_refresh: bool = False,
    source: str = "scheduled",
) -> list[dict[str, Any]]:
    started_at = datetime.utcnow()
    cache_key = _full_scan_cache_key(timeframe)

    async with _scan_lock:
        _update_scan_status(
            timeframe,
            status="running",
            is_running=True,
            source=source,
            last_started_at=started_at.isoformat(),
            last_error=None,
            duration_ms=None,
        )

        if force_refresh:
            await cache_delete(cache_key)

        cached = None if force_refresh else await cache_get(cache_key)
        if cached:
            _update_scan_status(
                timeframe,
                status="ready",
                is_running=False,
                cached_result_count=len(cached),
                last_finished_at=_utc_now_iso(),
                duration_ms=int((datetime.utcnow() - started_at).total_seconds() * 1000),
            )
            return cached

        try:
            universe, candidate_source, live_codes, live_phase = await _select_candidates(limit, timeframe)
            _update_scan_status(
                timeframe,
                universe_size=len(universe),
                candidate_source=candidate_source,
                candidate_count=len(universe),
                intraday_live_candidate_limit=(len(live_codes) if timeframe in {"1m", "15m", "30m", "60m"} else None),
                intraday_live_candidate_count=(len(live_codes) if timeframe in {"1m", "15m", "30m", "60m"} else None),
                intraday_live_phase=(live_phase if timeframe in {"1m", "15m", "30m", "60m"} else None),
            )

            results: list[dict[str, Any]] = []
            for index in range(0, len(universe), batch_size):
                batch = universe[index:index + batch_size]
                tasks = [
                    _analyze_one(
                        code,
                        name,
                        market,
                        timeframe,
                        force_refresh=force_refresh,
                        allow_live_intraday=(code in live_codes) if timeframe in {"1m", "15m", "30m", "60m"} else True,
                    )
                    for code, name, market in batch
                ]
                batch_results = await asyncio.gather(*tasks, return_exceptions=True)
                for item in batch_results:
                    if isinstance(item, dict):
                        if timeframe in {"1m", "15m", "30m", "60m"}:
                            item["live_intraday_candidate"] = item.get("code") in live_codes
                            item["live_intraday_reason"] = (
                                _live_intraday_reason(item, timeframe, live_phase)
                                if item["live_intraday_candidate"]
                                else ""
                            )
                            item["non_live_intraday_reason"] = (
                                ""
                                if item["live_intraday_candidate"]
                                else _non_live_intraday_reason(item, timeframe, live_phase, len(live_codes))
                            )
                            item["intraday_collection_mode"] = _intraday_collection_mode(item)
                        results.append(item)
                await asyncio.sleep(0.08)

            results.sort(
                key=lambda row: (
                        0 if row["no_signal_flag"] else 1,
                        row.get("trade_readiness_score", 0),
                        row.get("entry_window_score", 0),
                        row.get("freshness_score", 0),
                        row.get("reentry_score", 0),
                        row.get("active_setup_score", 0),
                    row.get("composite_score", 0),
                    row.get("historical_edge_score", 0),
                    row.get("sample_reliability", 0),
                    row.get("entry_score", 0),
                    row.get("data_quality", 0),
                    row.get("liquidity_score", 0),
                    row.get("textbook_similarity", 0),
                ),
                reverse=True,
            )
            await cache_set(cache_key, results, ttl=settings.dashboard_cache_ttl * 20)
            finished_at = datetime.utcnow()
            _update_scan_status(
                timeframe,
                status="ready",
                is_running=False,
                cached_result_count=len(results),
                last_finished_at=finished_at.isoformat(),
                duration_ms=int((finished_at - started_at).total_seconds() * 1000),
            )
            return results
        except Exception as exc:
            finished_at = datetime.utcnow()
            _update_scan_status(
                timeframe,
                status="error",
                is_running=False,
                last_error=str(exc),
                last_finished_at=finished_at.isoformat(),
                duration_ms=int((finished_at - started_at).total_seconds() * 1000),
            )
            logger.exception("Market scan crashed")
            raise


async def trigger_scan(
    timeframe: str = DEFAULT_TIMEFRAME,
    limit: int = 100,
    batch_size: int = 10,
    force_refresh: bool = True,
    source: str = "manual",
) -> dict[str, Any]:
    task = _scan_tasks.get(timeframe)
    if task and not task.done():
        status = await get_scan_status(timeframe)
        status["trigger_accepted"] = False
        return status

    _scan_tasks[timeframe] = asyncio.create_task(
        run_scan(timeframe=timeframe, limit=limit, batch_size=batch_size, force_refresh=force_refresh, source=source)
    )
    status = await get_scan_status(timeframe)
    status["status"] = "queued"
    status["is_running"] = True
    status["source"] = source
    status["last_started_at"] = _utc_now_iso()
    status["trigger_accepted"] = True
    return status


async def get_scan_results(timeframe: str = DEFAULT_TIMEFRAME) -> list[dict[str, Any]]:
    cache_key = _full_scan_cache_key(timeframe)
    cached = await cache_get(cache_key)
    if cached:
        _update_scan_status(timeframe, status="ready", cached_result_count=len(cached))
        return cached

    _update_scan_status(timeframe, status="warming", is_running=False, source="fallback")
    fallback = FALLBACK_CODES if timeframe == "1d" else FALLBACK_CODES[: min(len(FALLBACK_CODES), settings.intraday_seed_limit)]
    intraday_live_limit, intraday_live_phase = (
        _effective_live_intraday_limit(timeframe, len(fallback))
        if timeframe in {"1m", "15m", "30m", "60m"}
        else (0, "neutral")
    )
    fallback_live_codes = (
        {code for code, _, _ in fallback[:intraday_live_limit]}
        if timeframe in {"1m", "15m", "30m", "60m"}
        else set()
    )
    quick = await asyncio.gather(
        *[
            _analyze_one(
                code,
                name,
                market,
                timeframe,
                allow_live_intraday=(code in fallback_live_codes) if timeframe in {"1m", "15m", "30m", "60m"} else True,
            )
            for code, name, market in fallback
        ],
        return_exceptions=True,
    )
    results = [item for item in quick if isinstance(item, dict)]
    if timeframe in {"1m", "15m", "30m", "60m"}:
        for item in results:
            item["live_intraday_candidate"] = item.get("code") in fallback_live_codes
            item["live_intraday_reason"] = (
                _live_intraday_reason(item, timeframe, intraday_live_phase)
                if item["live_intraday_candidate"]
                else ""
            )
            item["non_live_intraday_reason"] = (
                ""
                if item["live_intraday_candidate"]
                else _non_live_intraday_reason(item, timeframe, intraday_live_phase, intraday_live_limit)
            )
            item["intraday_collection_mode"] = _intraday_collection_mode(item)
    results.sort(
        key=lambda row: (
            row.get("trade_readiness_score", 0),
            row.get("entry_window_score", 0),
            row.get("freshness_score", 0),
            row.get("reentry_score", 0),
            row.get("active_setup_score", 0),
            row.get("composite_score", row.get("entry_score", 0)),
            row.get("historical_edge_score", 0),
            row.get("sample_reliability", 0),
        ),
        reverse=True,
    )
    await cache_set(cache_key, results, ttl=300)
    _update_scan_status(
        timeframe,
        status="ready",
        cached_result_count=len(results),
        universe_size=len(fallback),
        candidate_source="fallback",
        candidate_count=len(fallback),
        intraday_live_candidate_limit=(intraday_live_limit if timeframe in {"1m", "15m", "30m", "60m"} else None),
        intraday_live_candidate_count=(intraday_live_limit if timeframe in {"1m", "15m", "30m", "60m"} else None),
        intraday_live_phase=(intraday_live_phase if timeframe in {"1m", "15m", "30m", "60m"} else None),
        last_finished_at=_utc_now_iso(),
        source="fallback",
    )

    task = _scan_tasks.get(timeframe)
    if not task or task.done():
        await trigger_scan(timeframe=timeframe, force_refresh=False, source="background")

    return results
