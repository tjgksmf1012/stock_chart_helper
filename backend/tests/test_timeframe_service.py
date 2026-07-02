from __future__ import annotations

from datetime import date, datetime

import pytest

from app.services.timeframe_service import (
    current_krx_session_day,
    get_timeframe_spec,
    is_intraday_timeframe,
    kst_now,
    pattern_threshold_profile,
    previous_krx_session_day,
    probability_threshold_profile,
    resolve_daily_reference_date,
    timeframe_label,
)


class TestTimeframeSpecs:
    def test_known_timeframe_returns_spec(self):
        spec = get_timeframe_spec("1d")
        assert spec.label == "일봉"
        assert spec.intraday is False

    def test_unknown_timeframe_raises(self):
        with pytest.raises(ValueError, match="Unsupported timeframe"):
            get_timeframe_spec("5m")

    def test_timeframe_label_matches_spec(self):
        assert timeframe_label("1m") == "1분"

    @pytest.mark.parametrize("timeframe,expected", [("1m", True), ("15m", True), ("30m", True), ("60m", True), ("1d", False), ("1wk", False), ("1mo", False)])
    def test_is_intraday_timeframe(self, timeframe, expected):
        assert is_intraday_timeframe(timeframe) is expected


class TestThresholdProfiles:
    def test_known_timeframe_returns_specific_profile(self):
        profile = pattern_threshold_profile("1m")
        default = pattern_threshold_profile(None)
        assert profile != default

    def test_unknown_timeframe_falls_back_to_default(self):
        assert pattern_threshold_profile("5m") == pattern_threshold_profile(None)

    def test_probability_profile_none_is_the_default(self):
        assert probability_threshold_profile(None).forming_direction_cap == 0.60

    def test_probability_profile_unknown_falls_back_to_default(self):
        assert probability_threshold_profile("unknown_tf") == probability_threshold_profile(None)


class TestSessionDayHelpers:
    def test_current_session_day_on_weekday_is_unchanged(self):
        monday = date(2026, 6, 29)  # a Monday
        assert current_krx_session_day(monday) == monday

    def test_current_session_day_on_saturday_rolls_back_to_friday(self):
        saturday = date(2026, 6, 27)
        assert current_krx_session_day(saturday) == date(2026, 6, 26)

    def test_current_session_day_on_sunday_rolls_back_to_friday(self):
        sunday = date(2026, 6, 28)
        assert current_krx_session_day(sunday) == date(2026, 6, 26)

    def test_previous_session_day_skips_weekend(self):
        monday = date(2026, 6, 29)
        assert previous_krx_session_day(monday) == date(2026, 6, 26)

    def test_previous_session_day_on_a_weekday_is_the_prior_day(self):
        wednesday = date(2026, 7, 1)
        assert previous_krx_session_day(wednesday) == date(2026, 6, 30)


class TestKstNow:
    def test_naive_datetime_gets_kst_attached(self):
        naive = datetime(2026, 6, 29, 10, 0, 0)
        result = kst_now(naive)
        assert result.tzinfo is not None
        assert result.hour == 10

    def test_aware_datetime_gets_converted_to_kst(self):
        from zoneinfo import ZoneInfo

        utc_dt = datetime(2026, 6, 29, 1, 0, 0, tzinfo=ZoneInfo("UTC"))
        result = kst_now(utc_dt)
        assert result.hour == 10  # UTC+9


class TestResolveDailyReferenceDate:
    def test_weekend_uses_previous_session(self):
        saturday_noon = datetime(2026, 6, 27, 12, 0, 0)
        day, reason = resolve_daily_reference_date(saturday_noon)
        assert reason == "weekend_previous_session"
        assert day == date(2026, 6, 26)

    def test_weekday_after_close_uses_same_day(self):
        monday_evening = datetime(2026, 6, 29, 17, 0, 0)
        day, reason = resolve_daily_reference_date(monday_evening)
        assert reason == "same_day_after_close"
        assert day == date(2026, 6, 29)

    def test_weekday_before_close_uses_previous_session(self):
        monday_morning = datetime(2026, 6, 29, 10, 0, 0)
        day, reason = resolve_daily_reference_date(monday_morning)
        assert reason == "previous_session_before_close"
        assert day == date(2026, 6, 26)  # rolls back to Friday
