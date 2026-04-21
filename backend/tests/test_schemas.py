# -*- coding: utf-8 -*-
"""Smoke-tests for the Pydantic API schemas.

Validates that:
- Schemas accept valid data without raising.
- Default values are as documented.
- Edge-case field types (None, empty lists) are accepted.
"""

from __future__ import annotations

import pytest

from app.api.schemas import (
    AnalysisResult,
    DashboardItem,
    KisPrimeStatus,
    KisRuntimeStatus,
    OHLCVBar,
    PatternInfo,
    RuntimeStatusResponse,
    ScreenerRequest,
    SymbolInfo,
)


# ─── SymbolInfo ────────────────────────────────────────────────────────────────

class TestSymbolInfo:
    def test_full(self):
        s = SymbolInfo(code="005930", name="삼성전자", market="KOSPI", sector="전기전자", market_cap=500.0, is_in_universe=True)
        assert s.code == "005930"
        assert s.market == "KOSPI"

    def test_nullable_fields(self):
        s = SymbolInfo(code="000000", name="테스트", market="KOSDAQ", sector=None, market_cap=None, is_in_universe=False)
        assert s.sector is None
        assert s.market_cap is None

    def test_market_cap_zero(self):
        s = SymbolInfo(code="000001", name="X", market="KRX", sector=None, market_cap=0.0, is_in_universe=False)
        assert s.market_cap == 0.0


# ─── OHLCVBar ──────────────────────────────────────────────────────────────────

class TestOHLCVBar:
    def test_with_amount(self):
        bar = OHLCVBar(date="2024-01-02", open=100.0, high=105.0, low=98.0, close=103.0, volume=1_000_000, amount=103_000_000.0)
        assert bar.amount == 103_000_000.0

    def test_without_amount(self):
        bar = OHLCVBar(date="2024-01-02", open=100.0, high=105.0, low=98.0, close=103.0, volume=1_000_000)
        assert bar.amount is None


# ─── ScreenerRequest ──────────────────────────────────────────────────────────

class TestScreenerRequest:
    def test_defaults(self):
        req = ScreenerRequest()
        assert req.exclude_no_signal is True
        assert req.sort_by == "composite_score"
        assert req.limit == 50
        assert req.min_textbook_similarity == 0.0
        assert req.min_p_up == 0.0
        assert req.max_p_down == 1.0
        assert req.timeframes is None

    def test_custom(self):
        req = ScreenerRequest(
            pattern_types=["double_bottom"],
            states=["confirmed"],
            min_textbook_similarity=0.6,
            min_p_up=0.55,
            timeframes=["1d", "1wk"],
            limit=10,
        )
        assert "double_bottom" in req.pattern_types  # type: ignore[operator]
        assert req.min_textbook_similarity == 0.6
        assert req.limit == 10

    def test_limit_bounds(self):
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            ScreenerRequest(limit=0)  # ge=1

        with pytest.raises(ValidationError):
            ScreenerRequest(limit=200)  # le=100


# ─── PatternInfo ──────────────────────────────────────────────────────────────

class TestPatternInfo:
    def test_minimal(self):
        p = PatternInfo(
            pattern_type="double_bottom",
            state="forming",
            grade="B",
            textbook_similarity=0.72,
            geometry_fit=0.68,
            neckline=None,
            invalidation_level=None,
            target_level=None,
            key_points=[],
            is_provisional=True,
            start_dt="2024-01-02",
            end_dt=None,
        )
        assert p.pattern_type == "double_bottom"
        assert p.state == "forming"
        assert p.neckline is None

    def test_with_levels(self):
        p = PatternInfo(
            pattern_type="ascending_triangle",
            state="confirmed",
            grade="A",
            textbook_similarity=0.88,
            geometry_fit=0.85,
            neckline=50_000.0,
            invalidation_level=45_000.0,
            target_level=55_000.0,
            key_points=[{"price": 50_000.0, "type": "breakout"}],
            is_provisional=False,
            start_dt="2024-01-10",
            end_dt="2024-03-01",
        )
        assert p.target_level == 55_000.0
        assert p.invalidation_level == 45_000.0
        assert len(p.key_points) == 1


# ─── DashboardItem / AnalysisResult — minimal smoke test ──────────────────────

def _symbol():
    return SymbolInfo(code="005930", name="삼성전자", market="KOSPI", sector=None, market_cap=300.0, is_in_universe=True)


class TestDashboardItemDefaults:
    def test_creates_with_required_only(self):
        item = DashboardItem(
            rank=1,
            symbol=_symbol(),
            timeframe="1d",
            timeframe_label="일봉",
            pattern_type=None,
            state=None,
            p_up=0.58,
            p_down=0.42,
            textbook_similarity=0.0,
            confidence=0.5,
            entry_score=0.5,
            no_signal_flag=True,
            reason_summary="패턴 없음",
        )
        assert item.rank == 1
        assert item.no_signal_flag is True
        # Check defaults
        assert item.trade_readiness_score == 0.0
        assert item.reentry_score == 0.0
        assert item.active_setup_score == 0.0
        assert item.risk_flags == []
        assert item.setup_stage == "neutral"


class TestRuntimeStatusSchemas:
    def test_runtime_status_accepts_nested_kis_prime(self):
        prime = KisPrimeStatus(
            status="ready",
            is_running=False,
            requested_at="2026-04-21T09:01:00",
            finished_at="2026-04-21T09:01:03",
            triggered_by="startup",
            symbol="005930",
            timeframe="1m",
            ok=True,
            token_cached_before=False,
            token_cached_after=True,
            store_rows_before=0,
            store_rows_after=120,
            store_rows_added=120,
            bars_returned=120,
            data_source="kis_intraday",
            fetch_status="live_ok",
            message="ok",
        )
        kis = KisRuntimeStatus(
            configured=True,
            environment="auto",
            token_cached=True,
            token_cache_path="data/kis_token_cache.json",
            max_concurrent_requests=2,
            request_spacing_ms=350,
            guidance=["ready"],
            last_prime=prime,
        )
        payload = RuntimeStatusResponse(
            generated_at="2026-04-21T09:01:05",
            app_name="Stock Chart Helper",
            debug=False,
            kis=kis,
            cache={"backend": "redis", "redis_available": True, "memory_fallback_entries": 0},
            intraday_store={"path": "data/intraday_cache.sqlite3", "retention_days": 45, "total_rows": 120, "symbol_count": 1},
            scheduler_enabled=True,
        )
        assert payload.kis.last_prime is not None
        assert payload.kis.last_prime.symbol == "005930"
