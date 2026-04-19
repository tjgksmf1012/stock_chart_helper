# -*- coding: utf-8 -*-
"""Shared pytest fixtures for the stock_chart_helper backend tests."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest


@pytest.fixture
def sample_ohlcv_df() -> pd.DataFrame:
    """A 120-bar daily OHLCV DataFrame with a realistic random walk price series.

    Suitable for feeding directly into PatternEngine.detect_all() and the
    analysis helper functions.
    """
    rng = np.random.default_rng(42)
    n = 120

    # Build a random-walk price series
    returns = rng.normal(0.0, 0.012, n)
    prices = [10_000.0]
    for r in returns[1:]:
        prices.append(max(1_000.0, prices[-1] * (1 + r)))

    dates = pd.bdate_range(start="2023-01-02", periods=n)
    volumes = rng.integers(200_000, 5_000_000, n)

    rows = []
    for i, (dt, close) in enumerate(zip(dates, prices)):
        noise_open = rng.normal(0.0, 0.005)
        open_px = max(1_000.0, close * (1 + noise_open))
        high = max(open_px, close) * (1 + abs(rng.normal(0.0, 0.006)))
        low = min(open_px, close) * (1 - abs(rng.normal(0.0, 0.006)))
        rows.append(
            {
                "date": dt,
                "open": round(open_px),
                "high": round(high),
                "low": round(low),
                "close": round(close),
                "volume": int(volumes[i]),
            }
        )

    return pd.DataFrame(rows)


@pytest.fixture
def sample_ohlcv_df_long() -> pd.DataFrame:
    """A 300-bar daily DataFrame — enough for wyckoff / trend-alignment helpers."""
    rng = np.random.default_rng(7)
    n = 300

    returns = rng.normal(0.001, 0.013, n)  # slight upward drift
    prices = [8_000.0]
    for r in returns[1:]:
        prices.append(max(1_000.0, prices[-1] * (1 + r)))

    dates = pd.bdate_range(start="2022-01-03", periods=n)
    volumes = rng.integers(300_000, 8_000_000, n)

    rows = []
    for i, (dt, close) in enumerate(zip(dates, prices)):
        noise = rng.normal(0.0, 0.005)
        open_px = max(1_000.0, close * (1 + noise))
        high = max(open_px, close) * (1 + abs(rng.normal(0.0, 0.005)))
        low = min(open_px, close) * (1 - abs(rng.normal(0.0, 0.005)))
        rows.append(
            {
                "date": dt,
                "open": round(open_px),
                "high": round(high),
                "low": round(low),
                "close": round(close),
                "volume": int(volumes[i]),
            }
        )

    return pd.DataFrame(rows)
