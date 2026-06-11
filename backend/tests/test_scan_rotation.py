"""스캔 로테이션(_rotate_scan_slice)·결과 병합(_merge_scan_results) 테스트."""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from app.services import scanner as sc


def _codes(rows):
    return [code for code, _, _ in rows]


def _mk(n: int):
    return [(f"{i:06d}", f"종목{i}", "KOSPI") for i in range(n)]


class _FakeCache:
    def __init__(self):
        self.store = {}

    async def get(self, key):
        return self.store.get(key)

    async def set(self, key, value, ttl=None):
        self.store[key] = value


@pytest.fixture
def fake_cache(monkeypatch):
    cache = _FakeCache()
    monkeypatch.setattr("app.services.scanner.cache_get", cache.get)
    monkeypatch.setattr("app.services.scanner.cache_set", cache.set)
    return cache


class TestRotateScanSlice:
    @pytest.mark.anyio
    async def test_small_universe_returns_all(self, fake_cache):
        rows = _mk(80)
        out = await sc._rotate_scan_slice(rows, 100)
        assert out == rows

    @pytest.mark.anyio
    async def test_fixed_head_always_included_and_tail_rotates(self, fake_cache):
        rows = _mk(200)
        first = await sc._rotate_scan_slice(rows, 100)
        second = await sc._rotate_scan_slice(rows, 100)

        head = _codes(rows[:50])
        assert _codes(first)[:50] == head
        assert _codes(second)[:50] == head
        # 회전부(50개씩)는 겹치지 않아야 한다
        assert set(_codes(first)[50:]).isdisjoint(set(_codes(second)[50:]))
        # 두 번이면 꼬리 150개 중 100개 커버
        covered = set(_codes(first)[50:]) | set(_codes(second)[50:])
        assert len(covered) == 100

    @pytest.mark.anyio
    async def test_wraps_around(self, fake_cache):
        rows = _mk(200)  # tail 150, 회전 50/스캔 → 3스캔이면 전체 커버 후 랩
        seen = set()
        for _ in range(3):
            out = await sc._rotate_scan_slice(rows, 100)
            seen |= set(_codes(out)[50:])
        assert len(seen) == 150  # 꼬리 전체 커버
        fourth = await sc._rotate_scan_slice(rows, 100)
        assert set(_codes(fourth)[50:]) <= seen  # 랩어라운드


def _signal_row(code: str, *, no_signal: bool = False, scanned_at: str | None = None, source: str = "fdr") -> dict:
    row = {
        "code": code,
        "no_signal_flag": no_signal,
        "trade_readiness_score": 0.5,
        "data_source": source,
    }
    if scanned_at is not None:
        row["scanned_at"] = scanned_at
    return row


class TestMergeScanResults:
    def test_fresh_replaces_same_code(self):
        old = [_signal_row("A", scanned_at=datetime.utcnow().isoformat())]
        old[0]["trade_readiness_score"] = 0.1
        fresh = [_signal_row("A")]
        merged = sc._merge_scan_results(old, fresh)
        assert len(merged) == 1
        assert merged[0]["trade_readiness_score"] == 0.5

    def test_carries_recent_signal_rows(self):
        recent = datetime.utcnow().isoformat()
        old = [_signal_row("B", scanned_at=recent)]
        merged = sc._merge_scan_results(old, [_signal_row("A")])
        assert {row["code"] for row in merged} == {"A", "B"}

    def test_drops_old_no_signal_and_placeholder_and_stale(self):
        recent = datetime.utcnow().isoformat()
        stale = (datetime.utcnow() - timedelta(hours=72)).isoformat()
        old = [
            _signal_row("NS", no_signal=True, scanned_at=recent),       # no_signal → 제외
            _signal_row("PH", scanned_at=recent, source="placeholder_seed"),  # placeholder → 제외
            _signal_row("ST", scanned_at=stale),                        # 48h 초과 → 제외
            _signal_row("NOTS"),                                        # scanned_at 없음 → 제외
            _signal_row("OK", scanned_at=recent),
        ]
        merged = sc._merge_scan_results(old, [_signal_row("A")])
        assert {row["code"] for row in merged} == {"A", "OK"}

    def test_fresh_rows_get_scanned_at(self):
        merged = sc._merge_scan_results(None, [_signal_row("A")])
        assert "scanned_at" in merged[0]

    def test_caps_total_size(self):
        recent = datetime.utcnow().isoformat()
        old = [_signal_row(f"O{i}", scanned_at=recent) for i in range(300)]
        merged = sc._merge_scan_results(old, [_signal_row("A")])
        assert len(merged) == sc._MERGED_RESULTS_MAX
