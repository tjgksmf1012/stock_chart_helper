from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from typing import Any

import pandas as pd

from ..core.config import get_settings
from .backtest_engine import get_pattern_stats
from .kis_client import get_kis_client
from .pattern_engine import PatternEngine, PatternResult
from .probability_engine import compute_probability
from .timeframe_service import get_timeframe_spec, timeframe_label, is_intraday_timeframe

settings = get_settings()

_BULLISH_PATTERNS = {
    "double_bottom",
    "inverse_head_and_shoulders",
    "ascending_triangle",
    "rectangle",
    "cup_and_handle",
    "rounding_bottom",
}

_BEARISH_PATTERNS = {
    "double_top",
    "head_and_shoulders",
    "descending_triangle",
}

_FRESH_SIGNAL_BARS = {
    "1mo": 6,
    "1wk": 10,
    "1d": 25,
    "60m": 18,
    "30m": 24,
    "15m": 36,
    "1m": 90,
}


def _is_bullish(pattern_type: str) -> bool:
    return pattern_type in _BULLISH_PATTERNS


def _is_bearish(pattern_type: str) -> bool:
    return pattern_type in _BEARISH_PATTERNS


def _df_timestamp_column(df: pd.DataFrame) -> str:
    return "datetime" if "datetime" in df.columns else "date"


def _current_ohlc(df: pd.DataFrame) -> tuple[float, float, float]:
    row = df.iloc[-1]
    return float(row["close"]), float(row["high"]), float(row["low"])


def _latest_pattern_timestamp(pattern: PatternResult) -> pd.Timestamp:
    candidates: list[pd.Timestamp] = []
    if pattern.end_dt:
        candidates.append(pd.Timestamp(pattern.end_dt))
    candidates.extend(
        pd.Timestamp(point["dt"])
        for point in pattern.key_points
        if isinstance(point, dict) and point.get("dt")
    )
    if candidates:
        return max(candidates)
    return pd.Timestamp(pattern.start_dt)


def _bars_since_pattern(pattern: PatternResult, df: pd.DataFrame) -> int:
    ts_col = _df_timestamp_column(df)
    timestamps = pd.to_datetime(df[ts_col])
    anchor = _latest_pattern_timestamp(pattern)
    matched = timestamps[timestamps <= anchor]
    if matched.empty:
        return max(0, len(df) - 1)
    anchor_index = matched.index[-1]
    return max(0, len(df) - 1 - int(anchor_index))


def _refresh_pattern_state(pattern: PatternResult, df: pd.DataFrame) -> PatternResult:
    refreshed = deepcopy(pattern)
    _, current_high, current_low = _current_ohlc(df)
    now_dt = pd.Timestamp(pd.to_datetime(df[_df_timestamp_column(df)].iloc[-1])).to_pydatetime()

    bullish = _is_bullish(refreshed.pattern_type)
    bearish = _is_bearish(refreshed.pattern_type)

    if bullish:
        if refreshed.invalidation_level and current_low <= refreshed.invalidation_level:
            refreshed.state = "invalidated"
            refreshed.end_dt = now_dt
            refreshed.is_provisional = True
        elif refreshed.target_level and current_high >= refreshed.target_level * 0.995:
            refreshed.state = "played_out"
            refreshed.end_dt = now_dt
            refreshed.is_provisional = False
    elif bearish:
        if refreshed.invalidation_level and current_high >= refreshed.invalidation_level:
            refreshed.state = "invalidated"
            refreshed.end_dt = now_dt
            refreshed.is_provisional = True
        elif refreshed.target_level and current_low <= refreshed.target_level * 1.005:
            refreshed.state = "played_out"
            refreshed.end_dt = now_dt
            refreshed.is_provisional = False
    else:
        if refreshed.target_level and refreshed.invalidation_level:
            if current_high >= refreshed.target_level * 0.995 or current_low <= refreshed.invalidation_level:
                refreshed.state = "played_out"
                refreshed.end_dt = now_dt
                refreshed.is_provisional = False

    return refreshed


def _completion_proximity(pattern: PatternResult, df: pd.DataFrame) -> float:
    if pattern.state in {"played_out", "invalidated"}:
        return 0.0
    if pattern.state == "confirmed":
        return 1.0

    current_close, _, _ = _current_ohlc(df)
    trigger_level = pattern.neckline
    if trigger_level is None and pattern.target_level is not None and pattern.invalidation_level is not None:
        trigger_level = (pattern.target_level + pattern.invalidation_level) / 2

    if trigger_level is None or trigger_level == 0:
        return 0.75 if pattern.state == "armed" else 0.45

    distance_ratio = abs(current_close - trigger_level) / abs(trigger_level)
    proximity = max(0.0, 1.0 - distance_ratio / 0.08)
    if pattern.state == "armed":
        proximity = min(1.0, proximity + 0.15)
    return round(proximity, 3)


def _recency_score(pattern: PatternResult, df: pd.DataFrame, timeframe: str) -> tuple[float, int]:
    if pattern.state in {"played_out", "invalidated"}:
        return 0.0, _bars_since_pattern(pattern, df)

    bars_since = _bars_since_pattern(pattern, df)
    fresh_window = _FRESH_SIGNAL_BARS[timeframe]
    score = max(0.0, 1.0 - (bars_since / fresh_window))
    if pattern.state == "armed":
        score = min(1.0, score + 0.15)
    elif pattern.state == "forming":
        score *= 0.85
    return round(score, 3), bars_since


def _pattern_rank_score(pattern: PatternResult, recency_score: float, completion_proximity: float) -> float:
    state_score = {
        "confirmed": 1.0,
        "armed": 0.85,
        "forming": 0.55,
        "invalidated": 0.0,
        "played_out": 0.0,
    }.get(pattern.state, 0.4)
    return (
        0.4 * pattern.textbook_similarity
        + 0.2 * state_score
        + 0.2 * completion_proximity
        + 0.2 * recency_score
    )


def _average_turnover_billion(df: pd.DataFrame) -> float:
    if df.empty:
        return 0.0

    amount_series = None
    if "amount" in df.columns:
        numeric_amount = pd.to_numeric(df["amount"], errors="coerce").dropna()
        if not numeric_amount.empty and float(numeric_amount.sum()) > 0:
            amount_series = numeric_amount

    if amount_series is None:
        amount_series = (pd.to_numeric(df["close"], errors="coerce") * pd.to_numeric(df["volume"], errors="coerce")).dropna()

    if amount_series.empty:
        return 0.0
    return round(float(amount_series.tail(min(20, len(amount_series))).mean()) / 1e8, 2)


def _liquidity_score(avg_turnover_billion: float) -> float:
    if avg_turnover_billion <= 0:
        return 0.25

    ratio = avg_turnover_billion / max(0.5, settings.min_avg_volume_billion)
    score = 0.25 + min(1.0, ratio) * 0.55
    if ratio > 1.0:
        score += min(0.2, (ratio - 1.0) * 0.08)
    return round(min(1.0, score), 3)


def _data_profile(df: pd.DataFrame, timeframe: str, source: str | None = None) -> dict[str, Any]:
    actual_source = source or str(df.attrs.get("data_source") or "")
    fetch_status = str(df.attrs.get("fetch_status") or "")
    fetch_message = str(df.attrs.get("fetch_message") or "")
    storage_age_minutes = df.attrs.get("storage_age_minutes")

    if not is_intraday_timeframe(timeframe):
        if actual_source == "fdr_daily":
            return {
                "data_source": "fdr_daily",
                "data_quality": 0.88 if timeframe in {"1mo", "1wk"} else 0.86,
                "source_note": "KRX daily data fallback was used for this analysis.",
                "fetch_status": fetch_status or "daily_fallback",
                "fetch_message": fetch_message or "FinanceDataReader daily fallback was used.",
            }
        return {
            "data_source": "krx_eod",
            "data_quality": 0.96 if timeframe in {"1mo", "1wk"} else 0.94,
            "source_note": "KRX end-of-day data is the main source for this analysis.",
            "fetch_status": fetch_status or "daily_ok",
            "fetch_message": fetch_message or "KRX daily bars loaded successfully.",
        }

    if actual_source in {"kis_intraday", "hybrid_intraday"}:
        quality_map = {"60m": 0.9, "30m": 0.88, "15m": 0.85, "1m": 0.76}
        return {
            "data_source": actual_source,
            "data_quality": quality_map.get(timeframe, 0.84),
            "source_note": "Intraday bars came from KIS or a KIS-assisted hybrid feed.",
            "fetch_status": fetch_status or "live_ok",
            "fetch_message": fetch_message or "Intraday bars loaded successfully.",
        }

    if fetch_status == "stored_fallback" or actual_source in {"intraday_store", "intraday_unavailable"}:
        quality_map = {"60m": 0.74, "30m": 0.68, "15m": 0.61, "1m": 0.42}
        quality = quality_map.get(timeframe, 0.64)
        if isinstance(storage_age_minutes, int) and storage_age_minutes > 120:
            quality = max(0.25, quality - min(0.18, storage_age_minutes / 1440))
        stored_from = df.attrs.get("stored_source")
        stored_suffix = f" Stored source: {stored_from}." if stored_from else ""
        return {
            "data_source": "intraday_store",
            "data_quality": round(quality, 3),
            "source_note": f"Stored intraday bars were reused because live providers were unavailable.{stored_suffix}",
            "fetch_status": fetch_status,
            "fetch_message": fetch_message or "Stored intraday bars were used.",
        }

    if actual_source == "yahoo_fallback" or not get_kis_client().configured:
        quality_map = {"60m": 0.68, "30m": 0.62, "15m": 0.56, "1m": 0.35}
        return {
            "data_source": "yahoo_fallback",
            "data_quality": quality_map.get(timeframe, 0.65),
            "source_note": "KIS is not configured, so intraday analysis is using the Yahoo fallback source conservatively.",
            "fetch_status": fetch_status or "intraday_unavailable",
            "fetch_message": fetch_message or "Intraday bars depend on the Yahoo fallback in this environment.",
        }

    return {
        "data_source": actual_source or "intraday_unknown",
        "data_quality": 0.7,
        "source_note": "Intraday bars were loaded from the currently available provider.",
        "fetch_status": fetch_status or "intraday_unavailable",
        "fetch_message": fetch_message or "Intraday provider details are unavailable.",
    }


def _no_signal_text(timeframe: str, fetch_status: str, fetch_message: str, available_bars: int, min_bars: int) -> tuple[str, str]:
    label = timeframe_label(timeframe)

    if is_intraday_timeframe(timeframe):
        if fetch_status == "intraday_rate_limited":
            return (
                "분봉 요청 제한",
                "Yahoo 분봉 요청 제한이 걸려 현재 실시간 분봉을 바로 계산하지 못했습니다. 잠시 후 다시 시도하거나 일봉/주봉 신호를 먼저 확인해 주세요.",
            )
        if fetch_status == "stored_fallback" and available_bars > 0:
            return (
                "저장된 분봉 사용",
                f"{label} 기준 라이브 분봉 수급이 막혀 저장해둔 분봉 {available_bars}개를 대신 사용했습니다. {fetch_message}",
            )
        if fetch_status in {"intraday_empty", "stored_empty", "intraday_unavailable"}:
            return (
                "분봉 소스 부족",
                f"{label} 분봉을 현재 안정적으로 확보하지 못했습니다. {fetch_message or '잠시 후 다시 시도하거나 상위 타임프레임을 먼저 확인해 주세요.'}",
            )
        if available_bars < min_bars:
            return (
                "분봉 바 수 부족",
                f"{label} 패턴 판정을 하려면 최소 {min_bars}개 바가 필요한데 현재는 {available_bars}개만 확보됐습니다.",
            )

    if available_bars < min_bars:
        return (
            "데이터 부족",
            f"{label} 기준 패턴 분석을 하려면 최소 {min_bars}개 바가 필요한데 현재는 {available_bars}개만 확보됐습니다.",
        )

    return (
        "패턴 없음",
        f"{label} 차트에서는 아직 신뢰도 있는 교과서형 패턴이 포착되지 않았습니다.",
    )


def build_no_signal_snapshot(
    symbol_info: Any,
    timeframe: str,
    *,
    reason: str,
    summary: str,
    profile: dict[str, Any] | None = None,
    available_bars: int = 0,
    avg_turnover_billion: float = 0.0,
) -> dict[str, Any]:
    active_profile = profile or _data_profile(pd.DataFrame(), timeframe)
    return {
        "symbol": symbol_info,
        "timeframe": timeframe,
        "timeframe_label": timeframe_label(timeframe),
        "data_source": active_profile["data_source"],
        "data_quality": active_profile["data_quality"],
        "source_note": active_profile["source_note"],
        "fetch_status": active_profile.get("fetch_status"),
        "fetch_message": active_profile.get("fetch_message"),
        "p_up": 0.5,
        "p_down": 0.5,
        "textbook_similarity": 0.0,
        "pattern_confirmation_score": 0.0,
        "confidence": 0.0,
        "entry_score": 0.0,
        "completion_proximity": 0.0,
        "recency_score": 0.0,
        "bars_since_signal": None,
        "liquidity_score": _liquidity_score(avg_turnover_billion),
        "avg_turnover_billion": avg_turnover_billion,
        "no_signal_flag": True,
        "no_signal_reason": reason,
        "reason_summary": summary,
        "sample_size": 0,
        "stats_timeframe": timeframe if timeframe in {"1mo", "1wk", "1d"} else "1d",
        "available_bars": available_bars,
        "patterns": [],
        "is_provisional": True,
        "updated_at": datetime.utcnow().isoformat(),
    }


async def analyze_symbol_dataframe(
    *,
    symbol_info: Any,
    timeframe: str,
    df: pd.DataFrame,
) -> dict[str, Any]:
    spec = get_timeframe_spec(timeframe)
    profile = _data_profile(df, timeframe)
    available_bars = len(df)
    avg_turnover_billion = _average_turnover_billion(df)
    liquidity_score = _liquidity_score(avg_turnover_billion)

    if df.empty or available_bars < spec.min_bars:
        reason, summary = _no_signal_text(
            timeframe,
            str(profile.get("fetch_status") or ""),
            str(profile.get("fetch_message") or ""),
            available_bars,
            spec.min_bars,
        )
        return build_no_signal_snapshot(
            symbol_info,
            timeframe,
            reason=reason,
            summary=summary,
            profile=profile,
            available_bars=available_bars,
            avg_turnover_billion=avg_turnover_billion,
        )

    engine = PatternEngine()
    raw_patterns = engine.detect_all(df)
    if not raw_patterns:
        reason, summary = _no_signal_text(
            timeframe,
            str(profile.get("fetch_status") or ""),
            str(profile.get("fetch_message") or ""),
            available_bars,
            spec.min_bars,
        )
        reason = "패턴 없음"
        summary = f"{spec.label} 차트에서는 아직 신뢰도 있는 교과서형 패턴이 감지되지 않았습니다."
        return build_no_signal_snapshot(
            symbol_info,
            timeframe,
            reason=reason,
            summary=summary,
            profile=profile,
            available_bars=available_bars,
            avg_turnover_billion=avg_turnover_billion,
        )

    enriched_patterns: list[tuple[PatternResult, float, float, int]] = []
    for pattern in raw_patterns:
        refreshed = _refresh_pattern_state(pattern, df)
        recency_score, bars_since = _recency_score(refreshed, df, timeframe)
        completion_proximity = _completion_proximity(refreshed, df)
        enriched_patterns.append((refreshed, recency_score, completion_proximity, bars_since))

    best_pattern, best_recency, best_completion, bars_since_signal = max(
        enriched_patterns,
        key=lambda item: _pattern_rank_score(item[0], item[1], item[2]),
    )

    patterns_payload = [
        {
            "pattern_type": pattern.pattern_type,
            "state": pattern.state,
            "grade": pattern.grade,
            "textbook_similarity": pattern.textbook_similarity,
            "geometry_fit": pattern.geometry_fit,
            "neckline": pattern.neckline,
            "invalidation_level": pattern.invalidation_level,
            "target_level": pattern.target_level,
            "key_points": pattern.key_points,
            "is_provisional": pattern.is_provisional,
            "start_dt": pattern.start_dt.isoformat(),
            "end_dt": pattern.end_dt.isoformat() if pattern.end_dt else None,
            "recency_score": recency_score,
            "completion_proximity": completion_proximity,
            "bars_since_signal": bars_since,
        }
        for pattern, recency_score, completion_proximity, bars_since in sorted(
            enriched_patterns,
            key=lambda item: _pattern_rank_score(item[0], item[1], item[2]),
            reverse=True,
        )
    ]

    stats_timeframe = timeframe if timeframe in {"1mo", "1wk", "1d"} else "1d"
    stats = await get_pattern_stats(best_pattern.pattern_type, stats_timeframe)
    sample_size = int(stats["sample_size"])
    similar_win_rate = float(stats["win_rate"])
    if is_intraday_timeframe(timeframe):
        similar_win_rate = round(0.65 * similar_win_rate + 0.35 * 0.5, 3)
        sample_size = max(0, int(sample_size * 0.6))

    prob = compute_probability(
        best_pattern,
        similar_win_rate=similar_win_rate,
        sample_size=sample_size,
        liquidity_score=liquidity_score,
        multi_tf_agreement=0.45 if str(profile["data_source"]) in {"yahoo_fallback", "intraday_store"} else 0.58,
        regime_match=best_pattern.regime_fit,
        data_quality=float(profile["data_quality"]),
        risk_penalty=max(0.0, 0.35 - best_completion) + (1 - float(profile["data_quality"])) * 0.45,
        completion_proximity=best_completion,
        recency_score=best_recency,
    )

    return {
        "symbol": symbol_info,
        "timeframe": timeframe,
        "timeframe_label": spec.label,
        "data_source": profile["data_source"],
        "data_quality": profile["data_quality"],
        "source_note": profile["source_note"],
        "fetch_status": profile.get("fetch_status"),
        "fetch_message": profile.get("fetch_message"),
        "p_up": prob.p_up,
        "p_down": prob.p_down,
        "textbook_similarity": prob.textbook_similarity,
        "pattern_confirmation_score": prob.pattern_confirmation_score,
        "confidence": prob.confidence,
        "entry_score": prob.entry_score,
        "completion_proximity": prob.completion_proximity,
        "recency_score": prob.recency_score,
        "bars_since_signal": bars_since_signal,
        "liquidity_score": liquidity_score,
        "avg_turnover_billion": avg_turnover_billion,
        "no_signal_flag": prob.no_signal_flag,
        "no_signal_reason": prob.no_signal_reason,
        "reason_summary": prob.reason_summary,
        "sample_size": prob.sample_size,
        "stats_timeframe": stats_timeframe,
        "available_bars": available_bars,
        "patterns": patterns_payload,
        "is_provisional": best_pattern.is_provisional,
        "updated_at": datetime.utcnow().isoformat(),
    }
