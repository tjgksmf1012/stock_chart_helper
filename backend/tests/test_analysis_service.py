"""Characterization test for the full analysis pipeline.

analysis_service.py is a large, heuristic-heavy module with no direct tests.
This pins the end-to-end output of analyze_symbol_dataframe() for a fixed
synthetic input so that behavior-preserving refactors (e.g. pulling the many
magic numbers into a constants module) cannot silently change the numbers.

If a real behavior change is intended, update the expected values deliberately.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from app.api.schemas import SymbolInfo
from app.services.analysis_service import analyze_symbol_dataframe


def _double_bottom_df() -> pd.DataFrame:
    rng = np.random.default_rng(0)
    closes = (
        list(np.linspace(10_000, 9_000, 30))
        + list(np.linspace(9_000, 8_000, 15))
        + list(np.linspace(8_000, 9_000, 15))
        + list(np.linspace(9_000, 8_050, 15))
        + list(np.linspace(8_050, 9_400, 20))
    )
    dates = pd.bdate_range("2023-01-02", periods=len(closes))
    rows = []
    for dt, close in zip(dates, closes):
        open_px = close * (1 + rng.normal(0, 0.002))
        high = max(open_px, close) * (1 + abs(rng.normal(0, 0.003)))
        low = min(open_px, close) * (1 - abs(rng.normal(0, 0.003)))
        rows.append(
            {
                "date": dt,
                "open": round(open_px),
                "high": round(high),
                "low": round(low),
                "close": round(close),
                "volume": 1_000_000,
            }
        )
    return pd.DataFrame(rows)


async def _fixed_stats(pattern_type: str, timeframe: str) -> dict:
    return {
        "pattern_type": pattern_type,
        "timeframe": "1d",
        "win_rate": 0.6,
        "sample_size": 30,
        "wins": 18,
        "total": 30,
        "avg_mfe_pct": 0.075,
        "avg_mae_pct": 0.035,
        "avg_bars_to_outcome": 16.0,
        "historical_edge_score": 0.55,
    }


@pytest.mark.anyio
async def test_analyze_symbol_dataframe_characterization(monkeypatch):
    monkeypatch.setattr("app.services.analysis_service.get_pattern_stats", _fixed_stats)

    symbol = SymbolInfo(
        code="005930",
        name="Test",
        market="KOSPI",
        sector=None,
        market_cap=1e12,
        is_in_universe=True,
    )
    result = await analyze_symbol_dataframe(symbol, "1d", _double_bottom_df())

    assert result.timeframe == "1d"
    assert result.no_signal_flag is True
    assert result.p_up == 0.56
    assert result.p_down == 0.44
    assert result.confidence == 0.662
    assert result.entry_score == 0.326
    assert result.trade_readiness_score == 0.48
