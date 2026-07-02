"""Tests for _resolve_live_price() — the KIS -> Toss live-quote fallback chain used by
GET /symbols/{symbol}/price. Before this, the price endpoint only ever checked KIS and
skipped straight to a non-live daily-bar fallback, even though the Toss client already
had a working fetch_current_price() that was never wired in.
"""

from __future__ import annotations

import pytest

from app.api.routes.symbols import _resolve_live_price


class FakeClient:
    def __init__(self, configured: bool = True, price: dict | None = None, raise_exc: Exception | None = None):
        self.configured = configured
        self._price = price
        self._raise = raise_exc
        self.calls = 0

    async def fetch_current_price(self, code: str):
        self.calls += 1
        if self._raise:
            raise self._raise
        return self._price


async def _prev_close_fn(current_close: float) -> float:
    return current_close * 0.98


class TestResolveLivePrice:
    @pytest.mark.anyio
    async def test_prefers_kis_when_both_configured(self):
        kis = FakeClient(configured=True, price={"close": 100.0, "volume": 500, "timestamp": "t1"})
        toss = FakeClient(configured=True, price={"close": 200.0, "timestamp": "t2"})

        info = await _resolve_live_price("005930", kis, toss, _prev_close_fn)

        assert info is not None
        assert info.source == "kis"
        assert info.close == 100.0
        assert kis.calls == 1
        assert toss.calls == 0

    @pytest.mark.anyio
    async def test_falls_back_to_toss_when_kis_not_configured(self):
        kis = FakeClient(configured=False)
        toss = FakeClient(configured=True, price={"close": 200.0, "timestamp": "t2"})

        info = await _resolve_live_price("005930", kis, toss, _prev_close_fn)

        assert info is not None
        assert info.source == "toss"
        assert info.close == 200.0

    @pytest.mark.anyio
    async def test_falls_back_to_toss_when_kis_raises(self):
        kis = FakeClient(configured=True, raise_exc=RuntimeError("kis down"))
        toss = FakeClient(configured=True, price={"close": 200.0, "timestamp": "t2"})

        info = await _resolve_live_price("005930", kis, toss, _prev_close_fn)

        assert info is not None
        assert info.source == "toss"

    @pytest.mark.anyio
    async def test_falls_back_to_toss_when_kis_returns_no_close(self):
        kis = FakeClient(configured=True, price={"close": None})
        toss = FakeClient(configured=True, price={"close": 200.0, "timestamp": "t2"})

        info = await _resolve_live_price("005930", kis, toss, _prev_close_fn)

        assert info is not None
        assert info.source == "toss"

    @pytest.mark.anyio
    async def test_returns_none_when_neither_configured(self):
        kis = FakeClient(configured=False)
        toss = FakeClient(configured=False)

        info = await _resolve_live_price("005930", kis, toss, _prev_close_fn)

        assert info is None

    @pytest.mark.anyio
    async def test_returns_none_when_both_fail(self):
        kis = FakeClient(configured=True, raise_exc=RuntimeError("kis down"))
        toss = FakeClient(configured=True, raise_exc=RuntimeError("toss down"))

        info = await _resolve_live_price("005930", kis, toss, _prev_close_fn)

        assert info is None

    @pytest.mark.anyio
    async def test_change_pct_computed_from_prev_close(self):
        kis = FakeClient(configured=True, price={"close": 100.0, "volume": 10, "timestamp": "t1"})
        toss = FakeClient(configured=False)

        info = await _resolve_live_price("005930", kis, toss, _prev_close_fn)

        assert info is not None
        assert info.prev_close == pytest.approx(98.0)
        assert info.change == pytest.approx(2.0)
        assert info.change_pct == pytest.approx(2.0 / 98.0, abs=1e-4)

    @pytest.mark.anyio
    async def test_toss_volume_defaults_to_zero(self):
        # Toss's /api/v1/prices response doesn't include volume, unlike KIS.
        kis = FakeClient(configured=False)
        toss = FakeClient(configured=True, price={"close": 200.0, "timestamp": "t2"})

        info = await _resolve_live_price("005930", kis, toss, _prev_close_fn)

        assert info is not None
        assert info.volume == 0
