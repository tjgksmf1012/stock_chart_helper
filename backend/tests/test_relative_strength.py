"""Tests for the relative-strength (RS) and regime-fit helpers added to analysis_service.

These feed pattern_engine's VCP/momentum_breakout detectors — the app previously had no
per-stock relative-strength signal at all (regime_fit was also never actually wired into
detect_all() from the real analysis path, always defaulting to neutral).
"""

from __future__ import annotations

import pandas as pd

from app.services.analysis_service import _regime_fit_score, _relative_strength_fit


def _df_with_return(n: int, start: float, end: float) -> pd.DataFrame:
    closes = [start + (end - start) * i / (n - 1) for i in range(n)]
    dates = pd.bdate_range("2023-01-02", periods=n)
    return pd.DataFrame({"date": dates, "open": closes, "high": closes, "low": closes, "close": closes, "volume": [1_000_000.0] * n})


class TestRegimeFitScore:
    def test_bull_scores_high(self):
        market_regime = {"kospi": {"regime": "bull"}, "kosdaq": {"regime": "bear"}}
        assert _regime_fit_score(market_regime, "KOSPI") > 0.7

    def test_bear_scores_low(self):
        market_regime = {"kospi": {"regime": "bear"}, "kosdaq": {"regime": "bull"}}
        assert _regime_fit_score(market_regime, "KOSPI") < 0.3

    def test_kosdaq_uses_kosdaq_sub_dict(self):
        market_regime = {"kospi": {"regime": "bear"}, "kosdaq": {"regime": "bull"}}
        assert _regime_fit_score(market_regime, "KOSDAQ") > 0.7

    def test_unknown_regime_is_neutral(self):
        market_regime = {"kospi": {"regime": "unknown"}, "kosdaq": {"regime": "unknown"}}
        assert _regime_fit_score(market_regime, "KOSPI") == 0.5

    def test_missing_sub_dict_defaults_neutral(self):
        assert _regime_fit_score({}, "KOSPI") == 0.5


class TestRelativeStrengthFit:
    def test_none_index_return_defaults_neutral(self):
        market_regime = {"kospi": {"return_63d_pct": None}}
        df = _df_with_return(70, 100.0, 110.0)
        assert _relative_strength_fit(df, "1d", market_regime, "KOSPI") == 0.5

    def test_outperforming_market_scores_above_neutral(self):
        # stock up 20% over the window, index only up 2%
        market_regime = {"kospi": {"return_63d_pct": 0.02}}
        df = _df_with_return(70, 100.0, 120.0)
        fit = _relative_strength_fit(df, "1d", market_regime, "KOSPI")
        assert fit > 0.5

    def test_underperforming_market_scores_below_neutral(self):
        # stock flat, index up 15% -> stock is a laggard
        market_regime = {"kospi": {"return_63d_pct": 0.15}}
        df = _df_with_return(70, 100.0, 100.0)
        fit = _relative_strength_fit(df, "1d", market_regime, "KOSPI")
        assert fit < 0.5

    def test_short_history_defaults_neutral(self):
        market_regime = {"kospi": {"return_63d_pct": 0.05}}
        df = _df_with_return(10, 100.0, 105.0)  # fewer bars than the RS window
        assert _relative_strength_fit(df, "1d", market_regime, "KOSPI") == 0.5

    def test_result_is_clamped_to_unit_interval(self):
        market_regime = {"kospi": {"return_63d_pct": -0.50}}
        df = _df_with_return(70, 100.0, 300.0)  # extreme outperformance
        fit = _relative_strength_fit(df, "1d", market_regime, "KOSPI")
        assert 0.0 <= fit <= 1.0
