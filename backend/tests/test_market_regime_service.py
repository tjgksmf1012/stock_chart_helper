from __future__ import annotations

import asyncio

import pandas as pd
import pytest

import app.core.redis as cache
import app.services.market_regime_service as regime_service
from app.services.market_regime_service import _classify_regime, _close_series, get_market_regime


async def _wait_for_cache(key: str, attempts: int = 50):
    for _ in range(attempts):
        value = await cache.cache_get(key)
        if value is not None:
            return value
        await asyncio.sleep(0.01)
    return None


@pytest.fixture(autouse=True)
def memory_cache_and_fresh_lock(monkeypatch):
    monkeypatch.setattr(cache, "_mem_cache", {})

    async def _no_redis():
        return None

    monkeypatch.setattr(cache, "_try_get_redis", _no_redis)
    monkeypatch.setattr(regime_service, "_fetch_lock", None)


def _rising_close(n: int = 150, start: float = 100.0, step: float = 0.5) -> pd.Series:
    return pd.Series([start + i * step for i in range(n)])


def _falling_close(n: int = 150, start: float = 200.0, step: float = 0.5) -> pd.Series:
    return pd.Series([start - i * step for i in range(n)])


def _flat_close(n: int = 150, value: float = 100.0) -> pd.Series:
    return pd.Series([value] * n)


class TestClassifyRegime:
    def test_short_series_is_unknown(self):
        result = _classify_regime(pd.Series([100.0] * 10))
        assert result["regime"] == "unknown"
        assert result["ma20"] is None

    def test_sustained_uptrend_is_bull(self):
        result = _classify_regime(_rising_close())
        assert result["regime"] == "bull"
        assert result["current"] > result["ma60"] > 0

    def test_sustained_downtrend_is_bear(self):
        result = _classify_regime(_falling_close())
        assert result["regime"] == "bear"

    def test_flat_series_is_sideways(self):
        result = _classify_regime(_flat_close())
        assert result["regime"] == "sideways"
        assert result["change_pct"] == 0.0

    def test_change_pct_reflects_latest_move(self):
        close = _flat_close(n=100, value=100.0)
        close.iloc[-1] = 103.0
        result = _classify_regime(close)
        assert result["change_pct"] == 3.0

    def test_distance_from_ma120_is_computed(self):
        result = _classify_regime(_rising_close())
        assert result["distance_from_ma120_pct"] > 0


class TestCloseSeries:
    def test_extracts_korean_column_name(self):
        df = pd.DataFrame({"시가": [1, 2], "고가": [1, 2], "저가": [1, 2], "종가": [100.0, 101.0], "거래량": [1, 2]})
        series = _close_series(df)
        assert list(series) == [100.0, 101.0]

    def test_extracts_english_close_column(self):
        df = pd.DataFrame({"Open": [1, 2], "High": [1, 2], "Low": [1, 2], "Close": [50.0, 51.0]})
        series = _close_series(df)
        assert list(series) == [50.0, 51.0]

    def test_falls_back_to_fourth_column(self):
        df = pd.DataFrame([[1, 2, 3, 42.0], [1, 2, 3, 43.0]])
        series = _close_series(df)
        assert list(series) == [42.0, 43.0]

    def test_none_or_empty_returns_empty_series(self):
        assert _close_series(None).empty
        assert _close_series(pd.DataFrame()).empty


class TestGetMarketRegime:
    @pytest.mark.anyio
    async def test_cache_hit_returns_immediately(self):
        cached_payload = {"kospi": {"regime": "bull"}, "kosdaq": {"regime": "bull"}, "overall_regime": "bull", "generated_at": "x"}
        await cache.cache_set(regime_service._CACHE_KEY, cached_payload, ttl=1800)

        result = await get_market_regime()

        assert result == cached_payload

    @pytest.mark.anyio
    async def test_cache_miss_returns_unknown_and_populates_cache_in_background(self, monkeypatch):
        async def fake_fetch_index_df(ticker: str, days: int = 180):
            return None  # simulate total fetch failure -> _close_series(None) -> empty -> unknown

        monkeypatch.setattr(regime_service, "_fetch_index_df", fake_fetch_index_df)

        result = await get_market_regime()
        assert result["overall_regime"] == "unknown"

        cached = await _wait_for_cache(regime_service._CACHE_KEY)
        assert cached is not None
        assert cached["overall_regime"] == "unknown"

    @pytest.mark.anyio
    async def test_cache_miss_populates_bull_regime_from_fetched_data(self, monkeypatch):
        async def fake_fetch_index_df(ticker: str, days: int = 180):
            df = pd.DataFrame({"종가": _rising_close()})
            return df

        monkeypatch.setattr(regime_service, "_fetch_index_df", fake_fetch_index_df)

        await get_market_regime()  # first call: unknown, schedules background fetch

        cached = await _wait_for_cache(regime_service._CACHE_KEY)
        assert cached is not None
        assert cached["overall_regime"] == "bull"
        assert cached["kospi"]["regime"] == "bull"

    @pytest.mark.anyio
    async def test_returns_unknown_immediately_when_fetch_already_in_progress(self):
        lock = regime_service._get_fetch_lock()
        await lock.acquire()
        try:
            result = await get_market_regime()
            assert result["overall_regime"] == "unknown"
        finally:
            lock.release()
