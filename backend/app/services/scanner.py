"""
Market scanner for dashboard and screener results.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd

from ..api.schemas import SymbolInfo
from ..core.config import get_settings
from ..core.redis import cache_get, cache_set
from .analysis_service import analyze_symbol_dataframe, build_no_signal_snapshot
from .data_fetcher import get_data_fetcher
from .scan_history_service import persist_scan_history
from .timeframe_service import DEFAULT_TIMEFRAME, is_intraday_timeframe, resolve_daily_reference_date, timeframe_label

logger = logging.getLogger(__name__)
settings = get_settings()
INTRADAY_SCAN_BATCH_SIZE = 4
INTRADAY_QUICK_SCAN_BATCH_SIZE = 3

FALLBACK_CODES: list[tuple[str, str, str]] = [
    # KOSPI 대형주 (시총 상위)
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
    ("105560", "KB금융", "KOSPI"),
    ("055550", "신한지주", "KOSPI"),
    ("086790", "하나금융지주", "KOSPI"),
    ("316140", "우리금융지주", "KOSPI"),
    ("032830", "삼성생명", "KOSPI"),
    ("003550", "LG", "KOSPI"),
    ("012330", "현대모비스", "KOSPI"),
    ("028260", "삼성물산", "KOSPI"),
    ("034730", "SK", "KOSPI"),
    ("017670", "SK텔레콤", "KOSPI"),
    ("030200", "KT", "KOSPI"),
    ("015760", "한국전력", "KOSPI"),
    ("096770", "SK이노베이션", "KOSPI"),
    ("066570", "LG전자", "KOSPI"),
    ("000100", "유한양행", "KOSPI"),
    ("018260", "삼성에스디에스", "KOSPI"),
    ("009150", "삼성전기", "KOSPI"),
    ("011200", "HMM", "KOSPI"),
    ("010950", "S-Oil", "KOSPI"),
    ("000720", "현대건설", "KOSPI"),
    ("097950", "CJ제일제당", "KOSPI"),
    ("021240", "코웨이", "KOSPI"),
    ("024110", "기업은행", "KOSPI"),
    ("139480", "이마트", "KOSPI"),
    ("180640", "한진칼", "KOSPI"),
    ("003490", "대한항공", "KOSPI"),
    ("004020", "현대제철", "KOSPI"),
    ("010140", "삼성중공업", "KOSPI"),
    ("042660", "한화오션", "KOSPI"),
    ("009830", "한화솔루션", "KOSPI"),
    ("047050", "포스코인터내셔널", "KOSPI"),
    ("005490", "POSCO홀딩스", "KOSPI"),
    ("000810", "삼성화재", "KOSPI"),
    ("090139", "LG생활건강", "KOSPI"),
    ("051900", "LG생활건강", "KOSPI"),
    ("373220", "LG에너지솔루션", "KOSPI"),
    ("329180", "현대중공업", "KOSPI"),
    ("267250", "HD현대", "KOSPI"),
    ("138040", "메리츠금융지주", "KOSPI"),
    ("000150", "두산에너빌리티", "KOSPI"),
    ("033780", "KT&G", "KOSPI"),
    ("003620", "KCC", "KOSPI"),
    ("011780", "금호석유", "KOSPI"),
    ("007070", "GS리테일", "KOSPI"),
    ("078930", "GS", "KOSPI"),
    ("004170", "신세계", "KOSPI"),
    ("271560", "오리온", "KOSPI"),
    ("282330", "BGF리테일", "KOSPI"),
    ("161390", "한국타이어앤테크놀로지", "KOSPI"),
    ("000120", "CJ대한통운", "KOSPI"),
    ("006360", "GS건설", "KOSPI"),
    ("000080", "하이트진로", "KOSPI"),
    ("002790", "아모레퍼시픽그룹", "KOSPI"),
    ("090430", "아모레퍼시픽", "KOSPI"),
    ("302440", "SK바이오사이언스", "KOSPI"),
    ("377300", "카카오페이", "KOSPI"),
    ("035900", "JYP Ent.", "KOSPI"),
    ("041960", "블리자드코리아", "KOSPI"),
    ("352820", "하이브", "KOSPI"),
    ("041510", "에스엠", "KOSPI"),
    # KOSDAQ 주요 종목
    ("247540", "에코프로비엠", "KOSDAQ"),
    ("086520", "에코프로", "KOSDAQ"),
    ("091990", "셀트리온헬스케어", "KOSDAQ"),
    ("263750", "펄어비스", "KOSDAQ"),
    ("112040", "위메이드", "KOSDAQ"),
    ("293490", "카카오게임즈", "KOSDAQ"),
    ("357780", "솔브레인", "KOSDAQ"),
    ("196170", "알테오젠", "KOSDAQ"),
    ("214150", "클래시스", "KOSDAQ"),
    ("041130", "에코프로에이치엔", "KOSDAQ"),
    ("240810", "원익IPS", "KOSDAQ"),
    ("054040", "한국컴퓨터", "KOSDAQ"),
    ("035900", "JYP Ent.", "KOSDAQ"),
    ("122870", "와이지엔터테인먼트", "KOSDAQ"),
    ("131290", "카이노스메드", "KOSDAQ"),
    ("039030", "이오테크닉스", "KOSDAQ"),
    ("039200", "오스코텍", "KOSDAQ"),
    ("095340", "ISC", "KOSDAQ"),
    ("108320", "LX세미콘", "KOSDAQ"),
    ("256840", "한국비엔씨", "KOSDAQ"),
    ("030270", "이노에이스", "KOSDAQ"),
    ("078160", "메디포스트", "KOSDAQ"),
    ("036930", "주성엔지니어링", "KOSDAQ"),
    ("237690", "에스티팜", "KOSDAQ"),
    ("064760", "티씨케이", "KOSDAQ"),
    ("093320", "케이씨에스", "KOSDAQ"),
    ("950130", "엑스페릭스", "KOSDAQ"),
    ("145720", "덴티움", "KOSDAQ"),
    ("060280", "큐렉소", "KOSDAQ"),
    ("035080", "인터파크트리플", "KOSDAQ"),
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
_quick_scan_tasks: dict[str, asyncio.Task] = {}
_scan_status: dict[str, dict[str, Any]] = {}
_KST = ZoneInfo("Asia/Seoul")
WATCHLIST_CACHE_KEY = "watchlist:v1:default"


def _full_scan_cache_key(timeframe: str) -> str:
    return f"scanner:v10:full_results:{timeframe}"


def _single_scan_cache_key(timeframe: str, code: str, allow_live_intraday: bool = True) -> str:
    mode = "live" if allow_live_intraday else "budget"
    return f"scan:v15:result:{timeframe}:{code}:{mode}"


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


def _status_snapshot(timeframe: str) -> dict[str, Any]:
    return dict(_scan_status.get(timeframe, _status_template(timeframe)))


def _fallback_universe_rows(universe, limit: int) -> list[tuple[str, str, str]]:
    seen: set[str] = set()
    ordered: list[tuple[str, str, str]] = []
    universe_map = (
        {
            str(row["code"]): (
                str(row["code"]),
                str(row.get("name") or row["code"]),
                str(row.get("market") or "KRX"),
            )
            for _, row in universe.iterrows()
        }
        if universe is not None and not universe.empty
        else {}
    )

    for code, name, market in FALLBACK_CODES:
        preferred = universe_map.get(code, (code, name, market))
        if preferred[0] in seen:
            continue
        seen.add(preferred[0])
        ordered.append(preferred)
        if len(ordered) >= limit:
            return ordered

    if universe is None or universe.empty:
        return ordered[:limit]

    for _, row in universe.iterrows():
        code = str(row["code"])
        if code in seen:
            continue
        seen.add(code)
        ordered.append(
            (
                code,
                str(row.get("name") or code),
                str(row.get("market") or "KRX"),
            )
        )
        if len(ordered) >= limit:
            break

    return ordered[:limit]


async def _load_watchlist_rows() -> list[tuple[str, str, str]]:
    stored = await cache_get(WATCHLIST_CACHE_KEY)
    if not isinstance(stored, list):
        return []

    rows: list[tuple[str, str, str]] = []
    seen: set[str] = set()
    for item in stored:
        if not isinstance(item, dict):
            continue
        code = str(item.get("code") or "").strip()
        if not code or code in seen:
            continue
        rows.append(
            (
                code,
                str(item.get("name") or code),
                str(item.get("market") or "KRX"),
            )
        )
        seen.add(code)
    return rows


def _merge_priority_rows(
    base_rows: list[tuple[str, str, str]],
    priority_rows: list[tuple[str, str, str]],
    *,
    limit: int,
) -> tuple[list[tuple[str, str, str]], int]:
    effective_limit = max(limit, len(priority_rows))
    merged: list[tuple[str, str, str]] = []
    seen: set[str] = set()
    priority_codes = {code for code, _, _ in priority_rows}

    for row in [*priority_rows, *base_rows]:
        code = str(row[0])
        if code in seen:
            continue
        seen.add(code)
        merged.append(row)
        if len(merged) >= effective_limit:
            break

    included_priority = sum(1 for code, _, _ in merged if code in priority_codes)
    return merged, included_priority


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
    task = _scan_tasks.get(timeframe)
    if task and not task.done():
        status["is_running"] = True
        status["status"] = "warming" if status.get("cached_result_count", 0) > 0 else "queued"
    return status


class _KrxCooldownActive(Exception):
    """KRX 서킷브레이커 활성 — pykrx 시도 자체를 건너뛰는 제어 흐름용."""


# 스캔 로테이션: 시총 상위 고정 헤드는 매번 스캔하고, 나머지 유니버스는 커서를
# 옮겨가며 순환한다 — limit이 작아도(free tier 메모리 제약) 수일에 걸쳐 전 종목 커버.
_ROTATION_FIXED_HEAD = 50
_ROTATION_CURSOR_KEY = "scan:universe-rotation-cursor:v1"

# 병합 결과 상한 — Upstash 요청 크기(1MB) 보호 (행당 ~3KB 가정)
_MERGED_RESULTS_MAX = 250


async def _rotate_scan_slice(
    ordered: list[tuple[str, str, str]], limit: int
) -> list[tuple[str, str, str]]:
    """정렬된 유니버스에서 이번 스캔 대상 슬라이스를 고른다 (고정 헤드 + 회전부)."""
    if limit <= 0:
        return []
    if len(ordered) <= limit:
        return list(ordered)

    head_count = min(_ROTATION_FIXED_HEAD, max(0, limit // 2))
    fixed = ordered[:head_count]
    tail = ordered[head_count:]
    rotation_size = limit - head_count

    cursor = 0
    try:
        raw = await cache_get(_ROTATION_CURSOR_KEY)
        if raw is not None:
            cursor = int(raw) % len(tail)
    except (TypeError, ValueError):
        cursor = 0

    rotating = (tail[cursor:] + tail[:cursor])[:rotation_size]
    try:
        await cache_set(_ROTATION_CURSOR_KEY, (cursor + rotation_size) % len(tail), ttl=7 * 24 * 3600)
    except Exception:
        pass
    return fixed + rotating


def _scan_row_sort_key(row: dict[str, Any]) -> tuple:
    return (
        0 if row.get("no_signal_flag") else 1,
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
    )


def _merge_scan_results(
    previous: Any, fresh: list[dict[str, Any]], *, max_age_hours: int = 48
) -> list[dict[str, Any]]:
    """로테이션 스캔용 병합: 이번 결과 + 이전 스캔의 (이번에 안 돈) 신호 종목.

    - 같은 코드는 fresh 우선
    - 이전 행은 신호 있는 행만, scanned_at이 max_age_hours 이내인 것만 유지
      (no_signal 행은 다음 로테이션에서 다시 돌게 두고 캐시 크기를 아낀다)
    - 플레이스홀더 행 제거, 전체 상한 _MERGED_RESULTS_MAX
    """
    now = _utc_now_iso()
    for row in fresh:
        row.setdefault("scanned_at", now)

    if not isinstance(previous, list):
        merged = list(fresh)
    else:
        fresh_codes = {str(row.get("code")) for row in fresh}
        cutoff = datetime.utcnow() - timedelta(hours=max_age_hours)
        carried: list[dict[str, Any]] = []
        for row in previous:
            if not isinstance(row, dict):
                continue
            if str(row.get("code")) in fresh_codes:
                continue
            if row.get("data_source") == "placeholder_seed":
                continue
            if row.get("no_signal_flag", True):
                continue
            ts_raw = row.get("scanned_at")
            if not ts_raw:
                continue
            try:
                if datetime.fromisoformat(str(ts_raw)) < cutoff:
                    continue
            except ValueError:
                continue
            carried.append(row)
        merged = list(fresh) + carried

    merged.sort(key=_scan_row_sort_key, reverse=True)
    return merged[:_MERGED_RESULTS_MAX]


async def _fetch_universe_codes(limit: int = 100) -> tuple[list[tuple[str, str, str]], str]:
    fetcher = get_data_fetcher()
    universe = await fetcher.get_universe()
    watchlist_rows = await _load_watchlist_rows()

    # pykrx/FDR 모두 실패한 경우 FALLBACK_CODES를 최소 universe로 사용
    # → static_fallback 대신 FDR fallback 경로를 탈 수 있도록 함
    if universe is None or universe.empty:
        logger.warning(
            "get_universe() returned empty; using %d FALLBACK_CODES as minimal universe",
            len(FALLBACK_CODES),
        )
        universe = pd.DataFrame(
            [{"code": c, "market": m, "name": n, "market_cap": None} for c, n, m in FALLBACK_CODES]
        )

    universe_names = {
        str(row["code"]): row.get("name", row["code"]) or row["code"]
        for _, row in universe.iterrows()
    }

    try:
        from .data_fetcher import krx_in_cooldown, mark_krx_cooldown

        if await krx_in_cooldown():
            raise _KrxCooldownActive("KRX cooldown active — skipping pykrx market-cap")

        from pykrx import stock as krx

        reference_day, _ = resolve_daily_reference_date()
        today = reference_day.strftime("%Y%m%d")
        rows: list[tuple[str, str, str, float, float]] = []  # code, name, market, mktcap, turnover

        for market in ("KOSPI", "KOSDAQ"):
            cap_df = await asyncio.wait_for(
                asyncio.to_thread(krx.get_market_cap_by_ticker, today, market=market),
                timeout=25.0,  # 시장별 타임아웃 — 첫 호출은 KRX 로그인 포함이라 여유 확보
            )
            if cap_df is None or cap_df.empty:
                continue
            market_cap_col = next((column for column in ("시가총액", "MarketCap", "market_cap") if column in cap_df.columns), None)
            if market_cap_col is None:
                raise KeyError(f"market cap column missing: {list(cap_df.columns)}")
            turnover_col = next((col for col in ("거래대금",) if col in cap_df.columns), None)
            for code, row in cap_df.iterrows():
                market_cap = float(row.get(market_cap_col, 0)) / 1e8
                if market_cap < settings.min_market_cap_billion:
                    continue
                code_str = str(code)
                turnover = float(row.get(turnover_col, 0)) if turnover_col else 0.0
                rows.append((code_str, universe_names.get(code_str, code_str), market, market_cap, turnover))

        if rows:
            # Liquidity filter: remove bottom 52% by single-day trading value (거래대금).
            # Stocks with thin liquidity often disconnect from chart patterns because
            # the bid-ask spread can't support normal position sizing.
            # Percentile is computed across the full market-cap-filtered universe so
            # the threshold reflects a true market-wide ranking.
            turnovers = [r[4] for r in rows]
            if any(t > 0 for t in turnovers):
                sorted_turnovers = sorted(turnovers)
                threshold = max(1.0, sorted_turnovers[int(len(sorted_turnovers) * 0.52)])
                before = len(rows)
                rows = [r for r in rows if r[4] >= threshold]
                logger.info(
                    "Liquidity filter applied: %d → %d stocks (bottom 52%% removed, threshold %.0f만원/day)",
                    before, len(rows), threshold / 10_000,
                )

            rows.sort(key=lambda item: item[3], reverse=True)
            ordered_full = [(code, name, market) for code, name, market, _, _ in rows]
            result = await _rotate_scan_slice(ordered_full, limit)
            result, watchlist_included = _merge_priority_rows(result, watchlist_rows, limit=limit)
            logger.info(
                "Universe loaded: %d stocks via pykrx market-cap (limit=%d, watchlist_included=%d)",
                len(result),
                limit,
                watchlist_included,
            )
            return result, "krx_universe+watchlist" if watchlist_included else "krx_universe"
    except _KrxCooldownActive as exc:
        logger.info("%s", exc)
    except Exception as exc:
        try:
            from .data_fetcher import mark_krx_cooldown as _mark
            await _mark(f"market-cap: {exc}")
        except Exception:
            pass
        logger.warning("Bulk market-cap universe fetch failed: %s", exc)

    if universe is not None and not universe.empty:
        ordered_full = _fallback_universe_rows(universe, len(universe) + len(FALLBACK_CODES))
        result = await _rotate_scan_slice(ordered_full, limit)
        result, watchlist_included = _merge_priority_rows(result, watchlist_rows, limit=limit)
        logger.warning(
            "Universe fallback: using broad FDR/pykrx universe (%d stocks, limit=%d). "
            "pykrx market-cap fetch failed — check network/market hours.",
            len(result), limit,
        )
        return result, "krx_universe_fdr+watchlist" if watchlist_included else "krx_universe_fdr"

    logger.error(
        "Universe STATIC FALLBACK: only %d hardcoded stocks will be scanned. "
        "pykrx AND FDR universe both failed. Full market scan is NOT running.",
        len(FALLBACK_CODES[:limit]),
    )
    result, watchlist_included = _merge_priority_rows(FALLBACK_CODES[:limit], watchlist_rows, limit=limit)
    return result, "static_fallback+watchlist" if watchlist_included else "static_fallback"


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
            f"{timeframe_label(timeframe)} 신호는 유지되지만 상위 축 정렬은 절반 정도입니다. 손절 기준가를 우선 보는 편이 좋습니다."
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
        analysis = await analyze_symbol_dataframe(symbol, timeframe, df, fetch_money_flow=False)
        signal_price = float(df["close"].iloc[-1]) if "close" in df.columns and not df.empty else None
        reference_day, _ = resolve_daily_reference_date()
        result = _analysis_to_scan_row(
            analysis,
            code=code,
            name=name,
            market=market,
            timeframe=timeframe,
            signal_price=signal_price,
            reference_date=reference_day.isoformat() if not is_intraday_timeframe(timeframe) else _kst_now().date().isoformat(),
        )

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
    watchlist_rows = await _load_watchlist_rows()
    watch_codes = {code for code, _, _ in watchlist_rows}
    if timeframe in {"1d", "1wk", "1mo"}:
        codes, universe_source = await _fetch_universe_codes(limit)
        return codes, universe_source, set(), "neutral"

    seed_limit = max(settings.intraday_seed_limit, limit * settings.intraday_seed_multiplier)
    daily_candidates = await get_scan_results("1d")
    daily_candidates = [
        row
        for row in daily_candidates
        if (
            str(row.get("code") or "") in watch_codes
            or (
                row.get("entry_score", 0) >= 0.45
                and row.get("confidence", 0) >= 0.30
                and row.get("action_plan") != "cooling"
            )
        )
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
        selected, watchlist_included = _merge_priority_rows(selected, watchlist_rows, limit=seed_limit)
        row_map = {str(row["code"]): row for row in daily_candidates}
        live_limit, live_phase = _effective_live_intraday_limit(timeframe, len(selected))
        live_priority_rows = sorted(
            [row_map.get(code) for code, _, _ in selected if row_map.get(code)],
            key=lambda row: (
                _live_intraday_priority(row, timeframe),
                row.get("composite_score", 0.0),
                row.get("historical_edge_score", 0.0),
            ),
            reverse=True,
        )
        live_codes = {str(row["code"]) for row in live_priority_rows[:live_limit]}
        return selected, "daily_seed+watchlist" if watchlist_included else "daily_seed", live_codes, live_phase

    fallback, fallback_source = await _fetch_universe_codes(seed_limit)
    live_limit, live_phase = _effective_live_intraday_limit(timeframe, len(fallback))
    live_codes = {code for code, _, _ in fallback[:live_limit]}
    return fallback, fallback_source, live_codes, live_phase


def _effective_batch_size(timeframe: str, requested: int, *, quick: bool = False) -> int:
    if timeframe not in {"1m", "15m", "30m", "60m"}:
        return max(1, requested)
    limit = INTRADAY_QUICK_SCAN_BATCH_SIZE if quick else INTRADAY_SCAN_BATCH_SIZE
    return max(1, min(requested, limit))


def _scan_workload_defaults(source: str) -> tuple[int, int]:
    if source == "scheduled":
        return settings.scheduled_scan_limit, settings.scheduled_scan_batch_size
    if source == "manual":
        return settings.manual_scan_limit, settings.manual_scan_batch_size
    return settings.background_scan_limit, settings.background_scan_batch_size


def _decorate_intraday_result(
    item: dict[str, Any],
    timeframe: str,
    *,
    live_codes: set[str],
    live_phase: str,
) -> dict[str, Any]:
    item["live_intraday_candidate"] = item.get("code") in live_codes
    item["live_intraday_reason"] = _live_intraday_reason(item, timeframe, live_phase) if item["live_intraday_candidate"] else ""
    item["non_live_intraday_reason"] = (
        ""
        if item["live_intraday_candidate"]
        else _non_live_intraday_reason(item, timeframe, live_phase, len(live_codes))
    )
    item["intraday_collection_mode"] = _intraday_collection_mode(item)
    return item


def _analysis_to_scan_row(
    analysis: Any,
    *,
    code: str,
    name: str,
    market: str,
    timeframe: str,
    signal_price: float | None = None,
    reference_date: str | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "code": code,
        "name": name,
        "market": market,
        "timeframe": timeframe,
        "timeframe_label": analysis.timeframe_label,
        "signal_price": signal_price,
        "reference_date": reference_date,
        "pattern_type": analysis.patterns[0].pattern_type if analysis.patterns else None,
        "state": analysis.patterns[0].state if analysis.patterns else None,
        "trigger_level": analysis.patterns[0].neckline if analysis.patterns else None,
        "invalidation_level": analysis.patterns[0].invalidation_level if analysis.patterns else None,
        "target_level": analysis.patterns[0].target_level if analysis.patterns else None,
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
    return result


def _placeholder_frame() -> pd.DataFrame:
    df = pd.DataFrame()
    df.attrs.update(
        {
            "data_source": "placeholder_seed",
            "fetch_status": "placeholder_pending",
            "fetch_message": "빠른 예열 후보입니다. 백그라운드 분봉 스캔이 끝나면 실제 결과로 자동 교체됩니다.",
            "available_bars": 0,
        }
    )
    return df


def _build_placeholder_scan_results(timeframe: str, fallback: list[tuple[str, str, str]]) -> list[dict[str, Any]]:
    placeholder_df = _placeholder_frame()
    results: list[dict[str, Any]] = []
    for code, name, market in fallback:
        symbol = SymbolInfo(
            code=code,
            name=name,
            market=market,
            sector=None,
            market_cap=None,
            is_in_universe=True,
        )
        analysis = build_no_signal_snapshot(symbol, timeframe, placeholder_df)
        row = _analysis_to_scan_row(analysis, code=code, name=name, market=market, timeframe=timeframe)
        row.update(
            {
                "setup_stage": "placeholder_watch",
                "confluence_score": 0.18,
                "confluence_summary": f"{timeframe_label(timeframe)} 빠른 예열 후보",
                "scenario_text": "백그라운드 분봉 스캔이 끝나면 실제 패턴·확률·준비도 계산으로 자동 교체됩니다.",
                "composite_score": round(0.12 + 0.04 * max(0, len(fallback) - len(results)), 3),
            }
        )
        results.append(row)
    return results


async def _enrich_money_flow_alignment(rows: list[dict[str, Any]], top_n: int = 30) -> None:
    """상위 후보에 수급 정렬(외인/기관 vs 패턴 방향)을 붙이고 랭킹 보정치 기록.

    aligned +0.05 / diverged -0.05 / mixed -0.02 — 대시보드 정렬에서
    trade_readiness_score에 더해져 수급이 패턴을 지지하는 후보를 위로 올린다.
    수급 데이터는 4시간 Redis 캐시(KIS)라 스캔당 추가 비용이 작고, 실패는 무시.
    """
    from .money_flow_service import get_money_flow

    bonus = {"aligned": 0.05, "diverged": -0.05, "mixed": -0.02}
    for row in rows[:top_n]:
        pattern_type = row.get("pattern_type")
        if not pattern_type or row.get("no_signal_flag"):
            continue
        code = str(row.get("code") or "").strip()
        if not code:
            continue
        try:
            flow = await get_money_flow(code, pattern_type)
        except Exception:
            continue
        if not flow:
            continue
        alignment = str(flow.get("alignment", "neutral"))
        row["money_flow_alignment"] = alignment
        row["money_flow_rank_boost"] = bonus.get(alignment, 0.0)


async def run_scan(
    timeframe: str = DEFAULT_TIMEFRAME,
    limit: int | None = None,
    batch_size: int | None = None,
    force_refresh: bool = False,
    source: str = "scheduled",
) -> list[dict[str, Any]]:
    started_at = datetime.utcnow()
    cache_key = _full_scan_cache_key(timeframe)
    default_limit, default_batch_size = _scan_workload_defaults(source)
    scan_limit = max(1, int(limit or default_limit))
    scan_batch_size = max(1, int(batch_size or default_batch_size))
    max_duration_seconds = (
        settings.scheduled_scan_max_duration_seconds
        if source == "scheduled"
        else settings.scan_max_duration_seconds
    )

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

        previous_cached = await cache_get(cache_key)
        if force_refresh and isinstance(previous_cached, list):
            _update_scan_status(timeframe, cached_result_count=len(previous_cached))

        # 플레이스홀더 캐시는 진짜 분석 결과가 아니므로 재스캔 필요
        _is_placeholder_cache = (
            isinstance(previous_cached, list)
            and len(previous_cached) > 0
            and previous_cached[0].get("data_source") == "placeholder_seed"
        )
        # 캐시 종목 수가 너무 적으면 (이전 불완전 스캔 잔재) 재스캔
        _MIN_VALID_SCAN_COUNT = 20
        _is_insufficient_cache = (
            isinstance(previous_cached, list)
            and len(previous_cached) < _MIN_VALID_SCAN_COUNT
            and not force_refresh  # force_refresh=True면 이미 재스캔 예정이므로 중복 체크 불필요
        )
        if _is_insufficient_cache:
            logger.warning(
                "Cached scan for %s has only %d items (< %d) — treating as incomplete, forcing rescan",
                timeframe, len(previous_cached) if isinstance(previous_cached, list) else 0, _MIN_VALID_SCAN_COUNT,
            )
        cached = None if (force_refresh or _is_placeholder_cache or _is_insufficient_cache) else previous_cached
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
            universe, candidate_source, live_codes, live_phase = await _select_candidates(scan_limit, timeframe)
            # Capture locally so concurrent cold-start calls cannot overwrite these
            # values in _scan_status before we reach the final status update.
            _universe_size = len(universe)
            _candidate_count = len(universe)
            _candidate_source = candidate_source
            _update_scan_status(
                timeframe,
                universe_size=len(universe),
                candidate_source=candidate_source,
                candidate_count=len(universe),
                scanned_count=0,  # 진행률 초기화
                intraday_live_candidate_limit=(len(live_codes) if timeframe in {"1m", "15m", "30m", "60m"} else None),
                intraday_live_candidate_count=(len(live_codes) if timeframe in {"1m", "15m", "30m", "60m"} else None),
                intraday_live_phase=(live_phase if timeframe in {"1m", "15m", "30m", "60m"} else None),
            )

            effective_batch_size = _effective_batch_size(timeframe, scan_batch_size)
            results: list[dict[str, Any]] = []
            for index in range(0, len(universe), effective_batch_size):
                elapsed = (datetime.utcnow() - started_at).total_seconds()
                if elapsed >= max_duration_seconds and results:
                    logger.warning(
                        "Market scan reached runtime cap for %s after %d/%d candidates; saving partial results",
                        timeframe,
                        index,
                        len(universe),
                    )
                    break
                batch = universe[index:index + effective_batch_size]
                tasks = [
                    asyncio.wait_for(
                        _analyze_one(
                            code,
                            name,
                            market,
                            timeframe,
                            force_refresh=force_refresh,
                            allow_live_intraday=(code in live_codes) if timeframe in {"1m", "15m", "30m", "60m"} else True,
                        ),
                        timeout=max(3, int(settings.scan_symbol_timeout_seconds)),
                    )
                    for code, name, market in batch
                ]
                batch_results = await asyncio.gather(*tasks, return_exceptions=True)
                for item in batch_results:
                    if isinstance(item, dict):
                        if timeframe in {"1m", "15m", "30m", "60m"}:
                            item = _decorate_intraday_result(item, timeframe, live_codes=live_codes, live_phase=live_phase)
                        results.append(item)
                # 진행률 보고 — 프론트가 scan-status 폴링으로 진행 바를 그린다
                _update_scan_status(timeframe, scanned_count=min(index + effective_batch_size, len(universe)))
                await asyncio.sleep(0.12 if timeframe in {"1m", "15m", "30m", "60m"} else 0.08)

            results.sort(key=_scan_row_sort_key, reverse=True)
            # 일봉 스캔: 상위 후보에 수급 정렬 보강 (대시보드 랭킹에서 보정치 사용)
            if timeframe == "1d":
                try:
                    await _enrich_money_flow_alignment(results)
                except Exception as enrich_exc:
                    logger.warning("Money flow enrichment failed for %s: %s", timeframe, enrich_exc)
            # 로테이션 스캔: 이번에 안 돈 종목의 최근 신호를 이전 결과에서 이월
            fresh_results = results
            if timeframe in {"1d", "1wk", "1mo"}:
                results = _merge_scan_results(previous_cached, fresh_results)
            await cache_set(cache_key, results, ttl=settings.scan_results_ttl)
            finished_at = datetime.utcnow()
            reference_day, reference_reason = resolve_daily_reference_date()
            if timeframe in {"1m", "15m", "30m", "60m"}:
                reference_date = _kst_now().date().isoformat()
                reference_reason = "intraday_live_session"
            else:
                reference_date = reference_day.isoformat()
            try:
                await persist_scan_history(
                    timeframe=timeframe,
                    timeframe_label=timeframe_label(timeframe),
                    source=source,
                    status="ready",
                    candidate_source=_candidate_source,
                    reference_date=reference_date,
                    reference_reason=reference_reason,
                    universe_size=_universe_size,
                    candidate_count=_candidate_count,
                    started_at=started_at,
                    finished_at=finished_at,
                    duration_ms=int((finished_at - started_at).total_seconds() * 1000),
                    last_error=None,
                    results=fresh_results,  # 이력에는 이번 런에서 실제 스캔한 행만 기록
                )
            except Exception as history_exc:
                logger.warning("Scan history persistence failed for %s: %s", timeframe, history_exc)
            _update_scan_status(
                timeframe,
                status="ready",
                is_running=False,
                source=source,
                cached_result_count=len(results),
                last_finished_at=finished_at.isoformat(),
                duration_ms=int((finished_at - started_at).total_seconds() * 1000),
                # Use locally captured values — concurrent cold-start calls can
                # overwrite _scan_status during the long scan loop, so we cannot
                # rely on _status_snapshot to recover the correct universe metadata.
                candidate_source=_candidate_source,
                universe_size=_universe_size,
                candidate_count=_candidate_count,
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
    limit: int | None = None,
    batch_size: int | None = None,
    force_refresh: bool = True,
    source: str = "manual",
) -> dict[str, Any]:
    task = _scan_tasks.get(timeframe)
    if task and not task.done():
        status = await get_scan_status(timeframe)
        status["trigger_accepted"] = False
        return status

    default_limit, default_batch_size = _scan_workload_defaults(source)
    scan_limit = max(1, int(limit or default_limit))
    scan_batch_size = max(1, int(batch_size or default_batch_size))

    _scan_tasks[timeframe] = asyncio.create_task(
        run_scan(
            timeframe=timeframe,
            limit=scan_limit,
            batch_size=scan_batch_size,
            force_refresh=force_refresh,
            source=source,
        )
    )
    _update_scan_status(
        timeframe,
        status="queued",
        is_running=True,
        source=source,
        last_started_at=_utc_now_iso(),
        last_error=None,
    )
    status = await get_scan_status(timeframe)
    status["trigger_accepted"] = True
    return status


async def _build_quick_scan_results(timeframe: str) -> tuple[list[dict[str, Any]], list[tuple[str, str, str]], int, str]:
    fallback = (
        FALLBACK_CODES
        if timeframe == "1d"
        else FALLBACK_CODES[: min(len(FALLBACK_CODES), max(8, min(settings.intraday_live_candidate_limit, 10)))]
    )
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
    effective_batch_size = _effective_batch_size(timeframe, len(fallback), quick=True)
    results: list[dict[str, Any]] = []
    for index in range(0, len(fallback), effective_batch_size):
        batch = fallback[index:index + effective_batch_size]
        quick = await asyncio.gather(
            *[
                _analyze_one(
                    code,
                    name,
                    market,
                    timeframe,
                    allow_live_intraday=False if timeframe in {"1m", "15m", "30m", "60m"} else True,
                )
                for code, name, market in batch
            ],
            return_exceptions=True,
        )
        results.extend(item for item in quick if isinstance(item, dict))
        if timeframe in {"1m", "15m", "30m", "60m"}:
            await asyncio.sleep(0.1)
    if timeframe in {"1m", "15m", "30m", "60m"}:
        for item in results:
            _decorate_intraday_result(item, timeframe, live_codes=fallback_live_codes, live_phase=intraday_live_phase)

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
    return results, fallback, intraday_live_limit, intraday_live_phase


def _placeholder_fallback_codes(timeframe: str) -> list[tuple[str, str, str]]:
    if timeframe == "1d":
        return FALLBACK_CODES
    return FALLBACK_CODES[: min(len(FALLBACK_CODES), max(6, min(settings.intraday_live_candidate_limit, 8)))]


async def _bootstrap_intraday_quick_scan(timeframe: str, cache_key: str) -> list[dict[str, Any]]:
    quick_task = asyncio.current_task()
    try:
        results, fallback, intraday_live_limit, intraday_live_phase = await _build_quick_scan_results(timeframe)
        if results:
            await cache_set(cache_key, results, ttl=180)
        _update_scan_status(
            timeframe,
            status="warming",
            cached_result_count=len(results),
            universe_size=len(fallback),
            candidate_source="fallback_seed",
            candidate_count=len(fallback),
            intraday_live_candidate_limit=intraday_live_limit,
            intraday_live_candidate_count=intraday_live_limit,
            intraday_live_phase=intraday_live_phase,
            last_finished_at=_utc_now_iso(),
            source="fallback",
        )
        await trigger_scan(
            timeframe=timeframe,
            limit=settings.background_scan_limit,
            batch_size=settings.background_scan_batch_size,
            force_refresh=True,
            source="background",
        )
        return results
    except Exception as exc:
        logger.warning("Quick scan bootstrap failed for %s: %s", timeframe, exc)
        _update_scan_status(
            timeframe,
            status="error",
            is_running=False,
            last_error=str(exc),
            last_finished_at=_utc_now_iso(),
        )
        return []
    finally:
        current_task = _quick_scan_tasks.get(timeframe)
        if current_task is quick_task:
            _quick_scan_tasks.pop(timeframe, None)


async def get_scan_results(timeframe: str = DEFAULT_TIMEFRAME) -> list[dict[str, Any]]:
    cache_key = _full_scan_cache_key(timeframe)
    cached = await cache_get(cache_key)
    if cached:
        previous = _status_snapshot(timeframe)
        candidate_source = previous.get("candidate_source")
        candidate_count = previous.get("candidate_count")
        universe_size = previous.get("universe_size")

        if timeframe in {"1m", "15m", "30m", "60m"} and candidate_source in {None, "background_pending"}:
            candidate_source = "cache_ready"
            if not candidate_count:
                candidate_count = len(cached)
            if not universe_size:
                universe_size = max(len(cached), candidate_count)

        _update_scan_status(
            timeframe,
            status="ready",
            is_running=False,
            source=previous.get("source"),
            candidate_source=candidate_source,
            candidate_count=candidate_count,
            universe_size=universe_size,
            cached_result_count=len(cached),
            last_error=None,
            # preserve timing metadata so they survive across get_scan_results calls
            last_finished_at=previous.get("last_finished_at"),
            last_started_at=previous.get("last_started_at"),
            duration_ms=previous.get("duration_ms"),
        )
        return cached

    if timeframe in {"1m", "15m", "30m", "60m"}:
        task = _scan_tasks.get(timeframe)
        if task and not task.done():
            quick_cached = await cache_get(cache_key)
            if quick_cached:
                return quick_cached
            placeholders = _build_placeholder_scan_results(timeframe, _placeholder_fallback_codes(timeframe))
            _update_scan_status(
                timeframe,
                status="warming",
                source="fallback",
                candidate_source="placeholder_seed",
                candidate_count=len(placeholders),
                cached_result_count=len(placeholders),
                universe_size=len(placeholders),
                last_error=None,
            )
            return placeholders

        quick_task = _quick_scan_tasks.get(timeframe)
        if quick_task and not quick_task.done():
            quick_cached = await cache_get(cache_key)
            if quick_cached:
                return quick_cached
            placeholders = _build_placeholder_scan_results(timeframe, _placeholder_fallback_codes(timeframe))
            _update_scan_status(
                timeframe,
                status="warming",
                source="fallback",
                candidate_source="placeholder_seed",
                candidate_count=len(placeholders),
                cached_result_count=len(placeholders),
                universe_size=len(placeholders),
                last_error=None,
            )
            return placeholders

        _update_scan_status(
            timeframe,
            status="warming",
            is_running=False,
            source="fallback",
            candidate_source="background_pending",
            candidate_count=0,
            cached_result_count=0,
        )
        try:
            if not quick_task or quick_task.done():
                quick_task = asyncio.create_task(_bootstrap_intraday_quick_scan(timeframe, cache_key))
                _quick_scan_tasks[timeframe] = quick_task
            await asyncio.wait_for(asyncio.shield(quick_task), timeout=3.5)
        except asyncio.TimeoutError:
            quick_cached = await cache_get(cache_key)
            if quick_cached:
                return quick_cached
            placeholders = _build_placeholder_scan_results(timeframe, _placeholder_fallback_codes(timeframe))
            await cache_set(cache_key, placeholders, ttl=45)
            _update_scan_status(
                timeframe,
                status="warming",
                source="fallback",
                candidate_source="placeholder_seed",
                candidate_count=len(placeholders),
                cached_result_count=len(placeholders),
                universe_size=len(placeholders),
                last_finished_at=_utc_now_iso(),
                last_error=None,
            )
            return placeholders
        quick_cached = await cache_get(cache_key)
        return quick_cached or []

    fallback = _placeholder_fallback_codes(timeframe)
    results = _build_placeholder_scan_results(timeframe, fallback)
    # TTL 짧게 유지 — 플레이스홀더는 run_scan이 진짜 결과로 교체할 때까지만 임시 사용
    await cache_set(cache_key, results, ttl=60)
    _update_scan_status(
        timeframe,
        status="ready",
        cached_result_count=len(results),
        universe_size=len(fallback),
        candidate_source="placeholder_seed",
        candidate_count=len(fallback),
        last_finished_at=_utc_now_iso(),
        source="placeholder",
    )

    return results
