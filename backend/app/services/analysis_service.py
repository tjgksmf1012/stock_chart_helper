from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from typing import Any

import pandas as pd

from .backtest_engine import get_win_rate
from .kis_client import get_kis_client
from .pattern_engine import PatternEngine, PatternResult
from .probability_engine import compute_probability
from .timeframe_service import get_timeframe_spec, timeframe_label, is_intraday_timeframe

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
    current_close, current_high, current_low = _current_ohlc(df)
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


def _data_profile(timeframe: str, source: str | None = None) -> dict[str, float | str]:
    actual_source = source or ""
    if not is_intraday_timeframe(timeframe):
        if actual_source == "fdr_daily":
            return {
                "data_source": "fdr_daily",
                "data_quality": 0.88 if timeframe in {"1mo", "1wk"} else 0.86,
                "source_note": "KRX 일봉 대체 데이터 기준으로 계산한 신호입니다.",
            }
        return {
            "data_source": "krx_eod",
            "data_quality": 0.96 if timeframe in {"1mo", "1wk"} else 0.94,
            "source_note": "KRX 일봉 기준 데이터로 계산한 신호입니다.",
        }

    if actual_source in {"kis_intraday", "hybrid_intraday"}:
        quality_map = {"60m": 0.9, "30m": 0.88, "15m": 0.85, "1m": 0.76}
        return {
            "data_source": actual_source or "kis_intraday",
            "data_quality": quality_map.get(timeframe, 0.84),
            "source_note": "실시간 또는 보강된 분봉 기준으로 계산한 신호입니다.",
        }

    if actual_source == "yahoo_fallback" or not get_kis_client().configured:
        quality_map = {"60m": 0.68, "30m": 0.62, "15m": 0.56, "1m": 0.35}
        return {
            "data_source": "yahoo_fallback",
            "data_quality": quality_map.get(timeframe, 0.65),
            "source_note": "KIS 미연동 상태라 분봉 fallback 데이터 기준으로 보수적으로 계산한 신호입니다.",
        }

    return {
        "data_source": actual_source or "intraday_unknown",
        "data_quality": 0.7,
        "source_note": "분봉 데이터 기준으로 계산한 신호입니다.",
    }


def build_no_signal_snapshot(
    symbol_info: Any,
    timeframe: str,
    *,
    reason: str,
    summary: str,
) -> dict[str, Any]:
    profile = _data_profile(timeframe)
    return {
        "symbol": symbol_info,
        "timeframe": timeframe,
        "timeframe_label": timeframe_label(timeframe),
        "data_source": profile["data_source"],
        "data_quality": profile["data_quality"],
        "source_note": profile["source_note"],
        "p_up": 0.5,
        "p_down": 0.5,
        "textbook_similarity": 0.0,
        "pattern_confirmation_score": 0.0,
        "confidence": 0.0,
        "entry_score": 0.0,
        "completion_proximity": 0.0,
        "recency_score": 0.0,
        "bars_since_signal": None,
        "no_signal_flag": True,
        "no_signal_reason": reason,
        "reason_summary": summary,
        "sample_size": 0,
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
    profile = _data_profile(timeframe, str(df.attrs.get("data_source") or ""))
    if df.empty or len(df) < spec.min_bars:
        return build_no_signal_snapshot(
            symbol_info,
            timeframe,
            reason="데이터 부족",
            summary=f"{spec.label} 기준으로 패턴을 판단하기에 충분한 캔들 수가 아직 부족합니다.",
        )

    engine = PatternEngine()
    raw_patterns = engine.detect_all(df)
    if not raw_patterns:
        return build_no_signal_snapshot(
            symbol_info,
            timeframe,
            reason="감지된 패턴 없음",
            summary=f"{spec.label} 차트에서는 아직 뚜렷한 교과서형 패턴이 잡히지 않았습니다.",
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

    win_rate = await get_win_rate(best_pattern.pattern_type)
    prob = compute_probability(
        best_pattern,
        similar_win_rate=win_rate,
        sample_size=50,
        multi_tf_agreement=0.45 if str(profile["data_source"]) == "yahoo_fallback" else 0.55,
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
        "p_up": prob.p_up,
        "p_down": prob.p_down,
        "textbook_similarity": prob.textbook_similarity,
        "pattern_confirmation_score": prob.pattern_confirmation_score,
        "confidence": prob.confidence,
        "entry_score": prob.entry_score,
        "completion_proximity": prob.completion_proximity,
        "recency_score": prob.recency_score,
        "bars_since_signal": bars_since_signal,
        "no_signal_flag": prob.no_signal_flag,
        "no_signal_reason": prob.no_signal_reason,
        "reason_summary": prob.reason_summary,
        "sample_size": prob.sample_size,
        "patterns": patterns_payload,
        "is_provisional": best_pattern.is_provisional,
        "updated_at": datetime.utcnow().isoformat(),
    }
