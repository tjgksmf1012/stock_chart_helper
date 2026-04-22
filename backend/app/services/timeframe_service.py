from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo


@dataclass(frozen=True)
class TimeframeSpec:
    value: str
    label: str
    chart_lookback_days: int
    analysis_lookback_days: int
    scanner_lookback_days: int
    min_bars: int
    intraday: bool = False


@dataclass(frozen=True)
class PatternThresholdProfile:
    price_symmetry_min: float
    max_second_leg_overshoot_pct: float
    armed_trigger_buffer_pct: float
    min_structure_height_pct: float
    max_structure_height_pct: float
    max_forming_trigger_distance_pct: float
    target_cap_floor_pct: float
    target_cap_ceiling_pct: float
    target_cap_vol_multiplier: float


@dataclass(frozen=True)
class ProbabilityThresholdProfile:
    forming_direction_cap: float
    armed_direction_cap: float
    confirmed_direction_cap: float
    no_signal_direction_cap: float
    far_target_warn_pct: float
    extreme_target_warn_pct: float
    mfe_soft_multiplier: float
    mfe_hard_multiplier: float


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
KST = ZoneInfo("Asia/Seoul")
DAILY_MARKET_CLOSE_BUFFER = time(16, 5)

PATTERN_THRESHOLD_PROFILES: dict[str | None, PatternThresholdProfile] = {
    None: PatternThresholdProfile(0.62, -0.05, 0.02, 0.025, 0.55, 0.10, 0.08, 0.30, 6.0),
    "1mo": PatternThresholdProfile(0.72, -0.025, 0.025, 0.050, 0.42, 0.11, 0.08, 0.18, 4.8),
    "1wk": PatternThresholdProfile(0.69, -0.035, 0.020, 0.035, 0.48, 0.10, 0.08, 0.22, 5.2),
    "1d": PatternThresholdProfile(0.62, -0.050, 0.020, 0.025, 0.55, 0.10, 0.08, 0.30, 6.0),
    "60m": PatternThresholdProfile(0.67, -0.030, 0.010, 0.015, 0.22, 0.055, 0.03, 0.12, 4.0),
    "30m": PatternThresholdProfile(0.68, -0.028, 0.008, 0.012, 0.18, 0.045, 0.025, 0.10, 3.6),
    "15m": PatternThresholdProfile(0.69, -0.026, 0.007, 0.010, 0.16, 0.035, 0.020, 0.09, 3.3),
    "1m": PatternThresholdProfile(0.72, -0.020, 0.005, 0.008, 0.12, 0.020, 0.010, 0.05, 2.5),
}

PROBABILITY_THRESHOLD_PROFILES: dict[str | None, ProbabilityThresholdProfile] = {
    None: ProbabilityThresholdProfile(0.60, 0.67, 0.72, 0.56, 0.24, 0.35, 2.8, 4.0),
    "1mo": ProbabilityThresholdProfile(0.62, 0.69, 0.74, 0.57, 0.26, 0.40, 3.3, 4.8),
    "1wk": ProbabilityThresholdProfile(0.61, 0.68, 0.73, 0.57, 0.22, 0.34, 3.0, 4.4),
    "1d": ProbabilityThresholdProfile(0.60, 0.67, 0.72, 0.56, 0.24, 0.35, 2.8, 4.0),
    "60m": ProbabilityThresholdProfile(0.58, 0.64, 0.69, 0.55, 0.09, 0.14, 1.9, 2.8),
    "30m": ProbabilityThresholdProfile(0.57, 0.63, 0.68, 0.55, 0.07, 0.12, 1.7, 2.4),
    "15m": ProbabilityThresholdProfile(0.56, 0.62, 0.67, 0.54, 0.06, 0.10, 1.6, 2.2),
    "1m": ProbabilityThresholdProfile(0.54, 0.60, 0.64, 0.53, 0.03, 0.05, 1.3, 1.8),
}


def get_timeframe_spec(timeframe: str) -> TimeframeSpec:
    spec = TIMEFRAME_SPECS.get(timeframe)
    if spec is None:
        raise ValueError(f"Unsupported timeframe: {timeframe}")
    return spec


def timeframe_label(timeframe: str) -> str:
    return get_timeframe_spec(timeframe).label


def is_intraday_timeframe(timeframe: str) -> bool:
    return get_timeframe_spec(timeframe).intraday


def pattern_threshold_profile(timeframe: str | None) -> PatternThresholdProfile:
    return PATTERN_THRESHOLD_PROFILES.get(timeframe, PATTERN_THRESHOLD_PROFILES[None])


def probability_threshold_profile(timeframe: str | None) -> ProbabilityThresholdProfile:
    return PROBABILITY_THRESHOLD_PROFILES.get(timeframe, PROBABILITY_THRESHOLD_PROFILES[None])


def kst_now(now: datetime | None = None) -> datetime:
    current = now or datetime.now(tz=KST)
    if current.tzinfo is None:
        return current.replace(tzinfo=KST)
    return current.astimezone(KST)


def current_krx_session_day(day: date) -> date:
    current = day
    while current.weekday() >= 5:
        current -= timedelta(days=1)
    return current


def previous_krx_session_day(day: date) -> date:
    current = day - timedelta(days=1)
    while current.weekday() >= 5:
        current -= timedelta(days=1)
    return current


def resolve_daily_reference_date(now: datetime | None = None) -> tuple[date, str]:
    current = kst_now(now)
    session_day = current_krx_session_day(current.date())
    if current.weekday() >= 5:
        return session_day, "weekend_previous_session"
    if current.timetz().replace(tzinfo=None) >= DAILY_MARKET_CLOSE_BUFFER:
        return session_day, "same_day_after_close"
    return previous_krx_session_day(session_day), "previous_session_before_close"
