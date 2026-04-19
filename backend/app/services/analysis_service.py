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
    "live_augmented_by_store": "실시간 + 저장 데이터 보강",
    "stored_fallback": "저장 분봉 대체",
    "stored_empty": "저장 분봉 없음",
    "intraday_rate_limited": "분봉 요청 제한",
    "intraday_unavailable": "분봉 데이터를 지원하지 않음",
    "intraday_empty": "분봉 데이터 없음",
    "yahoo_symbol_missing": "공개 데이터 심볼 없음",
    "yahoo_rate_limited": "공개 데이터 요청 제한",
    "yahoo_empty": "공개 데이터 없음",
    "kis_not_configured": "KIS 설정 없음",
    "kis_error": "KIS 호출 실패",
    "kis_empty": "KIS 데이터 없음",
    "daily_ok": "일봉 수집 성공",
    "daily_empty": "일봉 데이터 없음",
    "daily_error": "일봉 수집 실패",
    "unknown": "상태 정보 없음",
}


_FETCH_STATUS_LABELS.update(
    {
        "stored_recent": "최근 저장 분봉 사용",
        "kis_cooldown": "KIS 쿨다운 중",
        "scanner_store_only": "스캐너 저장 데이터 전용",
        "scanner_public_only": "스캐너 공개 데이터 전용",
        "scanner_public_augmented": "스캐너 공개 데이터 보강",
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
            "trend_warning": "?怨뺣뾼?????堉???熬곣뫗???????? ?熬곣뫗異??寃몃쳳???? ???용????덈펲.",
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
            warning = "??⑤챷留??怨뺣뾼??泥? ?熬곣뫗異??熬곣뫗?????⑤챶諭??筌먲퐣議?? ?熬곣뫀鍮???怨뺣뾼???怨뺣뾼鴉딅슜????????逾??筌먦끉逾????繞벿살탳???紐껊퉵??"
        else:
            score = 0.24
            warning = "?熬곣뫗???????? 繞벿살탪????濡?뎅 ?怨뺣뾼?????筌??濡ル츎 ?꾩룇瑗띈린????뚮벣??????덉넮 ?筌먲퐣??????곌랜????⑤챷紐드슖???끚딃뜮???紐껊퉵??"
    elif bearish:
        if trend_direction == "down":
            score = 0.92 if last_close < fast_now else 0.82
            warning = ""
        elif trend_direction == "sideways":
            score = 0.58
            warning = "??⑤챷留??怨뺣뾼??泥? ?熬곣뫗異??熬곣뫗?????濡?뎅 ?筌먲퐣議?? ?熬곣뫀鍮????袁㏉돮 ???덉넮 ?띠럾???쒑땻????節띾쐾 ??끚딃뜮???紐껊퉵??"
        else:
            score = 0.24
            warning = "?熬곣뫗???????? 繞벿살탪????⑤챶諭??怨뺣뾼?????筌??濡ル츎 ??濡?뎅????뚮벣?????λ닔???? ???낅츎 ?筌뤾쑴逾???ル열????덈펲."
    else:
        score = 0.5
        warning = "繞벿살탮????????? ??⑤챷留??怨뺣뾼??? ??節띾쐾 ??怨댄맍??怨룻뒍 ????띠럾? ??ｋ걠壤???덈펲."

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
            "wyckoff_note": "????怨밸쭨????節띉????堉???熬곣뫗???????? ?熬곣뫗異??寃몃쳳???? ???용????덈펲.",
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
    note = "????怨밸쭨???リ옇????怨쀬Ŧ???熬곣뫗異???類ㅼ＋????節띉??筌먦끉???熬곣뫗踰?繞벿살탮????뚮뜆????띠럾?濚밸Ŋ鍮????덈펲."

    if last_close > ma20_now > ma60_now and slope > 0.02 and range_pos > 0.62:
        phase = "markup"
        score = 0.88 if contraction > 0.15 else 0.78
        note = "繞벿살탪????⑤챶諭??怨뺣뾼??泥? ??????겶????곗꽑 ????怨밸쭨???リ옇?? ??⑤챶諭?嶺뚯쉳?듸쭛???뚮뜆???怨쀬Ŧ ??怨댄맍??濡ル츎 ?筌뤾쑴逾?嶺뚮씮?????덈펲."
    elif last_close < ma20_now < ma60_now and slope < -0.02 and range_pos < 0.36:
        phase = "markdown"
        score = 0.88 if contraction < 0.1 else 0.78
        note = "繞벿살탪????濡?뎅 ?怨뺣뾼??泥? ??怨룹꽑嶺뚯솘?????뚮뜆??????????怨밸쭨???リ옇?? ??濡?뎅 嶺뚯쉳?듸쭛???뚮뜆???怨쀬Ŧ ?곌랜????筌뤾쑴逾????깆쓧??紐껊퉵??"
    elif range_pos < 0.46 and abs(slope) < 0.04 and contraction > 0.18 and volume_ratio < 0.95:
        phase = "accumulation"
        score = 0.82 if bullish else 0.68
        note = "??濡ル펺??????곌떠????뉗뎽 ??瑜귣??濾곌쑨?????띠룆흮??붿쾸? ??節띾쐾 ?곌랜?삭굢?嶺뚮씞?됧퐲?嶺뚮씭횧?????裕???????띠럾???쒑땻????琉용펿???????곕????덈펲."
    elif range_pos > 0.58 and abs(slope) < 0.04 and volume_ratio > 1.05:
        phase = "distribution"
        score = 0.82 if bearish else 0.68
        note = "??⑤８堉?????濾곌쑨????源녿턄 ???겶??怨뺣뾼??泥? ??됀????釉뚯뫒亦????裕?????볦낯???뚮뜆????띠럾???쒑땻????節띾쐾 ??끚딃뜮???紐껊퉵??"
    elif last_close > ma60_now and contraction > 0.22 and volume_ratio < 0.92:
        phase = "accumulation"
        score = 0.72 if bullish else 0.58
        note = "??⑤챶諭??怨뺣뾼???熬곣뫖??????곕뻣 ????袁⑤콦???????????繹먭퍒遊???곌랜?????덈펲."
    elif last_close < ma60_now and contraction > 0.18 and volume_ratio > 1.0:
        phase = "distribution"
        score = 0.72 if bearish else 0.58
        note = "????돪 ?怨뺣뾼?????고뱺???꾩룇瑗띈린?????먪춯?뼿?띠럾? ??????釉뚯뫊揶????裕?????볦낯??繹먭퍒遊???롪퍔????怨룻뒍 ??紐껊퉵??"

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
            "intraday_session_note": "??쒎ㅇ???蹂?뜟?? ???????熬곥굥由????熬곣뫖裕???딆뜴泥? ?遊붋?브퀗?꿴뜮????덈펲.",
        }

    last_ts = timestamps.iloc[-1]
    hhmm = last_ts.hour * 100 + last_ts.minute
    close = pd.to_numeric(df["close"], errors="coerce").dropna()
    volume = pd.to_numeric(df["volume"], errors="coerce").dropna()
    if len(close) < 6:
        return {
            "intraday_session_phase": "neutral",
            "intraday_session_score": 0.5,
            "intraday_session_note": "??쒎ㅇ?????????袁ⓥ뵛??嶺뚣끉裕???釉뚯뫊????? ?熬곣뫗異??遊붋?브퀗?꿴뜮????덈펲.",
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
    note = "?熬곣뫗????蹂?뜟?? ??쒖굡??? 繞벿살탮????띠럾?濚밸Ŋ鍮????덈펲."

    if phase == "open_drive":
        if bullish:
            if momentum > 0.008 and volume_ratio > 1.15:
                score = 0.84
                note = "???貫?꾥????곷땵???띠룆踰ㅹ뇡?移??釉먮듋????뚮뜆????????⑤챶諭????????筌먦끉逾???裕???⑥쥙源??⑤챷逾???蹂?뜟?????낅퉵??"
            elif momentum < -0.004:
                score = 0.32
                note = "???貫?꾥뚭였寃????꾩럾??洹먮맧裕???????????怨뺣뼺??嶺뚮씞??遺삵돦????????덉넮 ?띠럾???쒑땻?????롪퍔????怨룻뒍 ??紐껊퉵??"
            else:
                score = 0.58
                note = "???貫?꾥??꾩렮維싧젆?繹? ?곌랜??醫묒??嶺???戮㏐국??怨쀬Ŧ ?筌먦끉????얄뵛???熬곣뫗異????藥???덈펲."
        elif bearish:
            if momentum < -0.008 and volume_ratio > 1.15:
                score = 0.84
                note = "???貫?꾥?嶺뚮씞?뉒뙴??筌먲퐣????띠룆踰ㅹ뜮???濡?뎅????????筌먦끉逾???裕???⑥쥙源??⑤챷逾???蹂?뜟?????낅퉵??"
            elif momentum > 0.004:
                score = 0.32
                note = "???貫?꾥뚭였寃????꾩룇瑗띈린???띠룆踰ㅹ뜮???濡?뎅 嶺뚯솘?????類?룎?洹먮봿沅???꾩룆?餓?亦껋꼷?숂뵳?????鈺???鍮??"
            else:
                score = 0.58
                note = "???貫?꾥??꾩렮維싧젆?繹? ?곌랜??醫묒??嶺??怨뺣뼺? ?筌먦끉逾?????熬곣뫗???紐껊퉵??"
    elif phase == "midday":
        if abs(momentum) < 0.003 or volume_ratio < 0.9:
            score = 0.40
            note = "???堉???獄????????類???뚮뜆????띠럾?濚밸Ŧ????釉뚯뫊???????? ??ル쪇源???λ닔??귦돦????????嶺뚯옕????????깆쓧??紐껊퉵??"
        else:
            score = 0.56
            note = "???堉???洹씲?μ쪚????嶺뚯쉳???????덈츎 ?筌뤾쑴逾좂춯?뼿嶺?嶺뚮씭?껇???????筌뤾쑴逾???繞벿살탳???紐껊퉵??"
    elif phase == "closing_drive":
        if bullish:
            if momentum > 0.006:
                score = 0.88 if volume_ratio > 1.0 else 0.78
                note = "嶺뚮씭?껇?????????곕턄 ?釉먮듋?????????????⑤챶諭????????筌먦끉逾???裕??띠럾?????ル열? ??蹂?뜟?? 繞???濡る룎???낅퉵??"
            elif momentum < -0.004:
                score = 0.30
                note = "嶺뚮씭?껇?????瑜곷턄 ?怨쀫폏?醫묒춺??獄??????????ル뱴?熬곣뫀裕????????됱꼻彛よ눧癒?퉵??"
            else:
                score = 0.60
                note = "嶺뚮씭?껇????????? ???亦???嶺??筌먦끇六???낅슣?????????듬뤀嶺뚯솘????熬곣뫀六???덈펲."
        elif bearish:
            if momentum < -0.006:
                score = 0.88 if volume_ratio > 1.0 else 0.78
                note = "嶺뚮씭?껇?????濡れ빼 ??????곕턄 ?釉먮듋?????????????濡?뎅????????筌먦끉逾???裕???⑥쥙源??⑤챷肉???덈펲."
            elif momentum > 0.004:
                score = 0.30
                note = "嶺뚮씭?껇?????濡?퍩???逾??띠룆踰ㅹ뜮???濡?뎅??????????λ닔????얄뵛 ???鈺???鍮??"
            else:
                score = 0.60
                note = "嶺뚮씭?껇????????? ???亦???嶺??띠룆踰ㅹ뇡??筌먦끉逾???뚮뜆?®뭐癒?뒩????熬곣뫀六???덈펲."
    elif phase == "regular_session":
        if bullish:
            score = 0.64 if momentum > 0.004 else 0.46
            note = "??쒎ㅇ???怨쀫틮 ??뚮뜆????????꾩렮維싧젆?繹? 嶺뚣볝늾???濡モ뵹 濾곌쑨???????쀫틮 ???????節띾쐾 ?곌랜????筌뤾쑴逾???ル열????덈펲."
        elif bearish:
            score = 0.64 if momentum < -0.004 else 0.46
            note = "??쒎ㅇ???怨쀫틮 ??뚮뜆?????????濡?뎅 嶺뚯솘???????곌랜?????袁㏉돮 ??? ???????節띾쐾 ??끚딃뜮???紐껊퉵??"
    else:
        score = 0.44
        note = "?筌?????꾩룆?썼눧???戮곗젍?????嶺뚮씭??嶺??釉뚯뫊?????蹂?뜟?? ??怨댄맍?? ?곌랜????⑤챷紐드슖??곌랜????筌뤾쑴逾?嶺뚮씮?????덈펲."

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


def _entry_window_profile(
    *,
    timeframe: str,
    pattern: PatternResult | None,
    current_close: float,
    reward_risk_ratio: float,
    headroom_score: float,
    target_distance_pct: float,
    stop_distance_pct: float,
    completion_proximity: float,
    target_hit_at: str | None,
    invalidated_at: str | None,
) -> dict[str, Any]:
    label = timeframe_label(timeframe)
    if pattern is None or current_close <= 0:
        return {
            "entry_window_score": 0.22,
            "entry_window_label": "재확인 필요",
            "entry_window_summary": f"{label} 기준 아직 유효한 패턴이 없어 진입 구간을 적극적으로 평가하기 어렵습니다.",
        }

    if pattern.state in {"played_out", "invalidated"} or target_hit_at or invalidated_at:
        reason = "이미 목표 달성 또는 무효화가 확인되어 지금은 신규 진입보다 패턴 종료로 보는 편이 안전합니다."
        return {
            "entry_window_score": 0.08,
            "entry_window_label": "관망",
            "entry_window_summary": f"{label} 기준 {reason}",
        }

    neckline = pattern.neckline
    invalidation = pattern.invalidation_level
    target = pattern.target_level
    bullish = _is_bullish(pattern.pattern_type)
    bearish = _is_bearish(pattern.pattern_type)
    if neckline is None or invalidation is None or target is None or (not bullish and not bearish):
        return {
            "entry_window_score": 0.28,
            "entry_window_label": "재확인 필요",
            "entry_window_summary": f"{label} 기준 핵심 가격대가 충분히 잡히지 않아 보수적으로 해석하는 편이 좋습니다.",
        }

    trigger_span = max(abs(neckline - invalidation), max(current_close * 0.012, 1.0))
    if bullish:
        distance_to_trigger_pct = max(0.0, (neckline - current_close) / max(neckline, 1.0))
        breakout_extension_pct = max(0.0, (current_close - neckline) / max(neckline, 1.0))
        risk_buffer = (current_close - invalidation) / trigger_span
    else:
        distance_to_trigger_pct = max(0.0, (current_close - neckline) / max(abs(neckline), 1.0))
        breakout_extension_pct = max(0.0, (neckline - current_close) / max(abs(neckline), 1.0))
        risk_buffer = (invalidation - current_close) / trigger_span

    score = (
        0.30 * min(1.0, max(0.0, reward_risk_ratio / 2.2))
        + 0.22 * headroom_score
        + 0.20 * completion_proximity
        + 0.16 * min(1.0, max(0.0, risk_buffer))
        + 0.12 * (1.0 - min(1.0, breakout_extension_pct / 0.06))
    )

    if target_distance_pct <= 0.018 or headroom_score < 0.16:
        score = min(score, 0.18)
        return {
            "entry_window_score": round(max(0.0, min(1.0, score)), 3),
            "entry_window_label": "목표 근접",
            "entry_window_summary": f"{label} 기준 목표가가 가까워 추가 기대수익이 작아졌습니다. 신규 진입보다 익절·관망에 가깝습니다.",
        }

    if stop_distance_pct <= 0.004:
        score = min(score, 0.24)
        return {
            "entry_window_score": round(max(0.0, min(1.0, score)), 3),
            "entry_window_label": "관망",
            "entry_window_summary": f"{label} 기준 손절 여유가 너무 좁아 실전 체결 잡음에 취약합니다. 진입보다는 기준 재정비가 먼저입니다.",
        }

    if pattern.state == "confirmed":
        if breakout_extension_pct <= (0.012 if is_intraday_timeframe(timeframe) else 0.025) and reward_risk_ratio >= 1.15:
            score = max(score, 0.74)
            entry_label = "초기 돌파"
            summary = "돌파 직후 구간으로 해석할 수 있어 추격 부담이 아직 크지 않습니다. 다만 무효화 기준과 거래대금은 함께 확인해야 합니다."
        elif breakout_extension_pct <= (0.024 if is_intraday_timeframe(timeframe) else 0.045) and reward_risk_ratio >= 1.0:
            score = max(min(score, 0.64), 0.52)
            entry_label = "확장 추격"
            summary = "이미 일부 확장이 진행되어 초기 진입보다 불리합니다. 재돌파 확인이나 눌림 확인 후 접근하는 편이 낫습니다."
        else:
            score = min(score, 0.34)
            entry_label = "관망"
            summary = "확인 완료 이후 가격이 너무 앞서가 있어 지금 구간은 추격 위험이 큽니다."
    elif pattern.state == "armed":
        if distance_to_trigger_pct <= (0.008 if is_intraday_timeframe(timeframe) else 0.015) and reward_risk_ratio >= 1.1:
            score = max(score, 0.72)
            entry_label = "트리거 임박"
            summary = "목선 또는 트리거 가격대 근처로, 확인만 붙으면 실전 진입 후보가 될 수 있습니다."
        elif distance_to_trigger_pct <= (0.02 if is_intraday_timeframe(timeframe) else 0.035):
            score = max(min(score, 0.58), 0.46)
            entry_label = "트리거 대기"
            summary = "아직 확인 직전 단계이므로 성급한 진입보다 돌파 확인 여부를 보는 편이 좋습니다."
        else:
            score = min(score, 0.40)
            entry_label = "관망"
            summary = "활성 직전이지만 아직 트리거까지 거리가 남아 있어 기다리는 편이 낫습니다."
    else:
        if completion_proximity >= 0.66 and distance_to_trigger_pct <= (0.025 if is_intraday_timeframe(timeframe) else 0.04):
            score = max(min(score, 0.54), 0.42)
            entry_label = "기준선 접근"
            summary = "형성 중 패턴이지만 핵심 가격대에 가까워지고 있어 관찰 가치가 있습니다."
        else:
            score = min(score, 0.32)
            entry_label = "패턴 형성"
            summary = "아직 패턴이 진행 중이라 실전 진입보다 구조 완성을 더 기다리는 편이 좋습니다."

    return {
        "entry_window_score": round(max(0.0, min(1.0, score)), 3),
        "entry_window_label": entry_label,
        "entry_window_summary": f"{label} 기준 {summary}",
    }

def _freshness_profile(
    *,
    timeframe: str,
    pattern: PatternResult | None,
    current_close: float,
    completion_proximity: float,
    recency_score: float,
    headroom_score: float,
    target_distance_pct: float,
    stop_distance_pct: float,
    bars_since_signal: int | None,
    target_hit_at: str | None,
    invalidated_at: str | None,
) -> dict[str, Any]:
    label = timeframe_label(timeframe)
    if pattern is None or current_close <= 0:
        return {
            "freshness_score": 0.18,
            "freshness_label": "재확인 필요",
            "freshness_summary": f"{label} 기준 아직 평가할 만한 활성 패턴이 부족합니다.",
        }

    target = pattern.target_level
    neckline = pattern.neckline
    anchor_level = neckline if neckline is not None else current_close
    target_span = max(abs((target or current_close) - anchor_level), max(current_close * 0.015, 1.0))
    cooling_to_trigger_score = 0.0
    if neckline is not None:
        cooling_to_trigger_score = max(0.0, 1.0 - min(1.0, abs(current_close - neckline) / target_span))

    freshness = (
        0.34 * recency_score
        + 0.24 * completion_proximity
        + 0.22 * headroom_score
        + 0.12 * min(1.0, target_distance_pct / 0.08)
        + 0.08 * min(1.0, stop_distance_pct / 0.03)
    )

    if invalidated_at or pattern.state == "invalidated":
        return {
            "freshness_score": 0.05,
            "freshness_label": "무효 만료",
            "freshness_summary": f"{label} 기준 무효화가 확인된 패턴이라 현재 시점의 신규 후보로 보기 어렵습니다.",
        }

    if target_hit_at or pattern.state == "played_out":
        retrace_ready = (
            cooling_to_trigger_score >= 0.58
            and headroom_score >= 0.34
            and target_distance_pct >= 0.04
            and stop_distance_pct >= 0.01
        )
        if retrace_ready:
            score = round(max(0.22, min(0.38, freshness * 0.62)), 3)
            return {
                "freshness_score": score,
                "freshness_label": "재기초 관찰",
                "freshness_summary": f"{label} 기준 과거 목표 달성 이후 다시 기준선 근처로 식어 들어왔습니다. 재형성 여부를 관찰하는 단계입니다.",
            }
        return {
            "freshness_score": 0.08,
            "freshness_label": "종료 패턴",
            "freshness_summary": f"{label} 기준 이미 목표가를 소화한 패턴이라 지금은 신선한 신규 셋업으로 보기 어렵습니다.",
        }

    if bars_since_signal is not None:
        stale_cutoff = 48 if is_intraday_timeframe(timeframe) else 16
        if bars_since_signal >= stale_cutoff and recency_score <= 0.3:
            score = round(max(0.12, min(0.28, freshness * 0.55)), 3)
            return {
                "freshness_score": score,
                "freshness_label": "오래됨",
                "freshness_summary": f"{label} 기준 신호가 나온 지 시간이 꽤 지나 현재 시점의 선명도는 떨어진 상태입니다.",
            }

    if pattern.state == "confirmed" and target_distance_pct >= 0.03 and headroom_score >= 0.3:
        score = round(max(0.68, min(0.92, freshness)), 3)
        return {
            "freshness_score": score,
            "freshness_label": "신선",
            "freshness_summary": f"{label} 기준 확인 완료 이후에도 목표까지 여유가 남아 있어 아직 살아 있는 셋업으로 볼 수 있습니다.",
        }

    if pattern.state in {"confirmed", "armed"}:
        score = round(max(0.46, min(0.74, freshness)), 3)
        return {
            "freshness_score": score,
            "freshness_label": "진행중",
            "freshness_summary": f"{label} 기준 패턴이 여전히 진행 중이지만 추가 확인이 더 붙으면 해석 품질이 좋아질 수 있습니다.",
        }

    score = round(max(0.24, min(0.5, freshness * 0.88)), 3)
    return {
        "freshness_score": score,
        "freshness_label": "재확인 필요",
        "freshness_summary": f"{label} 기준 아직 형성 단계라 신선도는 남아 있지만 확인 전 해석 오차도 함께 큽니다.",
    }

def _score_clamp(value: float) -> float:
    return round(max(0.0, min(1.0, value)), 3)


def _reentry_window_size(timeframe: str) -> int:
    if timeframe == "1mo":
        return 6
    if timeframe == "1wk":
        return 8
    if timeframe == "1d":
        return 10
    if timeframe == "60m":
        return 12
    if timeframe in {"30m", "15m"}:
        return 14
    return 18


def _reentry_factor_breakdown(
    *,
    df: pd.DataFrame,
    timeframe: str,
    pattern: PatternResult,
) -> dict[str, Any]:
    if df.empty:
        return {
            "compression_score": 0.5,
            "volume_recovery_score": 0.5,
            "trigger_hold_score": 0.5,
            "wick_absorption_score": 0.5,
            "failure_burden_score": 0.5,
            "detail_score": 0.5,
            "reentry_factors": [],
        }

    bullish = _is_bullish(pattern.pattern_type) or not _is_bearish(pattern.pattern_type)
    neckline = pattern.neckline
    window = min(len(df), _reentry_window_size(timeframe))
    recent = df.tail(window).copy()
    prior = df.iloc[max(0, len(df) - window * 2): max(0, len(df) - window)].copy()

    recent_high = pd.to_numeric(recent["high"], errors="coerce")
    recent_low = pd.to_numeric(recent["low"], errors="coerce")
    recent_open = pd.to_numeric(recent["open"], errors="coerce")
    recent_close = pd.to_numeric(recent["close"], errors="coerce")
    recent_volume = pd.to_numeric(recent["volume"], errors="coerce").fillna(0.0)

    range_floor = max(float(recent_close.iloc[-1]) * 0.002, 1.0)
    recent_range = float(recent_high.max() - recent_low.min()) if not recent.empty else range_floor
    if prior.empty:
        prior_range = recent_range
        prior_volume = recent_volume
    else:
        prior_high = pd.to_numeric(prior["high"], errors="coerce")
        prior_low = pd.to_numeric(prior["low"], errors="coerce")
        prior_range = float(prior_high.max() - prior_low.min())
        prior_volume = pd.to_numeric(prior["volume"], errors="coerce").fillna(0.0)

    range_ratio = recent_range / max(prior_range, range_floor)
    compression_score = _score_clamp((1.25 - range_ratio) / 0.85)

    event_window = min(3, len(recent_volume))
    event_volume = float(recent_volume.tail(event_window).mean()) if event_window else 0.0
    base_volume_series = recent_volume.head(max(1, len(recent_volume) - event_window))
    if base_volume_series.empty:
        base_volume_series = prior_volume if not prior_volume.empty else recent_volume
    base_volume = float(base_volume_series.mean()) if not base_volume_series.empty else 1.0
    volume_ratio = event_volume / max(base_volume, 1.0)
    volume_recovery_score = _score_clamp((volume_ratio - 0.72) / 0.88)

    wick_scores: list[float] = []
    for _, row in recent.tail(min(len(recent), 5)).iterrows():
        open_price = float(row["open"])
        high_price = float(row["high"])
        low_price = float(row["low"])
        close_price = float(row["close"])
        bar_range = max(high_price - low_price, range_floor)
        upper_wick = max(high_price - max(open_price, close_price), 0.0) / bar_range
        lower_wick = max(min(open_price, close_price) - low_price, 0.0) / bar_range
        close_location = (close_price - low_price) / bar_range if bullish else (high_price - close_price) / bar_range
        wick_quality = (1.0 - upper_wick) if bullish else (1.0 - lower_wick)
        wick_scores.append(0.55 * wick_quality + 0.45 * close_location)
    wick_absorption_score = _score_clamp(sum(wick_scores) / max(len(wick_scores), 1))

    if neckline is None:
        trigger_hold_score = 0.5
        failure_burden_score = 0.5
    else:
        closes = recent_close
        lows = recent_low
        highs = recent_high
        if bullish:
            side_holds = float((closes >= neckline * 0.995).mean())
            defense = float(((lows <= neckline * 1.01) & (closes >= neckline * 0.995)).mean())
        else:
            side_holds = float((closes <= neckline * 1.005).mean())
            defense = float(((highs >= neckline * 0.99) & (closes <= neckline * 1.005)).mean())
        trigger_hold_score = _score_clamp(0.62 * side_holds + 0.38 * defense)

        fail_count = 0
        for _, row in recent.iterrows():
            high_price = float(row["high"])
            low_price = float(row["low"])
            close_price = float(row["close"])
            if bullish:
                if high_price >= neckline * 1.002 and close_price < neckline:
                    fail_count += 1
            else:
                if low_price <= neckline * 0.998 and close_price > neckline:
                    fail_count += 1
        failure_burden_score = _score_clamp(1.0 - fail_count / 3.0)

    reentry_factors = [
        {
            "label": "박스 수축도",
            "score": compression_score,
            "weight": 0.20,
            "note": "최근 변동폭이 직전 구간보다 줄수록 재축적 구조로 해석합니다.",
        },
        {
            "label": "거래량 복원",
            "score": volume_recovery_score,
            "weight": 0.22,
            "note": "최근 2~3개 바에서 거래량이 다시 붙는지 확인합니다.",
        },
        {
            "label": "기준선 유지력",
            "score": trigger_hold_score,
            "weight": 0.24,
            "note": "목선 또는 기준선 위/아래를 얼마나 안정적으로 지키는지 반영합니다.",
        },
        {
            "label": "꼬리 흡수력",
            "score": wick_absorption_score,
            "weight": 0.18,
            "note": "윗꼬리 또는 아랫꼬리를 얼마나 잘 소화하는지 봅니다.",
        },
        {
            "label": "실패 부담 관리",
            "score": failure_burden_score,
            "weight": 0.16,
            "note": "최근 재돌파 실패 횟수가 적을수록 높은 점수를 줍니다.",
        },
    ]
    detail_score = _score_clamp(sum(float(item["score"]) * float(item["weight"]) for item in reentry_factors))
    return {
        "compression_score": compression_score,
        "volume_recovery_score": volume_recovery_score,
        "trigger_hold_score": trigger_hold_score,
        "wick_absorption_score": wick_absorption_score,
        "failure_burden_score": failure_burden_score,
        "detail_score": detail_score,
        "reentry_factors": reentry_factors,
    }


def _reentry_profile(
    *,
    df: pd.DataFrame,
    timeframe: str,
    pattern: PatternResult | None,
    current_close: float,
    completion_proximity: float,
    recency_score: float,
    headroom_score: float,
    target_distance_pct: float,
    stop_distance_pct: float,
    entry_window_score: float,
    target_hit_at: str | None,
    invalidated_at: str | None,
) -> dict[str, Any]:
    label = timeframe_label(timeframe)
    if pattern is None or current_close <= 0:
        return {
            "reentry_score": 0.0,
            "reentry_label": "재확인 필요",
            "reentry_summary": f"{label} 기준 아직 재진입 구조를 평가할 만한 패턴 정보가 부족합니다.",
            "reentry_case": "none",
            "reentry_case_label": "구조 없음",
            "reentry_trigger": "활성 패턴이 충분히 쌓이면 재진입 구조를 계산합니다.",
            "reentry_factors": [],
        }

    factor_profile = _reentry_factor_breakdown(df=df, timeframe=timeframe, pattern=pattern)

    neckline = pattern.neckline
    invalidation = pattern.invalidation_level
    target = pattern.target_level
    anchor_level = neckline if neckline is not None else current_close
    span = max(abs((target or current_close) - anchor_level), max(current_close * 0.015, 1.0))

    distance_to_trigger = 0.0
    if neckline is not None:
        distance_to_trigger = max(0.0, 1.0 - min(1.0, abs(current_close - neckline) / span))

    above_neckline = neckline is None or current_close >= neckline
    inside_reset_box = neckline is not None and abs(current_close - neckline) <= span * 0.22
    shallow_pullback = neckline is not None and current_close > neckline and (current_close - neckline) <= span * 0.38
    trigger_price = neckline if neckline is not None else current_close

    recovery_from_invalidation = 0.0
    if invalidation is not None:
        if target and abs(target - invalidation) > 1e-9:
            recovery_from_invalidation = max(
                0.0,
                min(1.0, (current_close - invalidation) / abs(target - invalidation)),
            )
        else:
            recovery_from_invalidation = 1.0 if current_close > invalidation else 0.0

    rebuild_score = max(
        0.0,
        min(
            1.0,
            0.24 * distance_to_trigger
            + 0.14 * headroom_score
            + 0.12 * recency_score
            + 0.10 * completion_proximity
            + 0.08 * min(1.0, target_distance_pct / 0.08)
            + 0.08 * min(1.0, stop_distance_pct / 0.03)
            + 0.24 * factor_profile["detail_score"],
        ),
    )

    if invalidated_at or pattern.state == "invalidated":
        repaired = (
            recovery_from_invalidation >= 0.45
            and distance_to_trigger >= 0.46
            and headroom_score >= 0.24
            and recency_score >= 0.22
        )
        if repaired:
            score = round(max(0.28, min(0.54, 0.54 * rebuild_score + 0.22 * recovery_from_invalidation + 0.24 * factor_profile["detail_score"])), 3)
            return {
                "reentry_score": score,
                "reentry_label": "실패 후 복구 관찰",
                "reentry_summary": f"{label} 기준 한 차례 무효화된 뒤 구조를 다시 회복하는 중입니다. 즉시 진입보다 복구 지속 여부를 먼저 확인하는 편이 좋습니다.",
                "reentry_case": "failed_breakout_recovery",
                "reentry_case_label": "실패 돌파 복구형",
                "reentry_trigger": f"무효화 구간 회복 유지와 {trigger_price:,.0f} 재돌파가 함께 확인되는지 보세요.",
                "reentry_factors": factor_profile["reentry_factors"],
            }
        return {
            "reentry_score": 0.06,
            "reentry_label": "재진입 비선호",
            "reentry_summary": f"{label} 기준 무효화 이후 구조 복구가 충분하지 않아 재진입 후보로 보기 어렵습니다.",
            "reentry_case": "avoid",
            "reentry_case_label": "재진입 비선호",
            "reentry_trigger": "추가 복구 없이 재진입을 서두르지 않는 편이 좋습니다.",
            "reentry_factors": factor_profile["reentry_factors"],
        }

    if target_hit_at or pattern.state == "played_out":
        reset_ready = (
            distance_to_trigger >= 0.56
            and headroom_score >= 0.34
            and target_distance_pct >= 0.04
            and stop_distance_pct >= 0.01
        )
        if reset_ready and inside_reset_box and factor_profile["compression_score"] >= 0.56 and factor_profile["trigger_hold_score"] >= 0.54:
            score = round(max(0.46, min(0.72, 0.52 * rebuild_score + 0.30 * factor_profile["compression_score"] + 0.18 * factor_profile["trigger_hold_score"])), 3)
            return {
                "reentry_score": score,
                "reentry_label": "재돌파 대기",
                "reentry_summary": f"{label} 기준 과거 목표 소화 후 다시 기준선 근처에서 구조를 재정비하고 있습니다. 재돌파가 붙는지 보는 단계입니다.",
                "reentry_case": "box_reaccumulation",
                "reentry_case_label": "박스 재축적형",
                "reentry_trigger": f"목선 {trigger_price:,.0f} 부근 박스 유지 후 거래대금 동반 재돌파를 기다리세요.",
                "reentry_factors": factor_profile["reentry_factors"],
            }
        if reset_ready and shallow_pullback and above_neckline and entry_window_score >= 0.46 and factor_profile["volume_recovery_score"] >= 0.5:
            score = round(max(0.44, min(0.70, 0.44 * rebuild_score + 0.22 * entry_window_score + 0.20 * factor_profile["volume_recovery_score"] + 0.14 * factor_profile["wick_absorption_score"])), 3)
            return {
                "reentry_score": score,
                "reentry_label": "재돌파 대기",
                "reentry_summary": f"{label} 기준 목표 소화 후 깊지 않은 눌림만 거치며 다시 위쪽으로 힘을 모으는 중입니다. 눌림 후 재가속 여부가 중요합니다.",
                "reentry_case": "pullback_relaunch",
                "reentry_case_label": "눌림 후 재상승형",
                "reentry_trigger": f"목선 위 안착 유지와 최근 고점 재돌파가 함께 나오는지 보세요.",
                "reentry_factors": factor_profile["reentry_factors"],
            }
        if reset_ready:
            score = round(max(0.28, min(0.52, 0.62 * rebuild_score + 0.38 * factor_profile["detail_score"])), 3)
            return {
                "reentry_score": score,
                "reentry_label": "재축적 관찰",
                "reentry_summary": f"{label} 기준 이전 목표 달성 이후 숨 고르기와 재축적이 진행 중입니다. 아직은 추격보다 재형성 확인이 우선입니다.",
                "reentry_case": "range_reset",
                "reentry_case_label": "재축적 준비형",
                "reentry_trigger": f"박스 하단 이탈 없이 {trigger_price:,.0f} 재접근이 이어지는지 확인하세요.",
                "reentry_factors": factor_profile["reentry_factors"],
            }
        return {
            "reentry_score": 0.12,
            "reentry_label": "재진입 비선호",
            "reentry_summary": f"{label} 기준 이미 목표가를 소화했고 재축적도 아직 약해 당장 재진입할 자리는 아닙니다.",
            "reentry_case": "avoid",
            "reentry_case_label": "재진입 비선호",
            "reentry_trigger": "목표 소화 직후라 구조가 다시 쌓일 때까지 기다리는 편이 좋습니다.",
            "reentry_factors": factor_profile["reentry_factors"],
        }

    if pattern.state == "confirmed" and entry_window_score >= 0.64 and headroom_score >= 0.32:
        score = round(max(0.64, min(0.84, 0.46 * entry_window_score + 0.30 * headroom_score + 0.24 * factor_profile["detail_score"])), 3)
        return {
            "reentry_score": score,
            "reentry_label": "신규 셋업 우선",
            "reentry_summary": f"{label} 기준 아직 1차 셋업이 살아 있어 재진입보다 현재 신규 셋업 해석이 더 적절합니다.",
            "reentry_case": "primary_setup",
            "reentry_case_label": "신규 셋업 우선형",
            "reentry_trigger": "재진입보다 현재 1차 셋업의 추세 유지와 손익비를 먼저 보세요.",
            "reentry_factors": factor_profile["reentry_factors"],
        }

    if pattern.state in {"armed", "forming"} and distance_to_trigger >= 0.52 and headroom_score >= 0.24:
        score = round(max(0.44, min(0.68, 0.58 * rebuild_score + 0.18 * factor_profile["volume_recovery_score"] + 0.14 * factor_profile["wick_absorption_score"] + 0.10 * factor_profile["trigger_hold_score"])), 3)
        return {
            "reentry_score": score,
            "reentry_label": "재돌파 대기",
            "reentry_summary": f"{label} 기준 기준선 재접근 이후 재돌파를 시도할 수 있는 구조입니다. 확인 전까지는 관찰 우선 구간입니다.",
            "reentry_case": "pullback_relaunch",
            "reentry_case_label": "눌림 후 재상승형",
            "reentry_trigger": f"기준선 {trigger_price:,.0f} 재확인 뒤 돌파 캔들과 거래량 회복을 같이 확인하세요.",
            "reentry_factors": factor_profile["reentry_factors"],
        }

    score = round(max(0.22, min(0.52, 0.50 * rebuild_score + 0.20 * entry_window_score + 0.30 * factor_profile["detail_score"])), 3)
    return {
        "reentry_score": score,
        "reentry_label": "신규 셋업 우선",
        "reentry_summary": f"{label} 기준 현재는 재진입보다는 기존 셋업의 완성도와 타이밍을 우선 해석하는 편이 좋습니다.",
        "reentry_case": "primary_setup",
        "reentry_case_label": "신규 셋업 우선형",
        "reentry_trigger": "현재 셋업 완성도가 먼저이며 재진입 시나리오는 보조적으로만 보세요.",
        "reentry_factors": factor_profile["reentry_factors"],
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
            note = "KRX ??怨좉껀 ??⑥щ턄??? ?リ옇????怨쀬Ŧ ??????겶????곗꽑 ?????⑤챷紐드슖???ル뱴?熬? ?沃? ?筌뤾쑴肉???덈펲."
        elif source == "fdr_daily":
            quality = 0.90
            note = "FinanceDataReader ??怨좉껀 ??⑥щ턄??? ?곌랜??????裕욃슖???????곕????덈펲."
        else:
            quality = 0.84
            note = "??怨좉껀 ??ｌ뫒????⑥щ턄???嶺???ㅻ??誘?럸?? ?곌랜??????裕????怨댄맍?? ????節띉??곌랜????⑤챷紐드슖??곌랜????筌뤾쑴逾???ル열????덈펲."
    else:
        if source == "kis_intraday":
            quality = 0.94
            note = "KIS ?釉뚯뫊????⑥щ턄??? 嶺뚯쉳?????????곕????덈펲."
        elif source == "hybrid_intraday":
            quality = 0.82
            note = "嶺뚣끉裕???釉뚯뫊??? KIS, ??λ닁????뚮뜆??? ?곌랜??????裕????濡レ꽑 ??????곕????덈펲."
        elif source in {"intraday_store", "yahoo_fallback"}:
            quality = 0.62 if timeframe in {"60m", "30m", "15m"} else 0.45
            note = "?釉뚯뫊??? ??ㅻ??????裕????裕??β돦裕뉛쭚?嶺?흮?????琉돠???????怨좉껀?곌랜????곌랜????⑤챷紐드슖???怨댄맍??怨룻뒍 ??紐껊퉵??"
        else:
            quality = 0.52
            note = "?釉뚯뫊????⑥щ턄??? ?釉띾쐠??熬곥굥??No Signal????貫?좂춯??띠럾???쒑땻???沃섅굥裕???덈펲."

    if fetch_status == "stored_recent":
        quality -= 0.02
        note = "嶺뚣끉裕?????繞③뇡???쒎ㅇ??釉뚯뫊??????곕뻣 ?釉띾쐞??? ????繞벿살탳????덈펲. API ?筌뤾쑵??? 繞벿븐뫒?嶺뚯솘?嶺?嶺뚣끉裕??繹? ??袁⑺뜟 ?곌랜????⑤챷紐드슖???怨댄맍??怨룻뒍 ??紐껊퉵??"
    elif fetch_status == "scanner_store_only":
        quality -= 0.05
        note = "???노뼆?????고뒎 嶺뚮ㅄ維獄?쑜?????縕ワ쭕??釉뚯뫊?釉앹춹???????곕????덈펲. ???곕뻣????쒎ㅇ??곌떠???븐뼔裕??곌랜????⑤챷紐드슖???怨댄맍??怨룻뒍 ??紐껊퉵??"
    elif fetch_status == "scanner_public_only":
        quality -= 0.07
        note = "???노뼆?????고뒎 嶺뚮ㅄ維獄?쑜??KIS ??????ㅻ????釉뚯뫊?????裕????????곕????덈펲."
    elif fetch_status == "scanner_public_augmented":
        quality -= 0.05
        note = "???노뼆?????고뒎 嶺뚮ㅄ維獄???????ㅻ????釉뚯뫊?酉맞??????釉뚯뫊?????節띾쐾 ??????곕????덈펲."
    elif fetch_status == "stored_fallback":
        quality -= 0.08
        note = "???곕뻣???釉뚯뫊????ㅻ???????닷젆????縕ワ쭕??釉뚯뫊??嶺?흮??븍ご???????????곕????덈펲."
    elif fetch_status == "kis_cooldown":
        quality -= 0.10
        note = "KIS ?筌뤾쑵??嶺뚯쉳????臾낅??????⑤객臾???????釉뚯뫊????????ㅻ??????裕??熬곣뫜?믣슖???怨댄맍???겶????곕????덈펲."
    elif fetch_status in {"intraday_rate_limited", "yahoo_rate_limited"}:
        quality -= 0.12
        note = "?釉뚯뫊????ㅻ??誘?럸???븐슙?????ル┰??濾곌쑬梨????? ??⑥щ턄?????裕???怨몄쓧 ??얜Ŧ堉쀧춯??꾩룇瑗????裕???덈펲."
    elif fetch_status in {"intraday_empty", "stored_empty", "intraday_unavailable", "yahoo_empty"}:
        quality -= 0.18
        note = "?熬곣뫗????븐슙??????熬곥굥????깅엮??????????띠럾??繞③뇡??釉뚯뫊??????? ?寃몃쳳???? ???용????덈펲."
    elif fetch_status == "yahoo_symbol_missing":
        quality -= 0.14
        note = "???????リ턁??????밸쐩 嶺뚮씞?뗩뇡???釉띾쐠??筌먐삵돵 ?釉뚯뫊????ㅻ??????袁㏉렩???鍮??"
    elif fetch_status == "kis_not_configured":
        quality -= 0.06
        note = "KIS?띠럾? ???깆젧??? ???욱닡 ??ㅻ??????裕욅춯?얠뒩???뿉??釉뚯뫊?????ｌ뫒亦???겶????곕????덈펲."

    if stored_source:
        note = f"{note} ??嶺????裕? {stored_source}."

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


def _pattern_is_terminal(pattern: PatternResult, target_hit_at: str | None, invalidated_at: str | None) -> bool:
    return pattern.state in {"played_out", "invalidated"} or bool(target_hit_at or invalidated_at)


def _primary_pattern_rank_score(
    item: tuple[PatternResult, float, float, int, str | None, str | None],
) -> float:
    pattern, completion, recency, bars_since_signal, target_hit_at, invalidated_at = item
    score = _pattern_rank_score(pattern, completion, recency)
    if _pattern_is_terminal(pattern, target_hit_at, invalidated_at):
        score -= 0.70
    elif pattern.state == "confirmed":
        score += 0.10
    elif pattern.state == "armed":
        score += 0.12
    elif pattern.state == "forming" and completion >= 0.55:
        score += 0.08

    if bars_since_signal > 0 and recency < 0.35:
        score -= 0.10
    return score


def _pattern_lifecycle_profile(
    pattern: PatternResult,
    completion: float,
    recency: float,
    bars_since_signal: int,
    target_hit_at: str | None,
    invalidated_at: str | None,
) -> dict[str, Any]:
    terminal = _pattern_is_terminal(pattern, target_hit_at, invalidated_at)
    formation_quality = max(
        0.0,
        min(
            1.0,
            0.22 * pattern.textbook_similarity
            + 0.18 * pattern.leg_balance_fit
            + 0.18 * pattern.reversal_energy_fit
            + 0.16 * pattern.breakout_quality_fit
            + 0.14 * pattern.retest_quality_fit
            + 0.12 * pattern.variant_fit,
        ),
    )
    score = 0.34 * formation_quality + 0.28 * completion + 0.24 * recency + 0.14 * pattern.candlestick_confirmation_fit

    if terminal:
        score = min(score, 0.22)
        label = "종료 패턴" if target_hit_at or pattern.state == "played_out" else "무효 만료"
        note = "이미 목표 달성 또는 무효화가 확인된 패턴이라 현재 시점의 활성 셋업으로 보기 어렵습니다."
    elif pattern.state == "confirmed":
        score = max(score, 0.62)
        label = "확인 완료"
        note = "패턴 구조와 확인 신호가 모두 붙어 현재 기준으로 가장 실전형에 가까운 단계입니다."
    elif pattern.state == "armed":
        score = max(score, 0.58)
        label = "활성 임박"
        note = "핵심 가격대에 근접해 있어 돌파 또는 확인 여부를 바로 체크할 단계입니다."
    elif completion >= 0.58:
        label = "형성 진전"
        note = "패턴이 꽤 진행되어 관찰 가치는 높지만 아직 확인 전이므로 성급한 해석은 주의가 필요합니다."
    else:
        label = "초기 형성"
        note = "구조는 보이지만 아직 초기 단계라 교과서형 패턴으로 단정하기에는 이릅니다."

    if bars_since_signal > 0 and recency < 0.35 and not terminal:
        score = min(score, 0.48)
        note = f"{note} 신호 발생 이후 {bars_since_signal}개 바가 지나 신선도도 함께 낮아졌습니다."

    return {
        "lifecycle_score": round(max(0.0, min(1.0, score)), 3),
        "lifecycle_label": label,
        "lifecycle_note": note,
    }

def _active_setup_profile(
    items: list[tuple[PatternResult, float, float, int, str | None, str | None]],
) -> dict[str, Any]:
    if not items:
        return {
            "active_setup_score": 0.0,
            "active_setup_label": "활성 셋업 없음",
            "active_setup_summary": "현재 활성 상태로 볼 패턴이 없어 관찰 우선 종목으로 보기 어렵습니다.",
            "active_pattern_count": 0,
            "completed_pattern_count": 0,
        }

    lifecycle_rows: list[dict[str, Any]] = []
    active_count = 0
    completed_count = 0
    for pattern, completion, recency, bars_since_signal, target_hit_at, invalidated_at in items:
        terminal = _pattern_is_terminal(pattern, target_hit_at, invalidated_at)
        if terminal:
            completed_count += 1
        else:
            active_count += 1
        lifecycle = _pattern_lifecycle_profile(pattern, completion, recency, bars_since_signal, target_hit_at, invalidated_at)
        lifecycle_rows.append({"pattern": pattern, "terminal": terminal, **lifecycle})

    active_rows = [row for row in lifecycle_rows if not row["terminal"]]
    score = max((float(row["lifecycle_score"]) for row in active_rows), default=0.0)
    if active_count == 0:
        label = "종료 패턴 위주"
        summary = "현재 잡힌 패턴은 대부분 이미 끝났거나 무효화된 상태입니다. 신규 진입보다 과거 패턴 정리에 가깝습니다."
    elif score >= 0.72:
        label = "활성 셋업 강함"
        summary = f"지금 살아 있는 패턴이 {active_count}개이며, 그중 적어도 하나는 실전 후보로 바로 볼 만한 강도를 보입니다."
    elif score >= 0.56:
        label = "활성 셋업 보통"
        summary = f"지금 살아 있는 패턴이 {active_count}개입니다. 다만 추가 확인 신호가 붙을 때 해석 품질이 더 좋아집니다."
    else:
        label = "재확인 필요"
        summary = f"활성 패턴은 {active_count}개 있지만 아직 초기 형성 또는 관찰 단계 비중이 큽니다."

    if completed_count:
        summary = f"{summary} 종료 또는 무효 패턴 {completed_count}개는 별도로 감점 반영했습니다."

    return {
        "active_setup_score": round(score, 3),
        "active_setup_label": label,
        "active_setup_summary": summary,
        "active_pattern_count": active_count,
        "completed_pattern_count": completed_count,
    }

def _no_signal_text(timeframe: str, available_bars: int, source_note: str, fetch_message: str) -> tuple[str, str]:
    label = timeframe_label(timeframe)
    suffix = f" {fetch_message}" if fetch_message else ""
    if available_bars <= 0:
        return (
            "데이터 부족으로 패턴을 평가하지 못했습니다.",
            f"{label} 기준 사용할 가격 데이터가 부족합니다. {source_note}{suffix}",
        )
    if available_bars < 40:
        return (
            "표본이 적어 신호를 만들지 못했습니다.",
            f"{label} 기준 바 수가 충분하지 않아 패턴 인식과 통계 판단을 보수적으로 제한했습니다. {source_note}{suffix}",
        )
    return (
        "현재는 뚜렷한 활성 패턴이 없습니다.",
        f"{label} 기준 가격 구조는 읽히지만 교과서형 패턴으로 확정할 만한 구조는 아직 부족합니다.{suffix}",
    )


def _no_signal_action_plan(timeframe: str, data_quality: float, available_bars: int) -> dict[str, Any]:
    label = timeframe_label(timeframe)
    if is_intraday_timeframe(timeframe):
        return {
            "action_plan": "recheck",
            "action_plan_label": "재확인 필요",
            "action_plan_summary": (
                f"{label} 기준 분봉 신호가 아직 약합니다. 장중 재수집 이후 구조가 더 선명해질 수 있어, 현재는 관찰 후 재평가가 우선입니다. "
                f"현재 데이터 품질은 {round(data_quality * 100)}%이고 사용 가능한 바 수는 {available_bars}개입니다."
            ),
            "action_priority_score": round(max(0.0, min(1.0, data_quality * 0.35)), 3),
        }
    return {
        "action_plan": "cooling",
        "action_plan_label": "관망",
        "action_plan_summary": (
            f"{label} 기준 아직 구조 완성도가 낮아 즉시 대응보다 대기 쪽이 적절합니다. "
            "추가 돌파, 눌림, 거래대금 회복 같은 보강 조건이 붙는지 보는 편이 좋습니다."
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
    entry_window_score: float,
    entry_window_label: str,
    freshness_score: float,
    freshness_label: str,
    reentry_score: float,
    reentry_label: str,
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
        + 0.08 * headroom_score
        + 0.08 * entry_window_score
        + 0.08 * freshness_score
        + 0.06 * reentry_score
        + 0.08 * historical_edge_score
        + 0.06 * trend_alignment_score
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
    if freshness_label in {"종료 패턴", "무효 만료"}:
        priority -= 0.18
    elif freshness_label == "재기초 관찰":
        priority -= 0.08
    elif freshness_score < 0.30:
        priority -= 0.10
    if reentry_label == "재진입 비선호":
        priority -= 0.16
    elif reentry_label == "실패 후 복구 관찰":
        priority -= 0.08
    elif reentry_label == "재축적 관찰":
        priority -= 0.04
    if entry_window_label in {"확장 추격", "목표 근접"}:
        priority -= 0.12
    elif entry_window_label in {"트리거 대기", "관망"}:
        priority -= 0.06

    priority = round(max(0.0, min(1.0, priority)), 3)
    bullish = p_up >= p_down
    direction = "상승" if bullish else "하락"
    label = timeframe_label(timeframe)

    if invalidated_at or pattern.state == "invalidated":
        if reentry_label == "실패 후 복구 관찰":
            return {
                "action_plan": "recheck",
                "action_plan_label": "복구 관찰",
                "action_plan_summary": f"{label} 기준 무효화 이후 구조 복구를 시도하고 있어 즉시 {direction} 대응보다 복구 확인이 우선입니다.",
                "action_priority_score": priority,
            }
        return {
            "action_plan": "cooling",
            "action_plan_label": "무효 만료",
            "action_plan_summary": f"{label} 기준 패턴이 무효화되어 현재는 신규 {direction} 대응보다 관망이 우선입니다.",
            "action_priority_score": priority,
        }

    if target_hit_at or pattern.state == "played_out":
        if reentry_label == "재돌파 대기":
            return {
                "action_plan": "watch",
                "action_plan_label": "재돌파 대기",
                "action_plan_summary": f"{label} 기준 기존 목표를 소화한 뒤 재돌파형 구조가 다시 만들어지고 있습니다. 재돌파 확인 전까지는 관찰이 적절합니다.",
                "action_priority_score": priority,
            }
        if reentry_label == "재축적 관찰" or freshness_label == "재기초 관찰":
            return {
                "action_plan": "watch",
                "action_plan_label": "재기초 관찰",
                "action_plan_summary": f"{label} 기준 목표 달성 이후 다시 기준선 근처로 식고 있어 재형성 여부를 관찰할 구간입니다.",
                "action_priority_score": priority,
            }
        return {
            "action_plan": "cooling",
            "action_plan_label": "목표 소진",
            "action_plan_summary": f"{label} 기준 기존 패턴은 이미 목표가를 소화했습니다. 지금은 과거 패턴 종료로 보는 편이 안전합니다.",
            "action_priority_score": priority,
        }

    ready_now = (
        pattern.state == "confirmed"
        and entry_window_score >= 0.68
        and freshness_score >= 0.58
        and reward_risk_ratio >= 1.15
        and data_quality >= 0.6
    )
    if ready_now:
        return {
            "action_plan": "ready_now",
            "action_plan_label": "실전 후보",
            "action_plan_summary": f"{label} 기준 확인 완료 패턴이며 진입 구간과 신선도가 모두 받쳐줘 바로 검토할 수 있는 후보입니다.",
            "action_priority_score": priority,
        }

    if reentry_label == "재돌파 대기":
        return {
            "action_plan": "watch",
            "action_plan_label": "재돌파 대기",
            "action_plan_summary": f"{label} 기준 기준선 재접근 뒤 재돌파를 노려볼 수 있는 구조입니다. 돌파 확인 전까지는 관찰 우선입니다.",
            "action_priority_score": priority,
        }

    if freshness_label == "재기초 관찰":
        return {
            "action_plan": "watch",
            "action_plan_label": "재기초 관찰",
            "action_plan_summary": f"{label} 기준 과거 패턴이 끝난 뒤 재형성 가능성이 보여 즉시 대응보다 재확인이 중요합니다.",
            "action_priority_score": priority,
        }

    if reentry_label == "실패 후 복구 관찰":
        return {
            "action_plan": "recheck",
            "action_plan_label": "복구 확인",
            "action_plan_summary": f"{label} 기준 실패했던 구조를 복구하는 중이라, 추격보다 복구 지속과 거래대금 회복 여부를 먼저 보는 편이 좋습니다.",
            "action_priority_score": priority,
        }

    watch_ready = (
        pattern.state in {"armed", "forming"}
        or entry_window_label in {"트리거 임박", "트리거 대기", "기준선 접근"}
    )
    if watch_ready:
        return {
            "action_plan": "watch",
            "action_plan_label": "관찰 후보",
            "action_plan_summary": f"{label} 기준 아직 확인 전이거나 트리거 직전 단계입니다. 돌파·거래대금·무효화 기준을 함께 체크하세요.",
            "action_priority_score": priority,
        }

    if freshness_score < 0.3 or entry_window_score < 0.28:
        return {
            "action_plan": "recheck",
            "action_plan_label": "재확인 필요",
            "action_plan_summary": f"{label} 기준 구조는 보이지만 현재 자리 또는 신선도가 약해 다시 확인하는 편이 낫습니다.",
            "action_priority_score": priority,
        }

    return {
        "action_plan": "cooling",
        "action_plan_label": "관망",
        "action_plan_summary": f"{label} 기준 실전 점수는 남아 있지만 지금 자리의 손익비와 타이밍은 보수적으로 보는 편이 좋습니다.",
        "action_priority_score": priority,
    }


def _no_signal_decision_support(timeframe: str, data_quality: float, available_bars: int, fetch_status: str) -> dict[str, Any]:
    flags: list[str] = []
    checklist: list[str] = []

    if available_bars < 40:
        flags.append("사용 가능한 데이터 바 수가 적어 패턴 인식 신뢰도가 낮습니다.")
    if data_quality < 0.55:
        flags.append("데이터 품질이 낮아 현재 결과를 강한 신호로 보기 어렵습니다.")
    if fetch_status in {"kis_cooldown", "intraday_rate_limited", "yahoo_rate_limited"}:
        flags.append("분봉 수집이 제한된 상태라 저장 데이터 또는 공개 데이터 보강 비중이 높습니다.")
    if not flags:
        flags.append("현재는 무신호 상태이지만 데이터 자체는 재확인용으로 볼 수 있습니다.")

    if is_intraday_timeframe(timeframe):
        checklist.extend(
            [
                "장중 재수집 후 거래대금과 분봉 구조를 다시 확인하기",
                "시가·고가·저가 핵심 구간에서 재돌파가 나오는지 보기",
                "저장 분봉과 실시간 분봉의 시간 정렬이 맞는지 확인하기",
            ]
        )
    else:
        checklist.extend(
            [
                "주봉/월봉 추세와 현재 일봉 구조가 충돌하지 않는지 확인하기",
                "거래대금과 종가 위치가 함께 좋아지는지 확인하기",
                "최근 고점 또는 목선 재돌파 가능성을 체크하기",
            ]
        )

    return {
        "risk_flags": flags[:5],
        "confirmation_checklist": checklist[:5],
        "next_trigger": "신규 패턴이 형성되거나 데이터 품질이 좋아진 뒤 다시 분석하는 것이 좋습니다.",
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
        flags.append("패턴이 이미 무효화되어 신규 대응 근거가 약합니다.")
    if target_hit_at or pattern.state == "played_out":
        flags.append("패턴이 이미 목표 구간을 소화해 신규 진입 메리트가 낮습니다.")
    if headroom_score < 0.25 or target_distance_pct < 0.025:
        flags.append("남은 목표 공간이 좁아 추가 기대수익이 작습니다.")
    if reward_risk_ratio < 1.2:
        flags.append("손익비가 낮아 실전 대응 우위가 약합니다.")
    if confidence < 0.42:
        flags.append("패턴 신뢰도가 아직 충분히 높지 않습니다.")
    if data_quality < 0.65:
        flags.append("데이터 품질이 낮아 해석 오차 가능성이 큽니다.")
    if sample_reliability < 0.35:
        flags.append("통계 표본 신뢰도가 낮습니다.")
    if recency_score < 0.35:
        flags.append("신호가 나온 지 시간이 지나 패턴 신선도가 약해졌습니다.")
    if trend_alignment_score < 0.45:
        flags.append("상위 추세와의 정렬이 좋지 않습니다.")
    if bullish and wyckoff_phase in {"distribution", "markdown"}:
        flags.append("와이코프 국면이 상승 패턴과 잘 맞지 않습니다.")
    if bearish and wyckoff_phase in {"accumulation", "markup"}:
        flags.append("와이코프 국면이 하락 패턴과 잘 맞지 않습니다.")
    if is_intraday_timeframe(timeframe) and intraday_session_score < 0.48:
        flags.append("장중 세션 컨디션이 지금 구간에 우호적이지 않습니다.")
    if fetch_status in {"kis_cooldown", "stored_fallback", "scanner_store_only", "scanner_public_only"}:
        flags.append("실시간 수집이 제한되어 저장 또는 공개 데이터 비중이 높습니다.")

    if pattern.state == "forming":
        checklist.append("패턴이 완성되는지와 목선 형성 여부를 확인하기")
    elif pattern.state == "armed":
        checklist.append("트리거 근처에서 거래대금과 캔들 확인이 붙는지 보기")
    elif pattern.state == "confirmed":
        checklist.append("확인 직후 되돌림과 무효화 기준이 유지되는지 보기")
    else:
        checklist.append("이미 종료된 패턴인지 먼저 확인하기")

    if pattern.neckline:
        relation = "돌파" if direction == "상승" else "이탈"
        checklist.append(f"목선 {pattern.neckline:,.0f} 부근에서 {relation} 여부 확인하기")
    if pattern.invalidation_level:
        checklist.append(f"무효화 기준 {pattern.invalidation_level:,.0f} 이탈 여부 확인하기")
    if pattern.target_level and action_plan.get("action_plan") != "cooling":
        checklist.append(f"1차 목표가 {pattern.target_level:,.0f}까지 남은 공간 확인하기")
    if stop_distance_pct > 0.0:
        checklist.append(f"손절 거리 {stop_distance_pct:.1%}가 감당 가능한지 점검하기")
    if bars_since_signal is not None and bars_since_signal > 0:
        checklist.append(f"신호 이후 {bars_since_signal}개 바 경과가 해석에 미치는 영향 보기")
    if is_intraday_timeframe(timeframe):
        checklist.append("장중 재수집 시 분봉 정렬과 거래대금 회복 확인하기")
    else:
        checklist.append("상위 타임프레임 추세와 종가 위치를 함께 점검하기")

    if action_plan.get("action_plan") == "ready_now":
        next_trigger = f"{pattern_name} 패턴 기준으로 {direction} 확인이 유지되는지만 체크하면 됩니다."
    elif action_plan.get("action_plan") == "watch":
        next_trigger = "핵심 가격대에서 돌파 또는 재돌파 신호가 붙는지 기다리는 것이 다음 단계입니다."
    elif action_plan.get("action_plan") == "recheck":
        next_trigger = "데이터 품질 또는 패턴 완성도가 좋아진 뒤 다시 평가하는 것이 좋습니다."
    else:
        next_trigger = "현재는 목표 소진·무효화 여부와 같은 종료 신호를 우선 확인하는 편이 좋습니다."

    if not flags:
        flags.append("크게 치명적인 리스크는 보이지 않지만 무효화 기준 확인은 여전히 필요합니다.")

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
    entry_window: dict[str, Any] | None,
    freshness: dict[str, Any] | None,
    reentry: dict[str, Any] | None,
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
            {"label": "데이터", "score": round(data_quality, 3), "weight": 0.34, "note": "분석 가능한 데이터 품질입니다."},
            {"label": "패턴", "score": 0.0, "weight": 0.33, "note": "현재 활성 패턴이 없습니다."},
            {"label": "실전 액션", "score": action_score, "weight": 0.33, "note": str(action_plan.get("action_plan_summary") or "")},
        ]
        score = sum(float(item["score"]) * float(item["weight"]) for item in factors)
        return {
            "trade_readiness_score": round(max(0.0, min(1.0, score)), 3),
            "trade_readiness_label": _readiness_label(score),
            "trade_readiness_summary": "활성 패턴이 없어 현재는 관찰·재확인 단계로 보는 편이 좋습니다.",
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
    entry_window_score = float((entry_window or {}).get("entry_window_score", 0.0))
    entry_window_label = str((entry_window or {}).get("entry_window_label") or "재확인 필요")
    entry_window_summary = str((entry_window or {}).get("entry_window_summary") or "")
    freshness_score = float((freshness or {}).get("freshness_score", 0.0))
    freshness_label = str((freshness or {}).get("freshness_label") or "재확인 필요")
    freshness_summary = str((freshness or {}).get("freshness_summary") or "")
    reentry_score = float((reentry or {}).get("reentry_score", 0.0))
    reentry_label = str((reentry or {}).get("reentry_label") or "재확인 필요")
    reentry_summary = str((reentry or {}).get("reentry_summary") or "")
    evidence_score = 0.56 * sample_reliability + 0.44 * historical_edge_score
    context_score = trend_alignment_score
    if is_intraday_timeframe(timeframe):
        context_score = 0.62 * trend_alignment_score + 0.38 * intraday_session_score

    if pattern.state in {"played_out", "invalidated"} or target_hit_at or invalidated_at:
        timing_score = min(timing_score, 0.16)
        opportunity_score = min(opportunity_score, 0.20)
        entry_window_score = min(entry_window_score, 0.12)
        freshness_score = min(freshness_score, 0.12)
        action_score = min(action_score, 0.18)
    if bars_since_signal is not None and bars_since_signal > 0 and recency_score < 0.35:
        timing_score = min(timing_score, 0.34)
    if freshness_label in {"종료 패턴", "무효 만료"}:
        action_score = min(action_score, 0.20)
    elif freshness_label == "재기초 관찰":
        action_score = min(max(action_score, 0.42), 0.58)
    if reentry_label == "재진입 비선호":
        action_score = min(action_score, 0.22)
    elif reentry_label == "실패 후 복구 관찰":
        action_score = min(max(action_score, 0.34), 0.48)
    elif reentry_label in {"재축적 관찰", "재돌파 대기"}:
        action_score = min(max(action_score, 0.42), 0.62)

    factors = [
        {
            "label": "패턴 완성도",
            "score": round(formation_quality, 3),
            "weight": 0.14,
            "note": "교과서 유사도와 구조 품질을 함께 반영합니다.",
        },
        {
            "label": "타이밍",
            "score": round(timing_score, 3),
            "weight": 0.12,
            "note": "완성도와 신호 최신성을 함께 봅니다.",
        },
        {
            "label": "확률/신뢰도",
            "score": round(probability_score, 3),
            "weight": 0.12,
            "note": "상승/하락 확률과 종합 신뢰도를 반영합니다.",
        },
        {
            "label": "손익비 여지",
            "score": round(opportunity_score, 3),
            "weight": 0.13,
            "note": "기대 손익비와 목표 여유를 반영합니다.",
        },
        {
            "label": "진입 구간",
            "score": round(entry_window_score, 3),
            "weight": 0.12,
            "note": entry_window_summary or f"현재 구간은 {entry_window_label} 상태입니다.",
        },
        {
            "label": "패턴 신선도",
            "score": round(freshness_score, 3),
            "weight": 0.10,
            "note": freshness_summary or f"현재 패턴 신선도는 {freshness_label} 상태입니다.",
        },
        {
            "label": "재진입 구조",
            "score": round(reentry_score, 3),
            "weight": 0.08,
            "note": reentry_summary or f"현재 재진입 평가는 {reentry_label} 상태입니다.",
        },
        {
            "label": "데이터 품질",
            "score": round(data_quality, 3),
            "weight": 0.09,
            "note": "실시간/저장/공개 데이터 품질을 반영합니다.",
        },
        {
            "label": "통계 근거",
            "score": round(evidence_score, 3),
            "weight": 0.10,
            "note": "표본 신뢰도와 백테스트 edge를 함께 반영합니다.",
        },
        {
            "label": "추세/세션",
            "score": round(context_score, 3),
            "weight": 0.04,
            "note": "상위 추세와 장중 세션 컨디션을 반영합니다.",
        },
        {
            "label": "실전 액션",
            "score": round(action_score, 3),
            "weight": 0.02,
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
    if entry_window_label in {"확장 추격", "목표 근접"}:
        raw_score = min(raw_score, 0.44)
    elif entry_window_score < 0.28:
        raw_score = min(raw_score, 0.50)
    if freshness_label in {"종료 패턴", "무효 만료"}:
        raw_score = min(raw_score, 0.22)
    elif freshness_label == "재기초 관찰":
        raw_score = min(raw_score, 0.46)
    elif freshness_score < 0.28:
        raw_score = min(raw_score, 0.50)
    if reentry_label == "재진입 비선호":
        raw_score = min(raw_score, 0.34 if target_hit_at or invalidated_at or pattern.state in {"played_out", "invalidated"} else 0.44)
    elif reentry_label == "실패 후 복구 관찰":
        raw_score = min(raw_score, 0.52)
    elif reentry_label == "재축적 관찰":
        raw_score = min(raw_score, 0.56)

    score = round(max(0.0, min(1.0, raw_score)), 3)
    label = _readiness_label(score)
    if label == "실전 후보":
        summary = "패턴, 타이밍, 손익비, 진입 구간, 신선도가 함께 맞물려 실전 검토 후보로 볼 수 있습니다."
    elif label == "관찰 후보":
        summary = "구조는 괜찮지만 한두 가지 조건이 더 붙어야 실전 대응 품질이 좋아집니다."
    elif label == "재확인 필요":
        summary = "시그널은 있으나 데이터·타이밍·신선도 중 약한 구간이 있어 다시 확인하는 편이 좋습니다."
    else:
        summary = "목표 소진, 무효화, 낮은 신선도, 추격 구간 같은 감점 요인이 커 현재는 보류에 가깝습니다."

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
    reentry: dict[str, Any] | None,
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
    reentry_case = str((reentry or {}).get("reentry_case") or "")
    reentry_case_label = str((reentry or {}).get("reentry_case_label") or "")

    if pattern.state == "played_out":
        if reentry_case == "box_reaccumulation":
            prices = [
                (steps[0], max(neckline * 0.99, current_close - span * 0.06), "range"),
                (steps[1], neckline, "coil"),
                (steps[2], neckline * 1.03 if bullish else neckline * 0.97, "rebreak"),
                (steps[3], current_close + span * 0.32 if bullish else current_close - span * 0.32, "followthrough"),
            ]
            summary = (
                f"{pattern_name} 패턴은 {reentry_case_label}으로 해석됩니다. "
                "목선 근처 박스 재축적 뒤 재돌파가 나오는 시나리오를 우선 반영했습니다."
            )
            return "박스 재축적 후 재돌파", summary, _projected_points(last_ts, timeframe, prices)

        if reentry_case == "pullback_relaunch":
            prices = [
                (steps[0], max(neckline * 1.01, current_close - span * 0.08) if bullish else min(neckline * 0.99, current_close + span * 0.08), "pullback"),
                (steps[1], current_close, "hold"),
                (steps[2], current_close + span * 0.22 if bullish else current_close - span * 0.22, "relaunch"),
                (steps[3], current_close + span * 0.42 if bullish else current_close - span * 0.42, "extension"),
            ]
            summary = (
                f"{pattern_name} 패턴은 {reentry_case_label}으로 해석됩니다. "
                "깊지 않은 눌림 뒤 재가속이 나오는 보수적 재상승 시나리오입니다."
            )
            return "눌림 후 재가속", summary, _projected_points(last_ts, timeframe, prices)

        base = max(neckline, current_close - span * 0.35) if bullish else min(neckline, current_close + span * 0.35)
        drift = current_close + span * 0.12 if bullish else current_close - span * 0.12
        prices = [
            (steps[0], base, "cooldown"),
            (steps[1], (base + current_close) / 2, "retest"),
            (steps[2], current_close, "range"),
            (steps[3], drift, "rebuild"),
        ]
        summary = (
            f"{pattern_name} 패턴은 이미 1차 목표를 소화한 뒤 숨 고르기 국면으로 보는 시나리오입니다. "
            "재돌파가 바로 나오기보다 박스 조정 또는 재기초 형성 가능성을 우선 반영했습니다."
        )
        return "목표 달성 이후 재정비", summary, _projected_points(last_ts, timeframe, prices)

    if pattern.state == "invalidated":
        if reentry_case == "failed_breakout_recovery":
            prices = [
                (steps[0], current_close, "reclaim"),
                (steps[1], max(current_close, neckline * 0.995) if bullish else min(current_close, neckline * 1.005), "retest"),
                (steps[2], neckline * 1.02 if bullish else neckline * 0.98, "rebreak"),
                (steps[3], current_close + span * 0.28 if bullish else current_close - span * 0.28, "followthrough"),
            ]
            summary = (
                f"{pattern_name} 패턴은 {reentry_case_label}으로 해석됩니다. "
                "실패했던 돌파를 복구한 뒤 다시 기준선을 회복하는 시나리오를 우선 반영했습니다."
            )
            return "실패 돌파 복구", summary, _projected_points(last_ts, timeframe, prices)

        drift = invalidation - span * 0.15 if bullish else invalidation + span * 0.15
        prices = [
            (steps[0], invalidation, "broken"),
            (steps[1], drift, "followthrough"),
            (steps[2], drift * (1.01 if bullish else 0.99), "bounce"),
            (steps[3], drift, "range"),
        ]
        summary = (
            f"{pattern_name} 패턴은 무효화 이후 새 균형점을 찾는 흐름으로 가정했습니다. "
            "기존 패턴 재개보다 손실 정리와 재축적 여부 확인이 먼저라는 의미입니다."
        )
        return "무효화 이후 재균형", summary, _projected_points(last_ts, timeframe, prices)

    if bullish:
        if pattern.state == "forming":
            prices = [
                (steps[0], max(current_close - span * 0.12, invalidation * 1.01), "handle"),
                (steps[1], neckline * 0.995, "trigger"),
                (steps[2], neckline * 1.02, "breakout"),
                (steps[3], target, "target"),
            ]
            summary = (
                f"{pattern_name} 패턴이 아직 형성 중이라 눌림과 기준선 접근을 거친 뒤 돌파가 나오는 보수적 시나리오입니다."
            )
            return "형성 후 돌파", summary, _projected_points(last_ts, timeframe, prices)

        if pattern.state == "armed":
            prices = [
                (steps[0], neckline * 0.998, "trigger"),
                (steps[1], neckline * 1.01, "breakout"),
                (steps[2], max(neckline, current_close - span * 0.08), "retest"),
                (steps[3], target, "target"),
            ]
            summary = f"{pattern_name} 패턴이 활성 직전이라 목선 돌파와 리테스트를 거쳐 목표가로 향하는 흐름을 우선 가정했습니다."
            return "돌파 임박", summary, _projected_points(last_ts, timeframe, prices)

        prices = [
            (steps[0], max(neckline, current_close - span * 0.1), "retest"),
            (steps[1], current_close + span * 0.12, "hold"),
            (steps[2], target, "target"),
            (steps[3], target + span * 0.12, "extension"),
        ]
        summary = (
            f"{pattern_name} 패턴은 이미 확인된 상태라 재테스트 이후 목표 구간과 추가 확장을 시도하는 흐름을 가정했습니다."
        )
        return "확인 후 재테스트", summary, _projected_points(last_ts, timeframe, prices)

    if pattern.state == "forming":
        prices = [
            (steps[0], min(current_close + span * 0.12, invalidation * 0.99), "handle"),
            (steps[1], neckline * 1.005, "trigger"),
            (steps[2], neckline * 0.98, "breakdown"),
            (steps[3], target, "target"),
        ]
        summary = f"{pattern_name} 패턴이 아직 형성 중이라 반등 후 기준선 이탈이 나오는 보수적 하락 시나리오입니다."
        return "형성 후 이탈", summary, _projected_points(last_ts, timeframe, prices)

    if pattern.state == "armed":
        prices = [
            (steps[0], neckline * 1.002, "trigger"),
            (steps[1], neckline * 0.99, "breakdown"),
            (steps[2], min(neckline, current_close + span * 0.08), "retest"),
            (steps[3], target, "target"),
        ]
        summary = f"{pattern_name} 패턴이 활성 직전이라 기준선 이탈과 되돌림 확인 뒤 목표가로 향하는 흐름을 우선 가정했습니다."
        return "이탈 임박", summary, _projected_points(last_ts, timeframe, prices)

    prices = [
        (steps[0], min(neckline, current_close + span * 0.1), "retest"),
        (steps[1], current_close - span * 0.12, "hold"),
        (steps[2], target, "target"),
        (steps[3], target - span * 0.12, "extension"),
    ]
    summary = f"{pattern_name} 패턴은 이미 확인된 상태라 되돌림 확인 후 추가 하락을 시도하는 흐름을 가정했습니다."
    return "확인 후 재테스트", summary, _projected_points(last_ts, timeframe, prices)


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
        entry_window=None,
        freshness=None,
        reentry=None,
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
        entry_window_score=0.0,
        entry_window_label="재확인 필요",
        entry_window_summary="활성 패턴이 없어 현재 자리의 진입 구간은 보수적으로 해석합니다.",
        freshness_score=0.0,
        freshness_label="재확인 필요",
        freshness_summary="의미 있는 활성 패턴이 아직 없어 패턴 신선도를 평가하지 않았습니다.",
        reentry_score=0.0,
        reentry_label="재확인 필요",
        reentry_summary="활성 패턴이 없어 재진입 구조 평가는 아직 보류했습니다.",
        reentry_case="none",
        reentry_case_label="구조 없음",
        reentry_trigger="활성 패턴이 충분히 쌓이면 재진입 유형을 계산합니다.",
        reentry_factors=[],
        score_factors=readiness["score_factors"],
        active_setup_score=0.0,
        active_setup_label="활성 셋업 없음",
        active_setup_summary="현재는 활성 셋업이 없어 신규 대응보다 관찰과 데이터 축적이 우선입니다.",
        active_pattern_count=0,
        completed_pattern_count=0,
        no_signal_flag=True,
        no_signal_reason=no_signal_reason,
        reason_summary=reason_summary,
        sample_size=0,
        empirical_win_rate=0.5,
        sample_reliability=0.0,
        patterns=[],
        projection_label="중립 시나리오",
        projection_summary="활성 패턴이 부족해 미래 경로는 보수적인 중립 시나리오로 처리했습니다.",
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

    patterns_with_meta.sort(key=_primary_pattern_rank_score, reverse=True)
    best_pattern, best_completion, best_recency, bars_since_signal, best_target_hit_at, best_invalidated_at = patterns_with_meta[0]
    active_setup = _active_setup_profile(patterns_with_meta)

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
    entry_window = _entry_window_profile(
        timeframe=timeframe,
        pattern=best_pattern,
        current_close=current_close,
        reward_risk_ratio=opportunity["reward_risk_ratio"],
        headroom_score=opportunity["headroom_score"],
        target_distance_pct=opportunity["target_distance_pct"],
        stop_distance_pct=opportunity["stop_distance_pct"],
        completion_proximity=best_completion,
        target_hit_at=best_target_hit_at,
        invalidated_at=best_invalidated_at,
    )
    freshness = _freshness_profile(
        timeframe=timeframe,
        pattern=best_pattern,
        current_close=current_close,
        completion_proximity=best_completion,
        recency_score=best_recency,
        headroom_score=opportunity["headroom_score"],
        target_distance_pct=opportunity["target_distance_pct"],
        stop_distance_pct=opportunity["stop_distance_pct"],
        bars_since_signal=bars_since_signal,
        target_hit_at=best_target_hit_at,
        invalidated_at=best_invalidated_at,
    )
    reentry = _reentry_profile(
        df=df,
        timeframe=timeframe,
        pattern=best_pattern,
        current_close=current_close,
        completion_proximity=best_completion,
        recency_score=best_recency,
        headroom_score=opportunity["headroom_score"],
        target_distance_pct=opportunity["target_distance_pct"],
        stop_distance_pct=opportunity["stop_distance_pct"],
        entry_window_score=entry_window["entry_window_score"],
        target_hit_at=best_target_hit_at,
        invalidated_at=best_invalidated_at,
    )

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
        reentry,
        best_target_hit_at,
        best_invalidated_at,
    )

    pattern_infos: list[PatternInfo] = []
    for pattern, completion, recency, pattern_bars_since_signal, target_hit_at, invalidated_at in patterns_with_meta:
        lifecycle = _pattern_lifecycle_profile(
            pattern,
            completion,
            recency,
            pattern_bars_since_signal,
            target_hit_at,
            invalidated_at,
        )
        pattern_infos.append(
            PatternInfo(
                pattern_type=pattern.pattern_type,
                state=pattern.state,
                grade=pattern.grade,
                variant=pattern.variant,
                lifecycle_score=lifecycle["lifecycle_score"],
                lifecycle_label=lifecycle["lifecycle_label"],
                lifecycle_note=lifecycle["lifecycle_note"],
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
        probability.no_signal_reason = "??類ｊ텥 ??ル뱴?? ??ル쪇源?嶺뚣끉裕??? ??⑥щ턄?????깆떨???リ옇???곸궡瑗룩굢?亦껋꼶梨????곕????덈펲."

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
        entry_window["entry_window_score"],
        entry_window["entry_window_label"],
        freshness["freshness_score"],
        freshness["freshness_label"],
        reentry["reentry_score"],
        reentry["reentry_label"],
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
        entry_window=entry_window,
        freshness=freshness,
        reentry=reentry,
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
        entry_window_score=entry_window["entry_window_score"],
        entry_window_label=entry_window["entry_window_label"],
        entry_window_summary=entry_window["entry_window_summary"],
        freshness_score=freshness["freshness_score"],
        freshness_label=freshness["freshness_label"],
        freshness_summary=freshness["freshness_summary"],
        reentry_score=reentry["reentry_score"],
        reentry_label=reentry["reentry_label"],
        reentry_summary=reentry["reentry_summary"],
        reentry_case=reentry["reentry_case"],
        reentry_case_label=reentry["reentry_case_label"],
        reentry_trigger=reentry["reentry_trigger"],
        reentry_factors=reentry["reentry_factors"],
        score_factors=readiness["score_factors"],
        active_setup_score=active_setup["active_setup_score"],
        active_setup_label=active_setup["active_setup_label"],
        active_setup_summary=active_setup["active_setup_summary"],
        active_pattern_count=active_setup["active_pattern_count"],
        completed_pattern_count=active_setup["completed_pattern_count"],
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






