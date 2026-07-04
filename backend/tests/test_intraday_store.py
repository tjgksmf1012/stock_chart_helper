from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pandas as pd
import pytest

from app.core.config import get_settings
from app.services.intraday_store import IntradayStore

settings = get_settings()


def _recent_start() -> str:
    # Relative to "now" so these tests don't silently fall outside the lookback
    # window (and start being filtered out as "too old") as real time passes.
    return (datetime.now(UTC).replace(tzinfo=None) - timedelta(minutes=10)).isoformat()


def _bars(minutes: int = 3, start: str | None = None) -> pd.DataFrame:
    idx = pd.date_range(start=start or _recent_start(), periods=minutes, freq="1min")
    return pd.DataFrame(
        {
            "datetime": idx,
            "open": [100.0 + i for i in range(minutes)],
            "high": [101.0 + i for i in range(minutes)],
            "low": [99.0 + i for i in range(minutes)],
            "close": [100.5 + i for i in range(minutes)],
            "volume": [1000 + i for i in range(minutes)],
            "amount": [None] * minutes,
        }
    )


@pytest.fixture
def store(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "intraday_storage_path", str(tmp_path / "test_intraday.sqlite3"))
    monkeypatch.setattr(settings, "intraday_store_retention_days", 45)
    return IntradayStore()


@pytest.mark.anyio
async def test_load_bars_empty_when_nothing_stored(store):
    df = await store.load_bars(symbol="005930", timeframe="1m", lookback_days=5)
    assert df.empty
    assert df.attrs["fetch_status"] == "stored_empty"


@pytest.mark.anyio
async def test_upsert_then_load_round_trips(store):
    bars = _bars()
    await store.upsert_bars(symbol="005930", timeframe="1m", df=bars, source="kis_intraday")

    loaded = await store.load_bars(symbol="005930", timeframe="1m", lookback_days=5)

    assert len(loaded) == 3
    assert loaded.attrs["fetch_status"] == "stored_available"
    assert loaded.attrs["stored_source"] == "kis_intraday"
    assert list(loaded["close"]) == [100.5, 101.5, 102.5]


@pytest.mark.anyio
async def test_upsert_is_idempotent_on_same_bar_time(store):
    bars = _bars()
    await store.upsert_bars(symbol="005930", timeframe="1m", df=bars, source="kis_intraday")

    updated = bars.copy()
    updated["close"] = [200.5, 201.5, 202.5]
    await store.upsert_bars(symbol="005930", timeframe="1m", df=updated, source="toss_intraday")

    loaded = await store.load_bars(symbol="005930", timeframe="1m", lookback_days=5)
    assert len(loaded) == 3  # no duplicate rows
    assert list(loaded["close"]) == [200.5, 201.5, 202.5]
    assert loaded.attrs["stored_source"] == "toss_intraday"


@pytest.mark.anyio
async def test_upsert_empty_dataframe_is_a_no_op(store):
    await store.upsert_bars(symbol="005930", timeframe="1m", df=pd.DataFrame(), source="kis_intraday")
    loaded = await store.load_bars(symbol="005930", timeframe="1m", lookback_days=5)
    assert loaded.empty


@pytest.mark.anyio
async def test_load_bars_is_scoped_by_symbol_and_timeframe(store):
    await store.upsert_bars(symbol="005930", timeframe="1m", df=_bars(), source="kis_intraday")
    await store.upsert_bars(symbol="000660", timeframe="1m", df=_bars(), source="kis_intraday")
    await store.upsert_bars(symbol="005930", timeframe="15m", df=_bars(), source="kis_intraday")

    loaded = await store.load_bars(symbol="005930", timeframe="1m", lookback_days=5)
    assert len(loaded) == 3

    status = await store.get_status()
    assert status["symbol_count"] == 2
    assert status["total_rows"] == 9
    timeframe_names = {row["timeframe"] for row in status["timeframes"]}
    assert timeframe_names == {"1m", "15m"}


@pytest.mark.anyio
async def test_old_rows_are_pruned_by_fetched_at_on_next_upsert(store):
    # NOTE: retention_days is captured on IntradayStore.__init__, so the `store` fixture's
    # value (45 days, from settings) is what actually governs pruning here.
    await store.upsert_bars(symbol="005930", timeframe="1m", df=_bars(minutes=1), source="kis_intraday")

    # Backdate this row's fetched_at (insertion time) well past the retention window —
    # pruning is keyed on fetched_at, not the bar's own timestamp.
    stale_fetched_at = (datetime.now(UTC).replace(tzinfo=None) - timedelta(days=100)).isoformat()
    with store._connect() as conn:
        conn.execute("UPDATE intraday_bars SET fetched_at = ?", (stale_fetched_at,))

    # Any subsequent upsert runs the retention-cutoff DELETE as a side effect.
    await store.upsert_bars(symbol="000660", timeframe="1m", df=_bars(minutes=1), source="kis_intraday")

    with store._connect() as conn:
        remaining_symbols = {row[0] for row in conn.execute("SELECT DISTINCT symbol FROM intraday_bars").fetchall()}
    assert remaining_symbols == {"000660"}


@pytest.mark.anyio
async def test_storage_age_minutes_reflects_recent_fetch(store):
    await store.upsert_bars(symbol="005930", timeframe="1m", df=_bars(), source="kis_intraday")
    loaded = await store.load_bars(symbol="005930", timeframe="1m", lookback_days=5)
    assert loaded.attrs["storage_age_minutes"] == 0


@pytest.mark.anyio
async def test_lookback_days_excludes_older_bars(store):
    old_bars = _bars(minutes=1, start=(datetime.now(UTC).replace(tzinfo=None) - timedelta(days=30)).isoformat())
    recent_bars = _bars(minutes=1)
    await store.upsert_bars(symbol="005930", timeframe="1m", df=old_bars, source="kis_intraday")
    await store.upsert_bars(symbol="005930", timeframe="1m", df=recent_bars, source="kis_intraday")

    loaded = await store.load_bars(symbol="005930", timeframe="1m", lookback_days=5)
    assert len(loaded) == 1
