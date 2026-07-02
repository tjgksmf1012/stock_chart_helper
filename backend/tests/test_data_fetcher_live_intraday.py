from __future__ import annotations

import pandas as pd
import pytest

from app.services.data_fetcher import KRXDataFetcher, settings
import app.services.data_fetcher as data_fetcher_module
import app.core.redis as cache


def _bars(minutes: int = 3, start: str = "2026-06-25 09:30:00") -> pd.DataFrame:
    idx = pd.date_range(start=start, periods=minutes, freq="1min")
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


class FakeKIS:
    def __init__(self, configured: bool = True, bars: pd.DataFrame | None = None, raise_exc: Exception | None = None):
        self.configured = configured
        self._bars = bars if bars is not None else pd.DataFrame()
        self._raise = raise_exc
        self.calls = 0

    async def fetch_today_minute_bars(self, code: str) -> pd.DataFrame:
        self.calls += 1
        if self._raise:
            raise self._raise
        return self._bars


class FakeToss:
    def __init__(self, configured: bool = True, bars: pd.DataFrame | None = None, raise_exc: Exception | None = None):
        self.configured = configured
        self._bars = bars if bars is not None else pd.DataFrame()
        self._raise = raise_exc
        self.calls = 0

    async def fetch_minute_candles(self, code: str, count: int = 390, max_pages: int = 3) -> pd.DataFrame:
        self.calls += 1
        if self._raise:
            raise self._raise
        return self._bars


class FakeIntradayStore:
    def __init__(self, stored_df: pd.DataFrame | None = None):
        self._stored_df = stored_df if stored_df is not None else pd.DataFrame()
        self.upserted: list[tuple] = []

    async def load_bars(self, *, symbol: str, timeframe: str, lookback_days: int) -> pd.DataFrame:
        return self._stored_df

    async def upsert_bars(self, *, symbol: str, timeframe: str, df: pd.DataFrame, source: str) -> None:
        self.upserted.append((symbol, timeframe, df, source))

    async def get_status(self) -> dict:
        return {}


@pytest.fixture
def memory_cache(monkeypatch):
    monkeypatch.setattr(cache, "_mem_cache", {})

    async def _no_redis():
        return None

    monkeypatch.setattr(cache, "_try_get_redis", _no_redis)


@pytest.fixture
def fetcher_factory(monkeypatch, memory_cache):
    """Returns a factory that builds a KRXDataFetcher with fake KIS/Toss/store/yahoo wired in."""

    def _build(
        kis: FakeKIS | None = None,
        toss: FakeToss | None = None,
        stored_df: pd.DataFrame | None = None,
        yahoo_df: pd.DataFrame | None = None,
    ) -> KRXDataFetcher:
        fake_store = FakeIntradayStore(stored_df)
        monkeypatch.setattr(data_fetcher_module, "get_intraday_store", lambda: fake_store)

        f = KRXDataFetcher(kis_client=kis or FakeKIS(configured=False), toss_client=toss or FakeToss(configured=False))

        async def _fake_yahoo(code: str, timeframe: str, period_days: int) -> pd.DataFrame:
            df = yahoo_df if yahoo_df is not None else pd.DataFrame()
            df = df.copy()
            if df.empty:
                df.attrs.update(data_source="yahoo_fallback", fetch_status="yahoo_empty", fetch_message="no data")
            else:
                df.attrs.update(data_source="yahoo_fallback", fetch_status="live_ok", fetch_message="ok")
            return df

        monkeypatch.setattr(f, "_get_yahoo_intraday_ohlcv", _fake_yahoo)
        f.store = fake_store
        return f

    return _build


@pytest.mark.anyio
async def test_live_provider_order_defaults_to_toss_first(fetcher_factory):
    toss = FakeToss(configured=True, bars=_bars())
    kis = FakeKIS(configured=True, bars=_bars())
    fetcher = fetcher_factory(kis=kis, toss=toss)

    result = await fetcher._get_live_intraday_ohlcv("005930", "1m")

    assert not result.empty
    assert result.attrs["data_source"] == "toss_intraday"
    assert toss.calls == 1
    assert kis.calls == 0


@pytest.mark.anyio
async def test_live_provider_falls_back_to_kis_when_toss_empty(fetcher_factory):
    toss = FakeToss(configured=True, bars=pd.DataFrame())
    kis = FakeKIS(configured=True, bars=_bars())
    fetcher = fetcher_factory(kis=kis, toss=toss)

    result = await fetcher._get_live_intraday_ohlcv("005930", "1m")

    assert not result.empty
    assert result.attrs["data_source"] == "kis_intraday"
    assert toss.calls == 1
    assert kis.calls == 1


@pytest.mark.anyio
async def test_live_provider_order_setting_prefers_kis(fetcher_factory, monkeypatch):
    monkeypatch.setattr(settings, "live_intraday_provider_order", "kis,toss")
    toss = FakeToss(configured=True, bars=_bars())
    kis = FakeKIS(configured=True, bars=_bars())
    fetcher = fetcher_factory(kis=kis, toss=toss)

    result = await fetcher._get_live_intraday_ohlcv("005930", "1m")

    assert result.attrs["data_source"] == "kis_intraday"
    assert kis.calls == 1
    assert toss.calls == 0


@pytest.mark.anyio
async def test_live_provider_both_unconfigured_returns_empty_with_reason(fetcher_factory):
    fetcher = fetcher_factory(kis=FakeKIS(configured=False), toss=FakeToss(configured=False))

    result = await fetcher._get_live_intraday_ohlcv("005930", "1m")

    assert result.empty
    assert result.attrs["fetch_status"] in {"toss_not_configured", "kis_not_configured"}


@pytest.mark.anyio
async def test_toss_error_marks_cooldown_and_falls_back_to_kis(fetcher_factory):
    toss = FakeToss(configured=True, raise_exc=RuntimeError("boom"))
    kis = FakeKIS(configured=True, bars=_bars())
    fetcher = fetcher_factory(kis=kis, toss=toss)

    result = await fetcher._get_live_intraday_ohlcv("005930", "1m")

    assert result.attrs["data_source"] == "kis_intraday"
    # A second call should skip Toss entirely because it's now in cooldown.
    toss.calls = 0
    result2 = await fetcher._get_live_intraday_ohlcv("005930", "1m")
    assert toss.calls == 0
    assert result2.attrs["data_source"] == "kis_intraday"


def test_merge_intraday_sources_prefers_provider_for_recent_bars(fetcher_factory):
    fetcher = fetcher_factory()
    historical = _bars(minutes=2, start="2020-01-01 09:30:00")  # far in the past
    provider = _bars(minutes=2, start="2020-01-01 09:30:00")
    provider["close"] = [999.0, 998.0]  # distinguish provider rows

    merged = fetcher._merge_intraday_sources(historical, provider)

    assert merged.attrs["data_source"] == "hybrid_intraday"
    # provider rows win for overlapping timestamps (kept via drop_duplicates(keep="last"))
    assert list(merged["close"]) == [999.0, 998.0]


def test_combine_intraday_failure_generalizes_toss_prefix(fetcher_factory):
    fetcher = fetcher_factory()
    yahoo_empty = pd.DataFrame()
    yahoo_empty.attrs["fetch_status"] = "yahoo_empty"
    toss_not_configured = pd.DataFrame()
    toss_not_configured.attrs["fetch_status"] = "toss_not_configured"

    status, message = fetcher._combine_intraday_failure(yahoo_empty, toss_not_configured)

    assert status == "intraday_empty"
    assert "토스증권" in message


@pytest.mark.anyio
async def test_get_stock_intraday_ohlcv_augments_live_with_stored_bars(fetcher_factory):
    stored = _bars(minutes=2, start="2026-06-25 09:00:00")
    toss = FakeToss(configured=True, bars=_bars(minutes=3, start="2026-06-25 09:30:00"))
    fetcher = fetcher_factory(kis=FakeKIS(configured=False), toss=toss, stored_df=stored)

    result = await fetcher.get_stock_intraday_ohlcv("005930", "1m", days=5)

    assert not result.empty
    assert len(result) == 5  # 2 stored + 3 live, no overlap
    assert result.attrs["fetch_status"] == "live_augmented_by_store"
    assert fetcher.store.upserted, "expected upsert_bars to be called with the combined frame"
