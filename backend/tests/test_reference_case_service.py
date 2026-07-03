"""Regression tests for reference_case_service.py's outcome resolution.

_outcome_from_future() had two bugs of the same class already fixed elsewhere this
session:
1. Checked target-before-stop within the same forward bar, always resolving a bar
   that touches both as a "success" (backtest_engine.py's _resolve_bar_outcome and
   offline_calibration.py's simulate_window_outcome were already fixed to check the
   stop first).
2. Used its own hardcoded, stale direction set instead of pattern_engine.py's single
   source of truth -- missing momentum_breakout, and treating rectangle (now
   direction-neutral) as always-bullish.
"""

from __future__ import annotations

from datetime import datetime

import pandas as pd
import pytest

from app.services.pattern_engine import PatternResult
from app.services.reference_case_service import _outcome_from_future


def _pattern(pattern_type: str, target: float, invalidation: float, neckline: float | None = None) -> PatternResult:
    return PatternResult(
        pattern_type=pattern_type,
        state="confirmed",
        grade="B",
        start_dt=datetime(2023, 1, 1),
        end_dt=datetime(2023, 3, 1),
        neckline=neckline if neckline is not None else (target + invalidation) / 2,
        target_level=target,
        invalidation_level=invalidation,
    )


def _window_df(close: float) -> pd.DataFrame:
    return pd.DataFrame([{"close": close}])


def _future_bar(high: float, low: float, date: str = "2023-03-02") -> pd.DataFrame:
    return pd.DataFrame([{"high": high, "low": low, "close": (high + low) / 2, "date": date}])


class TestTouchOrderConservative:
    def test_bullish_bar_touching_both_target_and_stop_is_failure(self):
        pattern = _pattern("double_bottom", target=110.0, invalidation=95.0)
        result = _outcome_from_future(pattern, _window_df(100.0), _future_bar(high=115.0, low=90.0))
        assert result["outcome_label"] == "실패"

    def test_bearish_bar_touching_both_target_and_stop_is_failure(self):
        pattern = _pattern("double_top", target=90.0, invalidation=105.0)
        result = _outcome_from_future(pattern, _window_df(100.0), _future_bar(high=110.0, low=85.0))
        assert result["outcome_label"] == "실패"

    def test_bullish_bar_hitting_only_target_is_success(self):
        pattern = _pattern("double_bottom", target=110.0, invalidation=95.0)
        result = _outcome_from_future(pattern, _window_df(100.0), _future_bar(high=112.0, low=101.0))
        assert result["outcome_label"] == "성공"


class TestDirectionNeutralPatternsUseRealDirection:
    """rectangle used to be hardcoded bullish-only in this file's own stale direction
    set; symmetric_triangle/channels weren't in that set at all and fell to the
    implicit bearish 'else' branch regardless of actual breakout direction.
    """

    def test_rectangle_bearish_instance_resolves_bearish(self):
        # target below neckline -> this instance broke down; a rally back up should
        # resolve as a stop-out (invalidation above), not a bullish "success".
        pattern = _pattern("rectangle", target=90.0, invalidation=105.0, neckline=100.0)
        result = _outcome_from_future(pattern, _window_df(100.0), _future_bar(high=106.0, low=98.0))
        assert result["outcome_label"] == "실패"
        assert "이탈" not in result["outcome_summary"] or "손절" in result["outcome_summary"]

    def test_symmetric_triangle_bullish_instance_resolves_bullish(self):
        # target above neckline -> bullish breakout; hitting the (lower) invalidation
        # should be a failure, not misread as a bearish "target hit".
        pattern = _pattern("symmetric_triangle", target=110.0, invalidation=95.0, neckline=100.0)
        result = _outcome_from_future(pattern, _window_df(100.0), _future_bar(high=103.0, low=94.0))
        assert result["outcome_label"] == "실패"
        assert result["outcome_return_pct"] < 0
