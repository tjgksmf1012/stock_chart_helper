"""
Shared analysis pipeline for symbol detail pages and scanner snapshots.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import pandas as pd
from pandas.tseries.offsets import BDay, DateOffset

from ..api.schemas import AnalysisResult, PatternInfo, ProjectionPoint, SymbolInfo
from .backtest_engine import get_pattern_stats
from .pattern_engine import PatternEngine, PatternResult
from .probability_engine import compute_probability
from .timeframe_service import get_timeframe_spec, is_intraday_timeframe, timeframe_label

_BULLISH_PATTERNS = {
    "double_bottom",
    "inverse_head_and_shoulders",
    "ascending_triangle",
    "rectangle",
    "cup_and_handle",
    "rounding_bottom",
    "vcp",
}
_BEARISH_PATTERNS = {
    "double_top",
    "head_and_shoulders",
    "descending_triangle",
}

_FETCH_STATUS_LABELS = {
    "live_ok": "실시간 수집 성공",
    "live_augmented_by_store": "실시간과 저장 분봉 결합",
    "stored_fallback": "저장 분봉 대체",
    "stored_empty": "저장 분봉 없음",
    "intraday_rate_limited": "분봉 요청 제한",
    "intraday_unavailable": "분봉 제공처 응답 없음",
    "intraday_empty": "분봉 바 수 부족",
    "yahoo_symbol_missing": "야후 심볼 매핑 실패",
    "yahoo_rate_limited": "야후 요청 제한",
    "yahoo_empty": "야후 분봉 없음",
    "kis_not_configured": "KIS 미설정",
    "kis_error": "KIS 요청 실패",
    "kis_empty": "KIS 분봉 없음",
    "daily_ok": "일봉 수집 성공",
    "daily_empty": "일봉 바 수 부족",
    "daily_error": "일봉 수집 실패",
    "unknown": "상태 정보 없음",
}


_FETCH_STATUS_LABELS.update(
    {
        "stored_recent": "최근 저장 분봉 재사용",
        "kis_cooldown": "KIS 쿨다운",
        "scanner_store_only": "스캐너 저장 분봉 우선",
        "scanner_public_only": "스캐너 공개 분봉 사용",
        "scanner_public_augmented": "스캐너 공개 분봉+저장 결합",
    }
)


def _is_bullish(pattern_type: str) -> bool:
    return pattern_type in _BULLISH_PATTERNS


def _is_bearish(pattern_type: str) -> bool:
    return pattern_type in _BEARISH_PATTERNS


def _df_timestamp_column(df: pd.DataFrame) -> str:
    return "datetime" if "datetime" in df.columns else "date"


def _timestamp_series(df: pd.DataFrame) -> pd.Series:
    timestamps = pd.to_datetime(df[_df_timestamp_column(df)], errors="coerce")
    if getattr(timestamps.dt, "tz", None) is not None:
        timestamps = timestamps.dt.tz_convert("Asia/Seoul").dt.tz_localize(None)
    return timestamps


def _current_ohlc(df: pd.DataFrame) -> tuple[float, float, float]:
    last_row = df.iloc[-1]
    return float(last_row["close"]), float(last_row["high"]), float(last_row["low"])


def _latest_pattern_timestamp(pattern: PatternResult) -> pd.Timestamp:
    timestamps: list[pd.Timestamp] = []
    for point in pattern.key_points:
        dt = point.get("dt")
        if not dt:
            continue
        ts = pd.to_datetime(dt, errors="coerce")
        if pd.notna(ts):
            timestamps.append(ts.tz_localize(None) if getattr(ts, "tzinfo", None) else ts)
    if timestamps:
        return max(timestamps)
    fallback = pd.Timestamp(pattern.end_dt or pattern.start_dt)
    return fallback.tz_localize(None) if getattr(fallback, "tzinfo", None) else fallback


def _bars_since_pattern(df: pd.DataFrame, pattern: PatternResult) -> int:
    timestamps = _timestamp_series(df)
    latest_point = _latest_pattern_timestamp(pattern)
    candidates = timestamps[timestamps <= latest_point]
    if candidates.empty:
        return len(df) - 1
    anchor_index = candidates.index[-1]
    return max(0, len(df) - 1 - int(anchor_index))


def _historical_pattern_outcome(
    df: pd.DataFrame,
    pattern: PatternResult,
) -> tuple[str, str | None, str | None]:
    target = pattern.target_level
    invalidation = pattern.invalidation_level
    if target is None or invalidation is None:
        return pattern.state, None, None

    anchor = _latest_pattern_timestamp(pattern)
    timestamps = _timestamp_series(df)
    future_df = df.loc[timestamps >= anchor].copy()
    future_times = timestamps.loc[future_df.index]
    bullish = _is_bullish(pattern.pattern_type)
    bearish = _is_bearish(pattern.pattern_type)

    for idx, row in future_df.iterrows():
        ts = future_times.loc[idx]
        ts_text = ts.isoformat()
        high = float(row["high"])
        low = float(row["low"])

        if bullish:
            if high >= target:
                return "played_out", ts_text, None
            if low <= invalidation:
                return "invalidated", None, ts_text
        elif bearish:
            if low <= target:
                return "played_out", ts_text, None
            if high >= invalidation:
                return "invalidated", None, ts_text

    return pattern.state, None, None


def _refresh_pattern_state(
    df: pd.DataFrame,
    pattern: PatternResult,
    current_close: float,
    current_high: float,
    current_low: float,
) -> tuple[PatternResult, str | None, str | None]:
    refreshed = PatternResult(**pattern.__dict__)
    target = refreshed.target_level
    invalidation = refreshed.invalidation_level

    if target is None or invalidation is None:
        return refreshed, None, None

    historical_state, target_hit_at, invalidated_at = _historical_pattern_outcome(df, refreshed)
    refreshed.state = historical_state

    if historical_state not in {"played_out", "invalidated"}:
        bullish = _is_bullish(refreshed.pattern_type)
        bearish = _is_bearish(refreshed.pattern_type)
        if bullish:
            if current_low <= invalidation:
                refreshed.state = "invalidated"
            elif current_high >= target or current_close >= target:
                refreshed.state = "played_out"
        elif bearish:
            if current_high >= invalidation:
                refreshed.state = "invalidated"
            elif current_low <= target or current_close <= target:
                refreshed.state = "played_out"

    refreshed.is_provisional = refreshed.state != "confirmed"
    return refreshed, target_hit_at, invalidated_at


def _completion_proximity(pattern: PatternResult, current_close: float) -> float:
    neckline = pattern.neckline
    invalidation = pattern.invalidation_level
    if neckline is None or invalidation is None or neckline == invalidation:
        return 0.5 if pattern.state == "confirmed" else 0.35

    if _is_bullish(pattern.pattern_type):
        progress = (current_close - invalidation) / (neckline - invalidation)
    elif _is_bearish(pattern.pattern_type):
        progress = (invalidation - current_close) / (invalidation - neckline)
    else:
        progress = 0.5

    baseline = {
        "forming": 0.25,
        "armed": 0.72,
        "confirmed": 0.92,
        "played_out": 1.0,
        "invalidated": 0.0,
    }.get(pattern.state, 0.35)
    return max(0.0, min(1.0, max(progress, baseline)))


def _recency_score(timeframe: str, bars_since_signal: int) -> float:
    if bars_since_signal < 0:
        return 0.0
    thresholds = {
        "1mo": (1, 3, 6),
        "1wk": (2, 6, 12),
        "1d": (5, 20, 45),
        "60m": (6, 24, 48),
        "30m": (8, 32, 72),
        "15m": (10, 40, 96),
        "1m": (15, 60, 180),
    }
    fresh, okay, stale = thresholds.get(timeframe, (5, 20, 45))
    if bars_since_signal <= fresh:
        return 1.0
    if bars_since_signal <= okay:
        return 0.75
    if bars_since_signal <= stale:
        return 0.45
    return 0.15


def _average_turnover_billion(df: pd.DataFrame) -> float:
    if df.empty:
        return 0.0
    if "amount" in df.columns and df["amount"].notna().any():
        series = pd.to_numeric(df["amount"], errors="coerce").dropna()
        if not series.empty:
            return float(series.tail(min(len(series), 20)).mean() / 1e8)
    price = pd.to_numeric(df["close"], errors="coerce")
    volume = pd.to_numeric(df["volume"], errors="coerce")
    notional = (price * volume).dropna()
    if not notional.empty:
        return float(notional.tail(min(len(notional), 20)).mean() / 1e8)
    return 0.0


def _liquidity_score(turnover_billion: float) -> float:
    if turnover_billion >= 300:
        return 1.0
    if turnover_billion >= 120:
        return 0.9
    if turnover_billion >= 50:
        return 0.78
    if turnover_billion >= 20:
        return 0.66
    if turnover_billion >= 8:
        return 0.52
    if turnover_billion >= 3:
        return 0.40
    return 0.25


def _regime_match(df: pd.DataFrame, pattern_type: str) -> float:
    close = pd.to_numeric(df["close"], errors="coerce").dropna()
    if len(close) < 20:
        return 0.5
    fast = close.tail(min(len(close), 20)).mean()
    slow = close.tail(min(len(close), 60)).mean()
    if slow == 0:
        return 0.5
    bullish = fast >= slow
    if _is_bullish(pattern_type):
        return 0.68 if bullish else 0.38
    if _is_bearish(pattern_type):
        return 0.68 if not bullish else 0.38
    return 0.5


def _trend_alignment_profile(df: pd.DataFrame, pattern_type: str) -> dict[str, Any]:
    close = pd.to_numeric(df["close"], errors="coerce").dropna()
    if len(close) < 80:
        return {
            "trend_alignment_score": 0.5,
            "trend_direction": "sideways",
            "trend_warning": "추세 판단에 필요한 바 수가 아직 충분하지 않습니다.",
        }

    fast = close.rolling(20).mean()
    medium = close.rolling(60).mean()
    last_close = float(close.iloc[-1])
    fast_now = float(fast.iloc[-1])
    medium_now = float(medium.iloc[-1])
    medium_prev = float(medium.iloc[-21]) if len(medium.dropna()) >= 21 and pd.notna(medium.iloc[-21]) else medium_now
    medium_slope = 0.0 if medium_prev == 0 else (medium_now - medium_prev) / medium_prev

    if last_close > fast_now > medium_now and medium_slope > 0.02:
        trend_direction = "up"
    elif last_close < fast_now < medium_now and medium_slope < -0.02:
        trend_direction = "down"
    else:
        trend_direction = "sideways"

    bullish = _is_bullish(pattern_type)
    bearish = _is_bearish(pattern_type)

    if bullish:
        if trend_direction == "up":
            score = 0.92 if last_close > fast_now else 0.82
            warning = ""
        elif trend_direction == "sideways":
            score = 0.58
            warning = "상위 추세가 아직 완전한 상승 정렬은 아니라 추세 추종보다는 눌림 확인이 더 중요합니다."
        else:
            score = 0.24
            warning = "현재 패턴은 중기 하락 추세에 역행하는 반등형 구조라 실패 확률을 더 보수적으로 봐야 합니다."
    elif bearish:
        if trend_direction == "down":
            score = 0.92 if last_close < fast_now else 0.82
            warning = ""
        elif trend_direction == "sideways":
            score = 0.58
            warning = "상위 추세가 아직 완전한 하락 정렬은 아니라 이탈 실패 가능성을 함께 봐야 합니다."
        else:
            score = 0.24
            warning = "현재 패턴은 중기 상승 추세에 역행하는 하락형 구조라 과신하지 않는 편이 좋습니다."
    else:
        score = 0.5
        warning = "중립형 패턴은 상위 추세와 함께 해석해야 의미가 커집니다."

    return {
        "trend_alignment_score": round(score, 3),
        "trend_direction": trend_direction,
        "trend_warning": warning,
    }


def _wyckoff_profile(df: pd.DataFrame, pattern_type: str) -> dict[str, Any]:
    close = pd.to_numeric(df["close"], errors="coerce").dropna()
    volume = pd.to_numeric(df["volume"], errors="coerce").dropna()
    if len(close) < 80:
        return {
            "wyckoff_phase": "neutral",
            "wyckoff_score": 0.5,
            "wyckoff_note": "와이코프 단계 판단에 필요한 바 수가 아직 충분하지 않습니다.",
        }

    last_close = float(close.iloc[-1])
    ma20 = close.rolling(20).mean()
    ma60 = close.rolling(60).mean()
    ma20_now = float(ma20.iloc[-1])
    ma60_now = float(ma60.iloc[-1])
    ma60_prev = float(ma60.iloc[-21]) if len(ma60.dropna()) >= 21 and pd.notna(ma60.iloc[-21]) else ma60_now
    slope = 0.0 if ma60_prev == 0 else (ma60_now - ma60_prev) / ma60_prev

    range_window = close.tail(min(len(close), 252))
    range_low = float(range_window.min())
    range_high = float(range_window.max())
    range_span = max(range_high - range_low, max(last_close * 0.01, 1.0))
    range_pos = (last_close - range_low) / range_span

    long_range = (close.tail(40).max() - close.tail(40).min()) / max(last_close, 1.0)
    short_range = (close.tail(10).max() - close.tail(10).min()) / max(last_close, 1.0)
    contraction = 1.0 - (short_range / max(long_range, 0.01))
    volume_ratio = (
        float(volume.tail(10).mean()) / max(float(volume.tail(40).mean()), 1.0)
        if len(volume) >= 40
        else 1.0
    )

    bullish = _is_bullish(pattern_type)
    bearish = _is_bearish(pattern_type)

    phase = "neutral"
    score = 0.52
    note = "와이코프 기준으로는 아직 뚜렷한 단계 확정 전의 중립 구간에 가깝습니다."

    if last_close > ma20_now > ma60_now and slope > 0.02 and range_pos > 0.62:
        phase = "markup"
        score = 0.88 if contraction > 0.15 else 0.78
        note = "중기 상승 추세가 유지되고 있어 와이코프 기준 상승 진행 구간으로 해석하는 편이 맞습니다."
    elif last_close < ma20_now < ma60_now and slope < -0.02 and range_pos < 0.36:
        phase = "markdown"
        score = 0.88 if contraction < 0.1 else 0.78
        note = "중기 하락 추세가 이어지는 구간이라 와이코프 기준 하락 진행 구간으로 보는 편이 안전합니다."
    elif range_pos < 0.46 and abs(slope) < 0.04 and contraction > 0.18 and volume_ratio < 0.95:
        phase = "accumulation"
        score = 0.82 if bullish else 0.68
        note = "하단에서 변동성 수축과 거래량 감소가 함께 보여 매집 말기 또는 재축적 가능성을 의심할 수 있습니다."
    elif range_pos > 0.58 and abs(slope) < 0.04 and volume_ratio > 1.05:
        phase = "distribution"
        score = 0.82 if bearish else 0.68
        note = "상단에서 거래량이 늘고 추세가 둔화돼 분산 또는 재분배 구간일 가능성을 함께 봐야 합니다."
    elif last_close > ma60_now and contraction > 0.22 and volume_ratio < 0.92:
        phase = "accumulation"
        score = 0.72 if bullish else 0.58
        note = "상승 추세 위에서 다시 타이트해지는 재축적 성격이 보입니다."
    elif last_close < ma60_now and contraction > 0.18 and volume_ratio > 1.0:
        phase = "distribution"
        score = 0.72 if bearish else 0.58
        note = "약세 추세 안에서 반등 에너지가 약해 분배 또는 재분배 성격을 경계해야 합니다."

    return {
        "wyckoff_phase": phase,
        "wyckoff_score": round(float(max(0.0, min(1.0, score))), 3),
        "wyckoff_note": note,
    }


def _intraday_session_profile(df: pd.DataFrame, timeframe: str, pattern_type: str) -> dict[str, Any]:
    if not is_intraday_timeframe(timeframe) or "datetime" not in df.columns:
        return {
            "intraday_session_phase": "neutral",
            "intraday_session_score": 0.5,
            "intraday_session_note": "",
        }

    timestamps = _timestamp_series(df).dropna()
    if timestamps.empty:
        return {
            "intraday_session_phase": "neutral",
            "intraday_session_score": 0.5,
            "intraday_session_note": "장중 시간대 판정을 위한 타임스탬프가 부족합니다.",
        }

    last_ts = timestamps.iloc[-1]
    hhmm = last_ts.hour * 100 + last_ts.minute
    close = pd.to_numeric(df["close"], errors="coerce").dropna()
    volume = pd.to_numeric(df["volume"], errors="coerce").dropna()
    if len(close) < 6:
        return {
            "intraday_session_phase": "neutral",
            "intraday_session_score": 0.5,
            "intraday_session_note": "장중 흐름을 읽기엔 최근 분봉 수가 아직 부족합니다.",
        }

    recent_close = close.tail(min(len(close), 4))
    recent_volume = volume.tail(min(len(volume), 4))
    base_volume = volume.tail(min(len(volume), 24)).head(max(len(volume.tail(min(len(volume), 24))) - len(recent_volume), 1))

    start_price = float(recent_close.iloc[0])
    end_price = float(recent_close.iloc[-1])
    momentum = 0.0 if start_price == 0 else (end_price - start_price) / start_price
    volume_ratio = (
        float(recent_volume.mean()) / max(float(base_volume.mean()) if not base_volume.empty else float(recent_volume.mean()), 1.0)
    )

    bullish = _is_bullish(pattern_type)
    bearish = _is_bearish(pattern_type)

    if hhmm < 1000:
        phase = "open_drive"
    elif 1130 <= hhmm < 1400:
        phase = "midday"
    elif 1430 <= hhmm <= 1530:
        phase = "closing_drive"
    elif 1000 <= hhmm < 1130 or 1400 <= hhmm < 1430:
        phase = "regular_session"
    else:
        phase = "off_hours"

    score = 0.52
    note = "현재 시간대 문맥은 중립에 가깝습니다."

    if phase == "open_drive":
        if bullish:
            if momentum > 0.008 and volume_ratio > 1.15:
                score = 0.84
                note = "장 초반 수급이 강하게 붙는 구간이라 상승형 패턴 확인에는 우호적인 시간대입니다."
            elif momentum < -0.004:
                score = 0.32
                note = "장 초반부터 밀리는 흐름이라 추격 매수보다는 실패 가능성을 더 경계해야 합니다."
            else:
                score = 0.58
                note = "장 초반 방향성은 보이지만, 한쪽으로 확정하기엔 아직 이릅니다."
        elif bearish:
            if momentum < -0.008 and volume_ratio > 1.15:
                score = 0.84
                note = "장 초반 매도 압력이 강해 하락형 패턴 확인에는 우호적인 시간대입니다."
            elif momentum > 0.004:
                score = 0.32
                note = "장 초반부터 반등이 강해 하락 지속 시나리오를 바로 믿기는 어렵습니다."
            else:
                score = 0.58
                note = "장 초반 방향성은 보이지만, 추가 확인이 더 필요합니다."
    elif phase == "midday":
        if abs(momentum) < 0.003 or volume_ratio < 0.9:
            score = 0.40
            note = "점심장 특유의 소강 구간에 가까워, 분봉 패턴은 신호 과신보다 대기 쪽이 더 안전합니다."
        else:
            score = 0.56
            note = "점심장치고는 움직임이 있는 편이지만, 마감 전 재확인이 더 중요합니다."
    elif phase == "closing_drive":
        if bullish:
            if momentum > 0.006:
                score = 0.88 if volume_ratio > 1.0 else 0.78
                note = "마감 전 재가속이 붙는 흐름이라 상승형 패턴 확인에는 가장 좋은 시간대 중 하나입니다."
            elif momentum < -0.004:
                score = 0.30
                note = "마감 전 힘이 꺾이면 당일 패턴 신뢰도는 크게 낮아집니다."
            else:
                score = 0.60
                note = "마감 전 흐름은 무난하지만, 확신을 주는 재가속까지는 아닙니다."
        elif bearish:
            if momentum < -0.006:
                score = 0.88 if volume_ratio > 1.0 else 0.78
                note = "마감 전 하방 재가속이 붙는 흐름이라 하락형 패턴 확인에는 우호적입니다."
            elif momentum > 0.004:
                score = 0.30
                note = "마감 전 되받음이 강해 하락형 패턴을 과신하기 어렵습니다."
            else:
                score = 0.60
                note = "마감 전 흐름은 무난하지만, 강한 확인 구간까지는 아닙니다."
    elif phase == "regular_session":
        if bullish:
            score = 0.64 if momentum > 0.004 else 0.46
            note = "장중 일반 구간에서는 방향성은 참고하되, 거래량 동반 여부를 함께 보는 편이 좋습니다."
        elif bearish:
            score = 0.64 if momentum < -0.004 else 0.46
            note = "장중 일반 구간에서는 하락 지속 여부보다 이탈 유지 여부를 함께 봐야 합니다."
    else:
        score = 0.44
        note = "정규장 바깥 시점이라 마지막 분봉의 시간대 해석은 보수적으로 보는 편이 맞습니다."

    return {
        "intraday_session_phase": phase,
        "intraday_session_score": round(float(max(0.0, min(1.0, score))), 3),
        "intraday_session_note": note,
    }


def _opportunity_profile(pattern: PatternResult, current_close: float) -> dict[str, float]:
    target = pattern.target_level
    invalidation = pattern.invalidation_level
    if target is None or invalidation is None or current_close <= 0:
        return {
            "reward_risk_ratio": 1.0,
            "headroom_score": 0.5,
            "target_distance_pct": 0.0,
            "stop_distance_pct": 0.0,
        }

    bullish = _is_bullish(pattern.pattern_type)
    bearish = _is_bearish(pattern.pattern_type)

    if bullish:
        target_distance = max(0.0, target - current_close)
        stop_distance = max(0.0, current_close - invalidation)
    elif bearish:
        target_distance = max(0.0, current_close - target)
        stop_distance = max(0.0, invalidation - current_close)
    else:
        target_distance = abs(target - current_close)
        stop_distance = abs(current_close - invalidation)

    target_distance_pct = target_distance / current_close
    stop_distance_pct = stop_distance / current_close
    reward_risk_ratio = target_distance / max(stop_distance, current_close * 0.003)

    if target_distance_pct >= 0.12:
        headroom_score = 1.0
    elif target_distance_pct >= 0.08:
        headroom_score = 0.8
    elif target_distance_pct >= 0.05:
        headroom_score = 0.6
    elif target_distance_pct >= 0.03:
        headroom_score = 0.4
    elif target_distance_pct >= 0.015:
        headroom_score = 0.22
    else:
        headroom_score = 0.08

    return {
        "reward_risk_ratio": round(max(0.0, reward_risk_ratio), 3),
        "headroom_score": round(headroom_score, 3),
        "target_distance_pct": round(target_distance_pct, 4),
        "stop_distance_pct": round(stop_distance_pct, 4),
    }


def _stats_timeframe(timeframe: str) -> str:
    if timeframe in {"1mo", "1wk", "1d"}:
        return timeframe
    return "1d"


def _fetch_status_label(fetch_status: str) -> str:
    return _FETCH_STATUS_LABELS.get(fetch_status, _FETCH_STATUS_LABELS["unknown"])


def _data_profile(df: pd.DataFrame, timeframe: str) -> dict[str, Any]:
    source = str(df.attrs.get("data_source") or "unknown")
    fetch_status = str(df.attrs.get("fetch_status") or "unknown")
    fetch_message = str(df.attrs.get("fetch_message") or "")
    stored_source = df.attrs.get("stored_source")
    available_bars = int(df.attrs.get("available_bars") or len(df))

    if timeframe in {"1mo", "1wk", "1d"}:
        if source == "pykrx_daily":
            quality = 0.96
            note = "KRX 일봉 데이터를 기준으로 사용하고 있어 상대적으로 신뢰도가 높은 편입니다."
        elif source == "fdr_daily":
            quality = 0.90
            note = "FinanceDataReader 일봉 데이터를 보조 소스로 사용했습니다."
        else:
            quality = 0.84
            note = "일봉 계열 데이터지만 공급처가 보조 소스라 해석을 한 단계 보수적으로 보는 편이 좋습니다."
    else:
        if source == "kis_intraday":
            quality = 0.94
            note = "KIS 분봉 데이터를 직접 사용했습니다."
        elif source == "hybrid_intraday":
            quality = 0.82
            note = "최근 분봉은 KIS, 과거 구간은 보조 소스를 섞어 사용했습니다."
        elif source in {"intraday_store", "yahoo_fallback"}:
            quality = 0.62 if timeframe in {"60m", "30m", "15m"} else 0.45
            note = "분봉은 공개 소스와 로컬 저장 캐시에 의존하므로 일봉보다 보수적으로 해석해야 합니다."
        else:
            quality = 0.52
            note = "분봉 데이터 품질이 제한적이라 No Signal로 떨어질 가능성이 높습니다."

    if fetch_status == "stored_recent":
        quality -= 0.02
        note = "최근에 저장한 장중 분봉을 다시 불러와 재사용하는 상태라 불필요한 API 호출은 줄였지만 최신성은 약간 보수적으로 해석해야 합니다."
    elif fetch_status == "scanner_store_only":
        quality -= 0.05
        note = "스캐너 절약 모드로 저장된 분봉만 사용했습니다. 실시간 장중 변화는 보수적으로 해석해야 합니다."
    elif fetch_status == "scanner_public_only":
        quality -= 0.07
        note = "스캐너 절약 모드로 KIS 대신 공개 분봉 소스를 사용했습니다."
    elif fetch_status == "scanner_public_augmented":
        quality -= 0.05
        note = "스캐너 절약 모드에서 공개 분봉과 저장 분봉을 함께 사용했습니다."
    elif fetch_status == "stored_fallback":
        quality -= 0.08
        note = "실시간 분봉 공급이 비어 저장된 분봉 캐시를 대신 사용했습니다."
    elif fetch_status == "kis_cooldown":
        quality -= 0.10
        note = "KIS 오류 직후 쿨다운 상태라 저장 분봉이나 공개 소스 위주로 해석하고 있습니다."
    elif fetch_status in {"intraday_rate_limited", "yahoo_rate_limited"}:
        quality -= 0.12
        note = "분봉 제공처 요청 제한이 걸려 저장 데이터 또는 일부 응답만 반영됐습니다."
    elif fetch_status in {"intraday_empty", "stored_empty", "intraday_unavailable", "yahoo_empty"}:
        quality -= 0.18
        note = "현재 요청한 타임프레임에서 사용 가능한 분봉 바 수가 충분하지 않습니다."
    elif fetch_status == "yahoo_symbol_missing":
        quality -= 0.14
        note = "해당 종목의 야후 심볼 매핑이 불안정해 분봉 공급이 끊겼습니다."
    elif fetch_status == "kis_not_configured":
        quality -= 0.06
        note = "KIS가 설정되지 않아 공개 소스만으로 분봉을 계산하고 있습니다."

    if stored_source:
        note = f"{note} 저장 원본: {stored_source}."

    quality = max(0.2, min(0.98, quality))
    return {
        "data_source": source,
        "data_quality": round(quality, 3),
        "source_note": note,
        "fetch_status": fetch_status,
        "fetch_status_label": _fetch_status_label(fetch_status),
        "fetch_message": fetch_message,
        "available_bars": available_bars,
    }


def _pattern_rank_score(pattern: PatternResult, completion_proximity: float, recency_score: float) -> float:
    state_bonus = {
        "confirmed": 0.18,
        "armed": 0.12,
        "forming": 0.05,
        "played_out": -0.20,
        "invalidated": -0.35,
    }.get(pattern.state, 0.0)
    quality = (
        0.30 * pattern.breakout_quality_fit
        + 0.22 * pattern.retest_quality_fit
        + 0.20 * pattern.leg_balance_fit
        + 0.20 * pattern.reversal_energy_fit
        + 0.08 * pattern.variant_fit
    )
    return 0.42 * pattern.textbook_similarity + 0.16 * completion_proximity + 0.14 * recency_score + 0.12 * quality + state_bonus


def _no_signal_text(timeframe: str, available_bars: int, source_note: str, fetch_message: str) -> tuple[str, str]:
    label = timeframe_label(timeframe)
    suffix = f" {fetch_message}" if fetch_message else ""
    if is_intraday_timeframe(timeframe):
        return (
            "분봉 데이터를 충분히 확보하지 못했습니다.",
            f"{label} 기준으로 사용 가능한 바 수가 {available_bars}개라 패턴과 확률을 안정적으로 계산하기 어렵습니다. {source_note}{suffix}",
        )
    return (
        "뚜렷한 패턴 신호가 약합니다.",
        f"{label} 기준으로는 교과서형 패턴이 충분히 선명하지 않아 확률을 강하게 제시하지 않았습니다.{suffix}",
    )


def _no_signal_action_plan(timeframe: str, data_quality: float, available_bars: int) -> dict[str, Any]:
    label = timeframe_label(timeframe)
    if is_intraday_timeframe(timeframe):
        return {
            "action_plan": "recheck",
            "action_plan_label": "재확인 필요",
            "action_plan_summary": (
                f"{label} 데이터가 아직 충분하지 않아 매매 후보로 올리기보다 장중 데이터가 더 쌓인 뒤 다시 확인하는 구간입니다. "
                f"현재 사용 가능 봉 수는 {available_bars}개이고 데이터 신뢰도는 {round(data_quality * 100)}%입니다."
            ),
            "action_priority_score": round(max(0.0, min(1.0, data_quality * 0.35)), 3),
        }
    return {
        "action_plan": "cooling",
        "action_plan_label": "관망",
        "action_plan_summary": (
            f"{label} 기준으로 뚜렷한 패턴 신호가 없어 신규 판단을 보류하는 편이 안전합니다. "
            "패턴이 새로 형성되거나 거래량/추세 정렬이 개선될 때 다시 후보로 올리는 흐름입니다."
        ),
        "action_priority_score": round(max(0.0, min(1.0, data_quality * 0.25)), 3),
    }


def _action_plan_profile(
    timeframe: str,
    pattern: PatternResult,
    p_up: float,
    p_down: float,
    entry_score: float,
    completion_proximity: float,
    recency_score: float,
    data_quality: float,
    reward_risk_ratio: float,
    headroom_score: float,
    historical_edge_score: float,
    trend_alignment_score: float,
    intraday_session_score: float,
    target_hit_at: str | None,
    invalidated_at: str | None,
    fetch_status: str,
) -> dict[str, Any]:
    rr_score = min(1.0, max(0.0, reward_risk_ratio / 2.4))
    priority = (
        0.20 * entry_score
        + 0.14 * completion_proximity
        + 0.12 * recency_score
        + 0.12 * data_quality
        + 0.12 * rr_score
        + 0.10 * headroom_score
        + 0.10 * historical_edge_score
        + 0.10 * trend_alignment_score
    )
    if is_intraday_timeframe(timeframe):
        priority = priority * 0.86 + intraday_session_score * 0.14

    if pattern.state in {"played_out", "invalidated"} or target_hit_at or invalidated_at:
        priority -= 0.22
    if fetch_status in {"kis_cooldown", "intraday_rate_limited", "yahoo_rate_limited", "stored_fallback"}:
        priority -= 0.08
    if data_quality < 0.55:
        priority -= 0.10
    if reward_risk_ratio < 1.0 or headroom_score < 0.18:
        priority -= 0.12
    if recency_score < 0.28:
        priority -= 0.08

    priority = round(max(0.0, min(1.0, priority)), 3)
    bullish = p_up >= p_down
    direction = "상승" if bullish else "하락"
    label = timeframe_label(timeframe)

    if invalidated_at or pattern.state == "invalidated":
        return {
            "action_plan": "cooling",
            "action_plan_label": "관망/무효",
            "action_plan_summary": (
                f"{label} 기준 기존 패턴이 무효화된 상태입니다. 같은 모양을 계속 추격하기보다 새 지지/저항 구조가 만들어지는지 다시 봐야 합니다."
            ),
            "action_priority_score": priority,
        }

    if target_hit_at or pattern.state == "played_out" or headroom_score < 0.16:
        return {
            "action_plan": "cooling",
            "action_plan_label": "목표 도달 후 관망",
            "action_plan_summary": (
                f"{label} 기준 기존 패턴의 목표가 여지가 대부분 소진된 구간입니다. 확률보다 남은 기대수익과 재진입 구조를 우선 확인해야 합니다."
            ),
            "action_priority_score": priority,
        }

    if data_quality < 0.58 or fetch_status in {"kis_cooldown", "intraday_rate_limited", "yahoo_rate_limited"}:
        return {
            "action_plan": "recheck",
            "action_plan_label": "데이터 재확인",
            "action_plan_summary": (
                f"{label} 데이터 품질이나 수집 상태가 약해 {direction} 시나리오를 바로 신뢰하기 어렵습니다. 최신 봉이 갱신된 뒤 다시 계산하는 후보입니다."
            ),
            "action_priority_score": priority,
        }

    if priority >= 0.68 and max(p_up, p_down) >= 0.57 and reward_risk_ratio >= 1.15 and pattern.state in {"confirmed", "armed"}:
        return {
            "action_plan": "ready_now",
            "action_plan_label": "즉시 대응 후보",
            "action_plan_summary": (
                f"{label} 기준 패턴 완성도, 최근성, 손익비가 함께 맞는 편입니다. 다만 실제 진입은 기준선 이탈 여부와 거래량 확인을 같이 봐야 합니다."
            ),
            "action_priority_score": priority,
        }

    if pattern.state in {"forming", "armed"} or completion_proximity >= 0.45:
        return {
            "action_plan": "watch",
            "action_plan_label": "형성 관찰",
            "action_plan_summary": (
                f"{label} 기준 패턴이 만들어지는 중입니다. 완성 신호 전에는 예측보다 목선/지지선 반응, 캔들 확인, 거래량 확장을 기다리는 쪽이 좋습니다."
            ),
            "action_priority_score": priority,
        }

    return {
        "action_plan": "recheck",
        "action_plan_label": "재평가 후보",
        "action_plan_summary": (
            f"{label} 기준 패턴은 감지됐지만 우선순위가 높지는 않습니다. 다른 타임프레임 정렬이나 새 확인봉이 붙으면 다시 후보군에 올리는 흐름입니다."
        ),
        "action_priority_score": priority,
    }


def _no_signal_decision_support(timeframe: str, data_quality: float, available_bars: int, fetch_status: str) -> dict[str, Any]:
    flags: list[str] = []
    checklist: list[str] = []
    label = timeframe_label(timeframe)

    if available_bars < get_timeframe_spec(timeframe).min_bars:
        flags.append(f"{label} 분석에 필요한 봉 수가 부족합니다.")
    if data_quality < 0.65:
        flags.append("데이터 품질이 낮아 신호를 보수적으로 봐야 합니다.")
    if fetch_status in {"kis_cooldown", "intraday_rate_limited", "yahoo_rate_limited"}:
        flags.append("데이터 공급처 제한/쿨다운으로 최신성이 약할 수 있습니다.")
    if not flags:
        flags.append("교과서형 패턴이 아직 충분히 선명하지 않습니다.")

    if is_intraday_timeframe(timeframe):
        checklist.extend(
            [
                "장중 최신 봉이 추가된 뒤 다시 스캔하기",
                "상위 타임프레임(60분/일봉) 방향과 같은지 확인하기",
                "거래량이 평균보다 붙는 구간만 후보로 보기",
            ]
        )
    else:
        checklist.extend(
            [
                "새 지지/저항 구조가 생기는지 확인하기",
                "거래량 감소 후 돌파 거래량이 붙는지 확인하기",
                "일봉/주봉 방향이 서로 충돌하지 않는지 확인하기",
            ]
        )

    return {
        "risk_flags": flags[:5],
        "confirmation_checklist": checklist[:5],
        "next_trigger": "패턴 구조가 새로 감지되거나 데이터 품질이 회복되면 다시 후보로 올립니다.",
    }


def _decision_support_profile(
    timeframe: str,
    pattern: PatternResult,
    action_plan: dict[str, Any],
    p_up: float,
    p_down: float,
    confidence: float,
    data_quality: float,
    reward_risk_ratio: float,
    headroom_score: float,
    target_distance_pct: float,
    stop_distance_pct: float,
    recency_score: float,
    sample_reliability: float,
    trend_alignment_score: float,
    wyckoff_phase: str,
    intraday_session_score: float,
    fetch_status: str,
    target_hit_at: str | None,
    invalidated_at: str | None,
    bars_since_signal: int | None,
) -> dict[str, Any]:
    flags: list[str] = []
    checklist: list[str] = []
    bullish = _is_bullish(pattern.pattern_type)
    bearish = _is_bearish(pattern.pattern_type)
    direction = "상승" if bullish or (not bearish and p_up >= p_down) else "하락"
    pattern_name = pattern.pattern_type.replace("_", " ")

    if invalidated_at or pattern.state == "invalidated":
        flags.append("기존 패턴이 무효화되어 같은 구조를 계속 추격하면 위험합니다.")
    if target_hit_at or pattern.state == "played_out":
        flags.append("기존 목표가를 이미 한 번 소화한 패턴입니다.")
    if headroom_score < 0.25 or target_distance_pct < 0.025:
        flags.append("현재가에서 목표가까지 남은 여지가 작습니다.")
    if reward_risk_ratio < 1.2:
        flags.append("손익비가 낮아 작은 흔들림에도 기대값이 훼손됩니다.")
    if confidence < 0.42:
        flags.append("종합 신뢰도가 아직 낮습니다.")
    if data_quality < 0.65:
        flags.append("데이터 품질이 낮아 최신 봉 반영을 재확인해야 합니다.")
    if sample_reliability < 0.35:
        flags.append("유사 패턴 표본 신뢰도가 낮습니다.")
    if recency_score < 0.35:
        flags.append("감지된 신호가 다소 오래되어 현재 구조와 어긋날 수 있습니다.")
    if trend_alignment_score < 0.45:
        flags.append("추세 정렬이 약해 패턴 단독 판단은 위험합니다.")
    if bullish and wyckoff_phase in {"distribution", "markdown"}:
        flags.append("와이코프 국면이 상승 패턴과 충돌합니다.")
    if bearish and wyckoff_phase in {"accumulation", "markup"}:
        flags.append("와이코프 국면이 하락 패턴과 충돌합니다.")
    if is_intraday_timeframe(timeframe) and intraday_session_score < 0.48:
        flags.append("분봉 시간대 품질이 낮아 단타 진입 타이밍이 애매합니다.")
    if fetch_status in {"kis_cooldown", "stored_fallback", "scanner_store_only", "scanner_public_only"}:
        flags.append("실시간 KIS 데이터가 아닌 저장/공개 데이터 비중이 큽니다.")

    if pattern.state == "forming":
        checklist.append("완성 전 예측 매수보다 목선/저항선 반응을 먼저 확인하기")
    elif pattern.state == "armed":
        checklist.append("돌파 직전 후보이므로 기준선 돌파와 거래량 확장을 함께 확인하기")
    elif pattern.state == "confirmed":
        checklist.append("돌파 후 지지/저항 재확인과 손절 기준 이탈 여부 확인하기")
    else:
        checklist.append("새 구조가 만들어질 때까지 같은 패턴 재활용을 피하기")

    if pattern.neckline:
        relation = "상향 돌파" if direction == "상승" else "하향 이탈"
        checklist.append(f"목선 {pattern.neckline:,.0f}원 {relation} 후 종가 유지 확인하기")
    if pattern.invalidation_level:
        checklist.append(f"무효화 기준 {pattern.invalidation_level:,.0f}원 이탈 여부 확인하기")
    if pattern.target_level and action_plan.get("action_plan") != "cooling":
        checklist.append(f"1차 목표 {pattern.target_level:,.0f}원까지 남은 공간과 손익비 확인하기")
    if stop_distance_pct > 0.0:
        checklist.append(f"손절폭이 현재가 대비 {stop_distance_pct:.1%} 수준인지 감당 가능한지 확인하기")
    if bars_since_signal is not None and bars_since_signal > 0:
        checklist.append(f"신호 이후 {bars_since_signal}개 봉이 지나며 구조가 유지되는지 확인하기")
    if is_intraday_timeframe(timeframe):
        checklist.append("분봉은 KIS 최신 데이터 갱신 후 같은 판단이 유지되는지 재확인하기")
    else:
        checklist.append("상위/하위 타임프레임이 같은 방향인지 함께 확인하기")

    if action_plan.get("action_plan") == "ready_now":
        next_trigger = f"{pattern_name} 기준선 확인 후 {direction} 방향 추세가 유지되면 우선 후보입니다."
    elif action_plan.get("action_plan") == "watch":
        next_trigger = "완성 신호가 붙을 때까지 기다렸다가 돌파/재시험 품질을 확인합니다."
    elif action_plan.get("action_plan") == "recheck":
        next_trigger = "최신 데이터와 다음 확인봉이 들어온 뒤 같은 점수가 유지되는지 재계산합니다."
    else:
        next_trigger = "목표 소진/무효 가능성이 커서 새 패턴이 만들어질 때까지 관망합니다."

    if not flags:
        flags.append("치명적 리스크 플래그는 적지만, 기준선 이탈 여부는 계속 확인해야 합니다.")

    return {
        "risk_flags": flags[:6],
        "confirmation_checklist": checklist[:6],
        "next_trigger": next_trigger,
    }


def _readiness_label(score: float) -> str:
    if score >= 0.72:
        return "실전 후보"
    if score >= 0.58:
        return "관찰 후보"
    if score >= 0.44:
        return "재확인 필요"
    return "보류"


def _trade_readiness_profile(
    *,
    timeframe: str,
    pattern: PatternResult | None,
    action_plan: dict[str, Any],
    p_up: float,
    p_down: float,
    entry_score: float,
    confidence: float,
    completion_proximity: float,
    recency_score: float,
    data_quality: float,
    reward_risk_ratio: float,
    headroom_score: float,
    sample_reliability: float,
    historical_edge_score: float,
    trend_alignment_score: float,
    intraday_session_score: float,
    target_hit_at: str | None,
    invalidated_at: str | None,
    bars_since_signal: int | None,
) -> dict[str, Any]:
    action_score = {
        "ready_now": 0.86,
        "watch": 0.62,
        "recheck": 0.38,
        "cooling": 0.16,
    }.get(str(action_plan.get("action_plan") or "watch"), 0.45)

    if pattern is None:
        factors = [
            {"label": "데이터", "score": round(data_quality, 3), "weight": 0.35, "note": "사용 가능한 봉 수와 데이터 출처 기준입니다."},
            {"label": "패턴", "score": 0.0, "weight": 0.35, "note": "현재 의미 있는 패턴이 확인되지 않았습니다."},
            {"label": "재확인", "score": action_score, "weight": 0.30, "note": str(action_plan.get("action_plan_summary") or "")},
        ]
        score = sum(float(item["score"]) * float(item["weight"]) for item in factors)
        return {
            "trade_readiness_score": round(max(0.0, min(1.0, score)), 3),
            "trade_readiness_label": _readiness_label(score),
            "trade_readiness_summary": "패턴이 없거나 데이터가 부족해 실전 후보가 아니라 관찰/재확인 후보로만 봅니다.",
            "score_factors": factors,
        }

    formation_quality = max(
        0.0,
        min(
            1.0,
            0.24 * pattern.textbook_similarity
            + 0.18 * pattern.leg_balance_fit
            + 0.18 * pattern.reversal_energy_fit
            + 0.16 * pattern.breakout_quality_fit
            + 0.14 * pattern.retest_quality_fit
            + 0.10 * pattern.variant_fit,
        ),
    )
    probability_score = max(p_up, p_down) * 0.58 + confidence * 0.42
    timing_score = 0.55 * recency_score + 0.45 * completion_proximity
    rr_score = min(1.0, max(0.0, reward_risk_ratio / 2.4))
    opportunity_score = 0.56 * rr_score + 0.44 * headroom_score
    evidence_score = 0.56 * sample_reliability + 0.44 * historical_edge_score
    context_score = trend_alignment_score
    if is_intraday_timeframe(timeframe):
        context_score = 0.62 * trend_alignment_score + 0.38 * intraday_session_score

    if pattern.state in {"played_out", "invalidated"} or target_hit_at or invalidated_at:
        timing_score = min(timing_score, 0.16)
        opportunity_score = min(opportunity_score, 0.20)
        action_score = min(action_score, 0.18)
    if bars_since_signal is not None and bars_since_signal > 0 and recency_score < 0.35:
        timing_score = min(timing_score, 0.34)

    factors = [
        {
            "label": "패턴 완성도",
            "score": round(formation_quality, 3),
            "weight": 0.16,
            "note": "교과서 유사도, 레그 균형, 반전 에너지, 돌파/리테스트 품질을 합산했습니다.",
        },
        {
            "label": "타이밍",
            "score": round(timing_score, 3),
            "weight": 0.15,
            "note": "완성 임박도와 신호 최신성을 함께 봅니다. 목표 도달/무효화 패턴은 강하게 깎습니다.",
        },
        {
            "label": "확률/신뢰도",
            "score": round(probability_score, 3),
            "weight": 0.14,
            "note": "상승/하락 우위 확률과 종합 신뢰도를 같이 반영합니다.",
        },
        {
            "label": "손익비/여지",
            "score": round(opportunity_score, 3),
            "weight": 0.15,
            "note": "목표까지 남은 공간과 손절 거리 대비 기대 보상을 봅니다.",
        },
        {
            "label": "데이터 품질",
            "score": round(data_quality, 3),
            "weight": 0.11,
            "note": "KRX/KIS/공개/저장 캐시 출처와 수집 상태를 반영합니다.",
        },
        {
            "label": "통계 근거",
            "score": round(evidence_score, 3),
            "weight": 0.12,
            "note": "유사 패턴 표본 신뢰도와 백테스트 edge를 합산했습니다.",
        },
        {
            "label": "추세/세션",
            "score": round(context_score, 3),
            "weight": 0.10,
            "note": "상위 추세 정렬과 분봉의 장중 시간대 품질을 봅니다.",
        },
        {
            "label": "실전 액션",
            "score": round(action_score, 3),
            "weight": 0.07,
            "note": str(action_plan.get("action_plan_summary") or ""),
        },
    ]

    raw_score = sum(float(item["score"]) * float(item["weight"]) for item in factors)
    if action_plan.get("action_plan") == "cooling":
        raw_score = min(raw_score, 0.42)
    elif action_plan.get("action_plan") == "recheck":
        raw_score = min(raw_score, 0.56)
    if data_quality < 0.55:
        raw_score = min(raw_score, 0.52)
    if reward_risk_ratio < 1.0 or headroom_score < 0.15:
        raw_score = min(raw_score, 0.48)

    score = round(max(0.0, min(1.0, raw_score)), 3)
    label = _readiness_label(score)
    if label == "실전 후보":
        summary = "패턴, 타이밍, 손익비, 데이터 근거가 동시에 맞는 편입니다. 그래도 실제 매매 전에는 트리거와 무효화 기준을 먼저 확인해야 합니다."
    elif label == "관찰 후보":
        summary = "구조는 볼 만하지만 아직 한두 가지 조건이 부족합니다. 바로 추격하기보다 다음 트리거를 기다리는 쪽이 안전합니다."
    elif label == "재확인 필요":
        summary = "일부 신호는 있지만 데이터, 타이밍, 손익비 중 약한 부분이 있습니다. 최신 봉 갱신 후 다시 판단하는 후보입니다."
    else:
        summary = "목표 도달, 무효화, 낮은 손익비, 낮은 데이터 신뢰도 중 하나 이상이 커서 현재 실전 후보로 보기는 어렵습니다."

    return {
        "trade_readiness_score": score,
        "trade_readiness_label": label,
        "trade_readiness_summary": summary,
        "score_factors": factors,
    }


def _future_timestamp(last_ts: pd.Timestamp, timeframe: str, step: int) -> pd.Timestamp:
    base = pd.Timestamp(last_ts)
    if timeframe == "1mo":
        return base + DateOffset(months=step)
    if timeframe == "1wk":
        return base + DateOffset(weeks=step)
    if timeframe == "1d":
        return base + BDay(step)
    if timeframe == "60m":
        return base + pd.Timedelta(hours=step)
    if timeframe == "30m":
        return base + pd.Timedelta(minutes=30 * step)
    if timeframe == "15m":
        return base + pd.Timedelta(minutes=15 * step)
    return base + pd.Timedelta(minutes=step)


def _format_projection_dt(ts: pd.Timestamp, timeframe: str) -> str:
    return ts.isoformat() if is_intraday_timeframe(timeframe) else ts.date().isoformat()


def _projection_horizon(timeframe: str) -> list[int]:
    if timeframe == "1mo":
        return [1, 2, 3, 4]
    if timeframe == "1wk":
        return [1, 2, 4, 6]
    if timeframe == "1d":
        return [3, 7, 12, 20]
    if timeframe == "60m":
        return [4, 8, 16, 24]
    if timeframe == "30m":
        return [4, 10, 20, 30]
    if timeframe == "15m":
        return [6, 12, 24, 36]
    return [10, 20, 40, 60]


def _projected_points(
    last_ts: pd.Timestamp,
    timeframe: str,
    prices: list[tuple[int, float, str]],
) -> list[ProjectionPoint]:
    points: list[ProjectionPoint] = []
    for step, price, kind in prices:
        future_ts = _future_timestamp(last_ts, timeframe, step)
        points.append(
            ProjectionPoint(
                dt=_format_projection_dt(future_ts, timeframe),
                price=round(price, 2),
                kind=kind,
            )
        )
    return points


def _build_projection(
    df: pd.DataFrame,
    timeframe: str,
    pattern: PatternResult,
    current_close: float,
    target_hit_at: str | None,
    invalidated_at: str | None,
) -> tuple[str, str, list[ProjectionPoint]]:
    last_ts = _timestamp_series(df).iloc[-1]
    neckline = pattern.neckline or current_close
    target = pattern.target_level or current_close
    invalidation = pattern.invalidation_level or current_close
    span = max(abs(target - neckline), abs(current_close - invalidation), current_close * 0.04)
    bullish = _is_bullish(pattern.pattern_type)
    pattern_name = pattern.pattern_type.replace("_", " ")
    steps = _projection_horizon(timeframe)

    if pattern.state == "played_out":
        base = max(neckline, current_close - span * 0.35) if bullish else min(neckline, current_close + span * 0.35)
        drift = current_close + span * 0.12 if bullish else current_close - span * 0.12
        prices = [
            (steps[0], base, "cooldown"),
            (steps[1], (base + current_close) / 2, "retest"),
            (steps[2], current_close, "range"),
            (steps[3], drift, "rebuild"),
        ]
        summary = (
            f"기존 {pattern_name} 패턴은 이미 1차 목표가에 도달해 종료된 것으로 보는 편이 맞습니다. "
            f"다음 흐름은 재축적 또는 박스권 정리 여부를 새 패턴으로 다시 보는 편이 좋습니다."
        )
        return "1차 목표 달성 후 재축적 시나리오", summary, _projected_points(last_ts, timeframe, prices)

    if pattern.state == "invalidated":
        drift = invalidation - span * 0.15 if bullish else invalidation + span * 0.15
        prices = [
            (steps[0], invalidation, "broken"),
            (steps[1], drift, "followthrough"),
            (steps[2], drift * (1.01 if bullish else 0.99), "bounce"),
            (steps[3], drift, "range"),
        ]
        summary = (
            f"{pattern_name} 패턴은 이미 무효화된 쪽으로 보는 게 안전합니다. "
            f"기존 패턴 추종보다 새로운 바닥/천장 형성이 나오는지 다시 기다리는 편이 좋습니다."
        )
        return "무효화 이후 재정비 시나리오", summary, _projected_points(last_ts, timeframe, prices)

    if bullish:
        if pattern.state == "forming":
            prices = [
                (steps[0], max(current_close - span * 0.12, invalidation * 1.01), "handle"),
                (steps[1], neckline * 0.995, "trigger"),
                (steps[2], neckline * 1.02, "breakout"),
                (steps[3], target, "target"),
            ]
            summary = (
                f"{pattern_name} 패턴이 아직 완성 전이라 목선 부근까지 구조를 더 만드는 흐름을 우선 가정합니다. "
                f"목선 돌파가 실제로 나오기 전까지는 예비 시나리오로만 보는 편이 좋습니다."
            )
            return "패턴 완성 시도 시나리오", summary, _projected_points(last_ts, timeframe, prices)

        if pattern.state == "armed":
            prices = [
                (steps[0], neckline * 0.998, "trigger"),
                (steps[1], neckline * 1.01, "breakout"),
                (steps[2], max(neckline, current_close - span * 0.08), "retest"),
                (steps[3], target, "target"),
            ]
            summary = (
                f"{pattern_name} 패턴은 완성 직전으로 보고 있습니다. "
                f"짧은 눌림 이후 목선 돌파 확인과 목표가 접근 흐름을 기본 시나리오로 둡니다."
            )
            return "돌파 임박 시나리오", summary, _projected_points(last_ts, timeframe, prices)

        prices = [
            (steps[0], max(neckline, current_close - span * 0.1), "retest"),
            (steps[1], current_close + span * 0.12, "hold"),
            (steps[2], target, "target"),
            (steps[3], target + span * 0.12, "extension"),
        ]
        summary = (
            f"{pattern_name} 패턴은 이미 확인된 것으로 보고 있어 짧은 눌림 뒤 목표가 재도전 흐름을 기본으로 둡니다. "
            f"다만 {target_hit_at or '현재까지'} 목표가가 이미 닿은 적 없다면 retest 성공 여부를 먼저 확인해야 합니다."
        )
        return "확인 후 retest 시나리오", summary, _projected_points(last_ts, timeframe, prices)

    if pattern.state == "forming":
        prices = [
            (steps[0], min(current_close + span * 0.12, invalidation * 0.99), "handle"),
            (steps[1], neckline * 1.005, "trigger"),
            (steps[2], neckline * 0.98, "breakdown"),
            (steps[3], target, "target"),
        ]
        summary = (
            f"{pattern_name} 패턴이 아직 완성 전이라 지지 붕괴 구조를 더 만드는 흐름을 우선 가정합니다. "
            f"목선 이탈이 확정되기 전까지는 예비 시나리오로 봐야 합니다."
        )
        return "하락 패턴 완성 시도", summary, _projected_points(last_ts, timeframe, prices)

    if pattern.state == "armed":
        prices = [
            (steps[0], neckline * 1.002, "trigger"),
            (steps[1], neckline * 0.99, "breakdown"),
            (steps[2], min(neckline, current_close + span * 0.08), "retest"),
            (steps[3], target, "target"),
        ]
        summary = (
            f"{pattern_name} 패턴은 하락 완성 직전으로 보고 있습니다. "
            f"짧은 반등 뒤 지지 이탈 확인과 목표가 접근 흐름을 기본 시나리오로 둡니다."
        )
        return "이탈 임박 시나리오", summary, _projected_points(last_ts, timeframe, prices)

    prices = [
        (steps[0], min(neckline, current_close + span * 0.1), "retest"),
        (steps[1], current_close - span * 0.12, "hold"),
        (steps[2], target, "target"),
        (steps[3], target - span * 0.12, "extension"),
    ]
    summary = (
        f"{pattern_name} 패턴은 이미 확인된 것으로 보고 있어 짧은 반등 뒤 목표가 재도전 흐름을 기본으로 둡니다. "
        f"무효화 기준을 넘기면 기존 시나리오는 바로 폐기해야 합니다."
    )
    return "확인 후 retest 시나리오", summary, _projected_points(last_ts, timeframe, prices)


def build_no_signal_snapshot(
    symbol: SymbolInfo,
    timeframe: str,
    df: pd.DataFrame,
) -> AnalysisResult:
    profile = _data_profile(df, timeframe)
    no_signal_reason, reason_summary = _no_signal_text(
        timeframe,
        profile["available_bars"],
        profile["source_note"],
        profile["fetch_message"],
    )
    action_plan = _no_signal_action_plan(timeframe, profile["data_quality"], profile["available_bars"])
    decision_support = _no_signal_decision_support(
        timeframe,
        profile["data_quality"],
        profile["available_bars"],
        profile["fetch_status"],
    )
    readiness = _trade_readiness_profile(
        timeframe=timeframe,
        pattern=None,
        action_plan=action_plan,
        p_up=0.5,
        p_down=0.5,
        entry_score=0.0,
        confidence=0.0,
        completion_proximity=0.0,
        recency_score=0.0,
        data_quality=profile["data_quality"],
        reward_risk_ratio=0.0,
        headroom_score=0.0,
        sample_reliability=0.0,
        historical_edge_score=0.0,
        trend_alignment_score=0.0,
        intraday_session_score=0.5,
        target_hit_at=None,
        invalidated_at=None,
        bars_since_signal=None,
    )
    return AnalysisResult(
        symbol=symbol,
        timeframe=timeframe,
        timeframe_label=timeframe_label(timeframe),
        p_up=0.5,
        p_down=0.5,
        textbook_similarity=0.0,
        pattern_confirmation_score=0.0,
        confidence=0.0,
        entry_score=0.0,
        completion_proximity=0.0,
        recency_score=0.0,
        reward_risk_ratio=0.0,
        headroom_score=0.0,
        target_distance_pct=0.0,
        stop_distance_pct=0.0,
        avg_mfe_pct=0.0,
        avg_mae_pct=0.0,
        avg_bars_to_outcome=0.0,
        historical_edge_score=0.0,
        trend_alignment_score=0.0,
        trend_direction="sideways",
        trend_warning="",
        wyckoff_phase="neutral",
        wyckoff_score=0.0,
        wyckoff_note="",
        intraday_session_phase="neutral",
        intraday_session_score=0.5,
        intraday_session_note="",
        action_plan=action_plan["action_plan"],
        action_plan_label=action_plan["action_plan_label"],
        action_plan_summary=action_plan["action_plan_summary"],
        action_priority_score=action_plan["action_priority_score"],
        risk_flags=decision_support["risk_flags"],
        confirmation_checklist=decision_support["confirmation_checklist"],
        next_trigger=decision_support["next_trigger"],
        trade_readiness_score=readiness["trade_readiness_score"],
        trade_readiness_label=readiness["trade_readiness_label"],
        trade_readiness_summary=readiness["trade_readiness_summary"],
        score_factors=readiness["score_factors"],
        no_signal_flag=True,
        no_signal_reason=no_signal_reason,
        reason_summary=reason_summary,
        sample_size=0,
        empirical_win_rate=0.5,
        sample_reliability=0.0,
        patterns=[],
        projection_label="예측 보류",
        projection_summary="현재는 유의미한 패턴이 없어 미래 경로를 예측하지 않습니다.",
        projected_path=[],
        is_provisional=True,
        updated_at=datetime.utcnow().isoformat(),
        data_source=profile["data_source"],
        data_quality=profile["data_quality"],
        source_note=profile["source_note"],
        fetch_status=profile["fetch_status"],
        fetch_status_label=profile["fetch_status_label"],
        fetch_message=profile["fetch_message"],
        liquidity_score=0.0,
        avg_turnover_billion=0.0,
        bars_since_signal=None,
        stats_timeframe=_stats_timeframe(timeframe),
        available_bars=profile["available_bars"],
    )


async def analyze_symbol_dataframe(
    symbol: SymbolInfo,
    timeframe: str,
    df: pd.DataFrame,
) -> AnalysisResult:
    profile = _data_profile(df, timeframe)
    if df.empty or len(df) < max(20, get_timeframe_spec(timeframe).min_bars):
        return build_no_signal_snapshot(symbol, timeframe, df)

    current_close, current_high, current_low = _current_ohlc(df)
    engine = PatternEngine()
    raw_patterns = engine.detect_all(df)
    if not raw_patterns:
        return build_no_signal_snapshot(symbol, timeframe, df)

    patterns_with_meta: list[tuple[PatternResult, float, float, int, str | None, str | None]] = []
    for pattern in raw_patterns:
        refreshed, target_hit_at, invalidated_at = _refresh_pattern_state(df, pattern, current_close, current_high, current_low)
        bars_since_signal = _bars_since_pattern(df, refreshed)
        recency = _recency_score(timeframe, bars_since_signal)
        completion = _completion_proximity(refreshed, current_close)
        patterns_with_meta.append((refreshed, completion, recency, bars_since_signal, target_hit_at, invalidated_at))

    patterns_with_meta.sort(key=lambda item: _pattern_rank_score(item[0], item[1], item[2]), reverse=True)
    best_pattern, best_completion, best_recency, bars_since_signal, best_target_hit_at, best_invalidated_at = patterns_with_meta[0]

    turnover_billion = _average_turnover_billion(df)
    liquidity = _liquidity_score(turnover_billion)
    stats_timeframe = _stats_timeframe(timeframe)
    stats = await get_pattern_stats(best_pattern.pattern_type, stats_timeframe)
    similar_win_rate = float(stats.get("win_rate", 0.55))
    sample_size = int(stats.get("sample_size", 0))
    wins = int(stats.get("wins", 0))
    total = int(stats.get("total", sample_size))
    avg_mfe_pct = float(stats.get("avg_mfe_pct", 0.0))
    avg_mae_pct = float(stats.get("avg_mae_pct", 0.0))
    avg_bars_to_outcome = float(stats.get("avg_bars_to_outcome", 0.0))
    historical_edge_score = float(stats.get("historical_edge_score", 0.5))
    trend_profile = _trend_alignment_profile(df, best_pattern.pattern_type)
    wyckoff_profile = _wyckoff_profile(df, best_pattern.pattern_type)
    intraday_profile = _intraday_session_profile(df, timeframe, best_pattern.pattern_type)
    regime_match = trend_profile["trend_alignment_score"]
    opportunity = _opportunity_profile(best_pattern, current_close)

    risk_penalty = 0.0
    if profile["data_quality"] < 0.65:
        risk_penalty += 0.10
    if liquidity < 0.45:
        risk_penalty += 0.08
    if best_recency < 0.3:
        risk_penalty += 0.08
    if best_pattern.state == "played_out":
        risk_penalty += 0.18
    if trend_profile["trend_alignment_score"] < 0.35:
        risk_penalty += 0.18
    elif trend_profile["trend_alignment_score"] < 0.55:
        risk_penalty += 0.08
    if best_pattern.state == "confirmed" and best_pattern.breakout_quality_fit < 0.42:
        risk_penalty += 0.14
    if best_pattern.state in {"confirmed", "armed"} and best_pattern.retest_quality_fit < 0.35:
        risk_penalty += 0.10
    if best_pattern.leg_balance_fit < 0.42:
        risk_penalty += 0.12
    elif best_pattern.leg_balance_fit < 0.55:
        risk_penalty += 0.06
    if best_pattern.reversal_energy_fit < 0.38:
        risk_penalty += 0.14
    elif best_pattern.reversal_energy_fit < 0.52:
        risk_penalty += 0.07
    if best_pattern.variant_fit < 0.58:
        risk_penalty += 0.10
    elif best_pattern.variant_fit < 0.70:
        risk_penalty += 0.05
    if best_pattern.candlestick_confirmation_fit < 0.34:
        risk_penalty += 0.12
    elif best_pattern.candlestick_confirmation_fit < 0.48:
        risk_penalty += 0.06
    if is_intraday_timeframe(timeframe):
        if intraday_profile["intraday_session_score"] < 0.34:
            risk_penalty += 0.12
        elif intraday_profile["intraday_session_score"] < 0.48:
            risk_penalty += 0.06
        elif intraday_profile["intraday_session_score"] > 0.82:
            risk_penalty -= 0.02
    if _is_bullish(best_pattern.pattern_type):
        if wyckoff_profile["wyckoff_phase"] == "markdown":
            risk_penalty += 0.16
        elif wyckoff_profile["wyckoff_phase"] == "distribution":
            risk_penalty += 0.10
        elif wyckoff_profile["wyckoff_phase"] == "accumulation":
            risk_penalty -= 0.03
        elif wyckoff_profile["wyckoff_phase"] == "markup":
            risk_penalty -= 0.02
    elif _is_bearish(best_pattern.pattern_type):
        if wyckoff_profile["wyckoff_phase"] == "markup":
            risk_penalty += 0.16
        elif wyckoff_profile["wyckoff_phase"] == "accumulation":
            risk_penalty += 0.10
        elif wyckoff_profile["wyckoff_phase"] == "distribution":
            risk_penalty -= 0.03
        elif wyckoff_profile["wyckoff_phase"] == "markdown":
            risk_penalty -= 0.02
    risk_penalty = max(0.0, risk_penalty)
    if opportunity["reward_risk_ratio"] < 1.2:
        risk_penalty += 0.12
    if opportunity["headroom_score"] < 0.2:
        risk_penalty += 0.14
    if historical_edge_score < 0.28:
        risk_penalty += 0.12
    elif historical_edge_score < 0.40:
        risk_penalty += 0.06

    probability = compute_probability(
        best_pattern,
        similar_win_rate=similar_win_rate,
        sample_size=sample_size,
        liquidity_score=liquidity,
        multi_tf_agreement=0.55,
        regime_match=regime_match,
        data_quality=profile["data_quality"],
        risk_penalty=risk_penalty,
        completion_proximity=best_completion,
        recency_score=best_recency,
        reward_risk_ratio=opportunity["reward_risk_ratio"],
        headroom_score=opportunity["headroom_score"],
        target_distance_pct=opportunity["target_distance_pct"],
        stop_distance_pct=opportunity["stop_distance_pct"],
        avg_mfe_pct=avg_mfe_pct,
        avg_mae_pct=avg_mae_pct,
        avg_bars_to_outcome=avg_bars_to_outcome,
        historical_edge_score=historical_edge_score,
        wins=wins,
        total=total,
    )

    projection_label, projection_summary, projected_path = _build_projection(
        df,
        timeframe,
        best_pattern,
        current_close,
        best_target_hit_at,
        best_invalidated_at,
    )

    pattern_infos: list[PatternInfo] = []
    for pattern, _, _, _, target_hit_at, invalidated_at in patterns_with_meta:
        pattern_infos.append(
            PatternInfo(
                pattern_type=pattern.pattern_type,
                state=pattern.state,
                grade=pattern.grade,
                variant=pattern.variant,
                textbook_similarity=pattern.textbook_similarity,
                geometry_fit=pattern.geometry_fit,
                leg_balance_fit=pattern.leg_balance_fit,
                reversal_energy_fit=pattern.reversal_energy_fit,
                variant_fit=pattern.variant_fit,
                volume_context_fit=pattern.volume_context_fit,
                volatility_context_fit=pattern.volatility_context_fit,
                breakout_quality_fit=pattern.breakout_quality_fit,
                retest_quality_fit=pattern.retest_quality_fit,
                candlestick_confirmation_fit=pattern.candlestick_confirmation_fit,
                candlestick_label=pattern.candlestick_label,
                candlestick_note=pattern.candlestick_note,
                neckline=pattern.neckline,
                invalidation_level=pattern.invalidation_level,
                target_level=pattern.target_level,
                key_points=pattern.key_points,
                is_provisional=pattern.is_provisional,
                start_dt=pattern.start_dt.isoformat(),
                end_dt=pattern.end_dt.isoformat() if pattern.end_dt else None,
                target_hit_at=target_hit_at,
                invalidated_at=invalidated_at,
            )
        )

    if probability.no_signal_flag and not probability.no_signal_reason:
        probability.no_signal_reason = "표본 신뢰도, 신호 최신성, 데이터 품질이 기준치에 미달했습니다."

    action_plan = _action_plan_profile(
        timeframe,
        best_pattern,
        probability.p_up,
        probability.p_down,
        probability.entry_score,
        probability.completion_proximity,
        probability.recency_score,
        profile["data_quality"],
        probability.reward_risk_ratio,
        probability.headroom_score,
        probability.historical_edge_score,
        trend_profile["trend_alignment_score"],
        intraday_profile["intraday_session_score"],
        best_target_hit_at,
        best_invalidated_at,
        profile["fetch_status"],
    )
    decision_support = _decision_support_profile(
        timeframe,
        best_pattern,
        action_plan,
        probability.p_up,
        probability.p_down,
        probability.confidence,
        profile["data_quality"],
        probability.reward_risk_ratio,
        probability.headroom_score,
        probability.target_distance_pct,
        probability.stop_distance_pct,
        probability.recency_score,
        probability.sample_reliability,
        trend_profile["trend_alignment_score"],
        wyckoff_profile["wyckoff_phase"],
        intraday_profile["intraday_session_score"],
        profile["fetch_status"],
        best_target_hit_at,
        best_invalidated_at,
        bars_since_signal,
    )
    readiness = _trade_readiness_profile(
        timeframe=timeframe,
        pattern=best_pattern,
        action_plan=action_plan,
        p_up=probability.p_up,
        p_down=probability.p_down,
        entry_score=probability.entry_score,
        confidence=probability.confidence,
        completion_proximity=probability.completion_proximity,
        recency_score=probability.recency_score,
        data_quality=profile["data_quality"],
        reward_risk_ratio=probability.reward_risk_ratio,
        headroom_score=probability.headroom_score,
        sample_reliability=probability.sample_reliability,
        historical_edge_score=probability.historical_edge_score,
        trend_alignment_score=trend_profile["trend_alignment_score"],
        intraday_session_score=intraday_profile["intraday_session_score"],
        target_hit_at=best_target_hit_at,
        invalidated_at=best_invalidated_at,
        bars_since_signal=bars_since_signal,
    )

    return AnalysisResult(
        symbol=symbol,
        timeframe=timeframe,
        timeframe_label=timeframe_label(timeframe),
        p_up=probability.p_up,
        p_down=probability.p_down,
        textbook_similarity=probability.textbook_similarity,
        pattern_confirmation_score=probability.pattern_confirmation_score,
        confidence=probability.confidence,
        entry_score=probability.entry_score,
        completion_proximity=probability.completion_proximity,
        recency_score=probability.recency_score,
        reward_risk_ratio=probability.reward_risk_ratio,
        headroom_score=probability.headroom_score,
        target_distance_pct=probability.target_distance_pct,
        stop_distance_pct=probability.stop_distance_pct,
        avg_mfe_pct=probability.avg_mfe_pct,
        avg_mae_pct=probability.avg_mae_pct,
        avg_bars_to_outcome=probability.avg_bars_to_outcome,
        historical_edge_score=probability.historical_edge_score,
        trend_alignment_score=trend_profile["trend_alignment_score"],
        trend_direction=trend_profile["trend_direction"],
        trend_warning=trend_profile["trend_warning"],
        wyckoff_phase=wyckoff_profile["wyckoff_phase"],
        wyckoff_score=wyckoff_profile["wyckoff_score"],
        wyckoff_note=wyckoff_profile["wyckoff_note"],
        intraday_session_phase=intraday_profile["intraday_session_phase"],
        intraday_session_score=intraday_profile["intraday_session_score"],
        intraday_session_note=intraday_profile["intraday_session_note"],
        action_plan=action_plan["action_plan"],
        action_plan_label=action_plan["action_plan_label"],
        action_plan_summary=action_plan["action_plan_summary"],
        action_priority_score=action_plan["action_priority_score"],
        risk_flags=decision_support["risk_flags"],
        confirmation_checklist=decision_support["confirmation_checklist"],
        next_trigger=decision_support["next_trigger"],
        trade_readiness_score=readiness["trade_readiness_score"],
        trade_readiness_label=readiness["trade_readiness_label"],
        trade_readiness_summary=readiness["trade_readiness_summary"],
        score_factors=readiness["score_factors"],
        no_signal_flag=probability.no_signal_flag,
        no_signal_reason=probability.no_signal_reason,
        reason_summary=probability.reason_summary,
        sample_size=probability.sample_size,
        empirical_win_rate=probability.empirical_win_rate,
        sample_reliability=probability.sample_reliability,
        patterns=pattern_infos,
        projection_label=projection_label,
        projection_summary=projection_summary,
        projected_path=projected_path,
        is_provisional=best_pattern.is_provisional,
        updated_at=datetime.utcnow().isoformat(),
        data_source=profile["data_source"],
        data_quality=profile["data_quality"],
        source_note=profile["source_note"],
        fetch_status=profile["fetch_status"],
        fetch_status_label=profile["fetch_status_label"],
        fetch_message=profile["fetch_message"],
        liquidity_score=round(liquidity, 3),
        avg_turnover_billion=round(turnover_billion, 2),
        bars_since_signal=bars_since_signal,
        stats_timeframe=stats_timeframe,
        available_bars=profile["available_bars"],
    )
