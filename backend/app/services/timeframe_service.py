from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TimeframeSpec:
    value: str
    label: str
    chart_lookback_days: int
    analysis_lookback_days: int
    scanner_lookback_days: int
    min_bars: int
    intraday: bool = False


TIMEFRAME_SPECS: dict[str, TimeframeSpec] = {
    "1mo": TimeframeSpec("1mo", "월봉", chart_lookback_days=3650, analysis_lookback_days=3650, scanner_lookback_days=3650, min_bars=18),
    "1wk": TimeframeSpec("1wk", "주봉", chart_lookback_days=1825, analysis_lookback_days=1825, scanner_lookback_days=1825, min_bars=24),
    "1d": TimeframeSpec("1d", "일봉", chart_lookback_days=365, analysis_lookback_days=400, scanner_lookback_days=400, min_bars=40),
    "60m": TimeframeSpec("60m", "60분", chart_lookback_days=120, analysis_lookback_days=120, scanner_lookback_days=120, min_bars=28, intraday=True),
    "30m": TimeframeSpec("30m", "30분", chart_lookback_days=60, analysis_lookback_days=60, scanner_lookback_days=60, min_bars=30, intraday=True),
    "15m": TimeframeSpec("15m", "15분", chart_lookback_days=30, analysis_lookback_days=30, scanner_lookback_days=30, min_bars=30, intraday=True),
    "1m": TimeframeSpec("1m", "1분", chart_lookback_days=7, analysis_lookback_days=7, scanner_lookback_days=7, min_bars=60, intraday=True),
}

SUPPORTED_TIMEFRAMES = tuple(TIMEFRAME_SPECS.keys())
DEFAULT_TIMEFRAME = "1d"
DASHBOARD_TIMEFRAMES = ("1mo", "1wk", "1d", "60m", "30m", "15m", "1m")


def get_timeframe_spec(timeframe: str) -> TimeframeSpec:
    spec = TIMEFRAME_SPECS.get(timeframe)
    if spec is None:
        raise ValueError(f"Unsupported timeframe: {timeframe}")
    return spec


def timeframe_label(timeframe: str) -> str:
    return get_timeframe_spec(timeframe).label


def is_intraday_timeframe(timeframe: str) -> bool:
    return get_timeframe_spec(timeframe).intraday
