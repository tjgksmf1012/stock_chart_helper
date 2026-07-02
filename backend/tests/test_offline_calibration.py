from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from app.api.schemas import SymbolInfo
from app.services.offline_calibration import (
    _select_offline_symbols,
    collect_symbol_pairs,
    simulate_window_outcome,
)


def make_forward(rows: list[tuple[float, float]]) -> pd.DataFrame:
    """rows = [(high, low), ...]"""
    return pd.DataFrame(
        [
            {"date": pd.Timestamp("2024-01-01") + pd.Timedelta(days=i), "open": 100, "high": h, "low": l, "close": (h + l) / 2, "volume": 1000}
            for i, (h, l) in enumerate(rows)
        ]
    )


class TestSimulateWindowOutcome:
    def test_bullish_target_hit_first_is_win(self):
        fwd = make_forward([(105, 99), (112, 101)])  # 2nd bar high >= 110
        assert simulate_window_outcome(fwd, bullish=True, target=110, invalidation=95) is True

    def test_bullish_invalidation_hit_first_is_loss(self):
        fwd = make_forward([(105, 94), (112, 101)])  # 1st bar low <= 95
        assert simulate_window_outcome(fwd, bullish=True, target=110, invalidation=95) is False

    def test_bullish_same_bar_both_is_conservative_loss(self):
        fwd = make_forward([(112, 94)])
        assert simulate_window_outcome(fwd, bullish=True, target=110, invalidation=95) is False

    def test_bearish_target_below_is_win_when_low_touches(self):
        fwd = make_forward([(101, 89)])  # low <= 90
        assert simulate_window_outcome(fwd, bullish=False, target=90, invalidation=105) is True

    def test_bearish_invalidation_above_is_loss_when_high_touches(self):
        fwd = make_forward([(106, 98)])  # high >= 105
        assert simulate_window_outcome(fwd, bullish=False, target=90, invalidation=105) is False

    def test_unresolved_returns_none(self):
        fwd = make_forward([(102, 98), (103, 99)])
        assert simulate_window_outcome(fwd, bullish=True, target=110, invalidation=95) is None

    def test_empty_forward_returns_none(self):
        assert simulate_window_outcome(make_forward([]), bullish=True, target=110, invalidation=95) is None


def _double_bottom_closes() -> list[float]:
    return (
        list(np.linspace(10_000, 9_000, 30))
        + list(np.linspace(9_000, 8_000, 15))
        + list(np.linspace(8_000, 9_000, 15))
        + list(np.linspace(9_000, 8_050, 15))
        + list(np.linspace(8_050, 9_400, 20))
        + list(np.linspace(9_400, 10_400, 30))  # forward bars so the signal can resolve
    )


def _build_df(closes: list[float]) -> pd.DataFrame:
    rng = np.random.default_rng(0)
    dates = pd.bdate_range("2023-01-02", periods=len(closes))
    rows = []
    for dt, close in zip(dates, closes):
        open_px = close * (1 + rng.normal(0, 0.002))
        high = max(open_px, close) * (1 + abs(rng.normal(0, 0.003)))
        low = min(open_px, close) * (1 - abs(rng.normal(0, 0.003)))
        rows.append({"date": dt, "open": round(open_px), "high": round(high), "low": round(low), "close": round(close), "volume": 1_000_000})
    return pd.DataFrame(rows)


async def _fixed_stats(pattern_type: str, timeframe: str) -> dict:
    return {
        "pattern_type": pattern_type, "timeframe": "1d", "win_rate": 0.6,
        "sample_size": 30, "wins": 18, "total": 30, "avg_mfe_pct": 0.075,
        "avg_mae_pct": 0.035, "avg_bars_to_outcome": 16.0, "historical_edge_score": 0.55,
    }


@pytest.mark.anyio
async def test_collect_symbol_pairs_yields_valid_pairs(monkeypatch):
    monkeypatch.setattr("app.services.analysis_service.get_pattern_stats", _fixed_stats)

    symbol = SymbolInfo(code="005930", name="Test", market="KOSPI", sector=None, market_cap=1e12, is_in_universe=True)
    df = _build_df(_double_bottom_closes())

    pairs, meta = await collect_symbol_pairs(
        symbol, "1d", df, window=95, step=5, max_forward=30,
    )

    assert meta["windows"] > 0
    assert meta["signals"] >= len(pairs)
    for predicted, won in pairs:
        assert 0.0 <= predicted <= 1.0
        assert isinstance(won, bool)


class TestUnresolvedWindowsCountTowardCalibration:
    """Regression: unresolved (timeout) windows used to be dropped entirely instead of
    counted as a non-win, inflating the offline calibration's realized win rate relative
    to backtest_engine.py's own (already-conservative) treatment of timeouts.
    """

    @pytest.mark.anyio
    async def test_unresolved_window_is_appended_as_a_loss_not_dropped(self, monkeypatch):
        # Stub analyze_symbol_dataframe so every window is a confirmed signal with a
        # target/invalidation far outside the (flat, low-volatility) forward bars --
        # isolates the unresolved-handling fix from the real pattern engine's own gating.
        class _FakePattern:
            pattern_type = "double_bottom"
            target_level = 999_999.0
            invalidation_level = 1.0

        class _FakeResult:
            no_signal_flag = False
            patterns = [_FakePattern()]
            p_up = 0.6
            p_down = 0.4

        async def _fake_analyze(symbol, timeframe, window_df):
            return _FakeResult()

        monkeypatch.setattr("app.services.offline_calibration.analyze_symbol_dataframe", _fake_analyze)

        symbol = SymbolInfo(code="005930", name="Test", market="KOSPI", sector=None, market_cap=1e12, is_in_universe=True)
        df = _build_df([10_000.0] * 130)  # flat: forward bars never touch target or stop

        pairs, meta = await collect_symbol_pairs(symbol, "1d", df, window=95, step=5, max_forward=30)

        assert meta["signals"] > 0
        assert meta["unresolved"] == meta["signals"]
        # Before the fix, unresolved windows were skipped entirely (never appended), so
        # len(pairs) would be 0 here. Now they're appended as a loss.
        assert len(pairs) == meta["signals"]
        assert all(won is False for _, won in pairs)


class TestSelectOfflineSymbols:
    def test_returns_all_when_max_exceeds_universe(self):
        universe = ["005930", "000660", "035420"]
        assert _select_offline_symbols(universe, 10) == universe

    def test_spreads_across_the_universe_instead_of_just_the_prefix(self):
        universe = [str(i) for i in range(100)]
        selected = _select_offline_symbols(universe, 10)
        assert len(selected) == 10
        # Should not just be the first 10 (megacap-only) -- must reach well into the tail.
        assert max(int(code) for code in selected) >= 80

    def test_zero_or_negative_returns_empty(self):
        assert _select_offline_symbols(["005930"], 0) == []
        assert _select_offline_symbols(["005930"], -1) == []
