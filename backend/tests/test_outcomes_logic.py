from __future__ import annotations

from datetime import datetime

import pandas as pd
import pytest

from app.api.routes.outcomes import (
    PriceEvent,
    _decide_outcome_from_events,
    _load_price_path_since_signal,
)


def test_decide_outcome_marks_win_when_target_hits_first():
    decision = _decide_outcome_from_events(
        events=[
            PriceEvent(
                when=datetime(2026, 4, 21, 15, 0),
                high=102.0,
                low=98.0,
                close=101.0,
                basis="daily_high_low",
            ),
            PriceEvent(
                when=datetime(2026, 4, 22, 15, 0),
                high=111.0,
                low=103.0,
                close=109.0,
                basis="daily_high_low",
            ),
        ],
        target_price=110.0,
        stop_price=95.0,
    )

    assert decision is not None
    assert decision.outcome == "win"
    assert decision.exit_price == 110.0
    assert decision.evaluation_basis == "daily_high_low"


def test_decide_outcome_is_conservative_when_same_bar_hits_target_and_stop():
    decision = _decide_outcome_from_events(
        events=[
            PriceEvent(
                when=datetime(2026, 4, 22, 10, 5),
                high=111.0,
                low=94.0,
                close=101.0,
                basis="intraday_high_low",
            ),
        ],
        target_price=110.0,
        stop_price=95.0,
    )

    assert decision is not None
    assert decision.outcome == "stopped_out"
    assert decision.exit_price == 95.0
    assert "보수적으로 손절 처리" in decision.reason


@pytest.mark.anyio
async def test_load_price_path_since_signal_excludes_same_day_daily_bar_before_signal(monkeypatch):
    class StubFetcher:
        async def get_stock_ohlcv(self, symbol, start, end):
            return pd.DataFrame(
                [
                    {"date": pd.Timestamp("2026-04-21"), "open": 100, "high": 120, "low": 95, "close": 118},
                    {"date": pd.Timestamp("2026-04-22"), "open": 118, "high": 121, "low": 110, "close": 119},
                ]
            )

        async def get_stock_intraday_ohlcv(self, symbol, timeframe, days):
            return pd.DataFrame(
                [
                    {"datetime": pd.Timestamp("2026-04-21 10:00:00"), "open": 100, "high": 101, "low": 99, "close": 100},
                    {"datetime": pd.Timestamp("2026-04-21 15:10:00"), "open": 100, "high": 111, "low": 100, "close": 109},
                ]
            )

    monkeypatch.setattr("app.api.routes.outcomes.get_data_fetcher", lambda: StubFetcher())

    snapshot = await _load_price_path_since_signal(
        "005930",
        datetime(2026, 4, 21).date(),
        "1d",
        datetime(2026, 4, 21, 15, 0),
    )

    assert len(snapshot.events) == 1
    assert snapshot.events[0].when == datetime(2026, 4, 21, 15, 10)
    assert snapshot.highest_high == 111
    assert snapshot.lowest_low == 100
