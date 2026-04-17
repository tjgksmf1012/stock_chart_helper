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
    "1mo": TimeframeSpec("1mo", "월봉", 3650, 3650, 3650, 18),
    "1wk": TimeframeSpec("1wk", "주봉", 1825, 1825, 1825, 24),
    "1d": TimeframeSpec("1d", "일봉", 365, 400, 400, 40),
    "60m": TimeframeSpec("60m", "60분", 120, 120, 120, 28, intraday=True),
    "30m": TimeframeSpec("30m", "30분", 60, 60, 60, 30, intraday=True),
    "15m": TimeframeSpec("15m", "15분", 30, 30, 30, 30, intraday=True),
    "1m": TimeframeSpec("1m", "1분", 7, 7, 7, 60, intraday=True),
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
