"""PR #11(스캔 취소 + 데이터 소스 장애 감지) 회귀 테스트.

request_scan_cancel()이 실제로 run_scan()의 배치 루프를 조기 종료시키고 부분
결과를 저장하는지, FDR 서킷브레이커가 실제로 반복 실패 후 호출을 건너뛰는지,
_fetch_universe_codes()가 한쪽 시장만 실패해도 다른 쪽 결과는 살리는지를
검증한다 -- 세 가지 모두 PR 설명이 주장하는 핵심 동작이라 실제로 그렇게
동작하는지 직접 실행해서 확인한다.
"""
from __future__ import annotations

import pandas as pd
import pytest

import app.core.redis as cache
import app.services.data_fetcher as data_fetcher_module
import app.services.scanner as scanner_module
from app.services.data_fetcher import KRXDataFetcher, fdr_in_cooldown, mark_fdr_cooldown
from app.services.scanner import _scan_status, request_scan_cancel
from tests.test_data_fetcher_live_intraday import FakeKIS, FakeToss, FakeIntradayStore


@pytest.fixture(autouse=True)
def _reset_mem_cache(monkeypatch):
    monkeypatch.setattr(cache, "_mem_cache", {})

    async def _no_redis():
        return None

    monkeypatch.setattr(cache, "_try_get_redis", _no_redis)


@pytest.fixture(autouse=True)
def _reset_scan_status():
    _scan_status.clear()
    yield
    _scan_status.clear()


class TestRequestScanCancel:
    def test_returns_false_when_no_scan_recorded(self):
        assert request_scan_cancel("1d") is False

    def test_returns_false_when_scan_exists_but_not_running(self):
        _scan_status["1d"] = {"is_running": False, "cancel_requested": False}
        assert request_scan_cancel("1d") is False
        assert _scan_status["1d"]["cancel_requested"] is False

    def test_sets_flag_and_returns_true_when_running(self):
        _scan_status["1d"] = {"is_running": True, "cancel_requested": False}
        assert request_scan_cancel("1d") is True
        assert _scan_status["1d"]["cancel_requested"] is True

    def test_does_not_affect_other_timeframes(self):
        _scan_status["1d"] = {"is_running": True, "cancel_requested": False}
        _scan_status["1wk"] = {"is_running": True, "cancel_requested": False}
        request_scan_cancel("1d")
        assert _scan_status["1d"]["cancel_requested"] is True
        assert _scan_status["1wk"]["cancel_requested"] is False


class TestRunScanHonorsCancellation:
    """run_scan()의 진짜 배치 루프를 돌려서, 취소 요청이 다음 배치 시작 전에
    반영되어 이미 처리된 부분 결과만 저장되고 나머지 종목은 건너뛰는지 확인한다.
    request_scan_cancel()이 플래그만 세우고 실제로는 아무 효과가 없는 상황을
    잡아내기 위한 엔드투엔드 성격의 테스트다.
    """

    @pytest.mark.anyio
    async def test_cancel_mid_scan_stops_early_and_saves_partial_results(self, monkeypatch):
        universe = [(f"{i:06d}", f"Stock{i}", "KOSPI") for i in range(6)]

        async def _fake_select_candidates(limit, timeframe):
            return universe, "test_source", set(), "neutral"

        call_log: list[str] = []

        async def _fake_analyze_one(code, name, market, timeframe, *, force_refresh, allow_live_intraday):
            call_log.append(code)
            if len(call_log) == 2:
                # 첫 배치(2종목)가 처리되는 도중 사용자가 취소를 누른 상황을 재현.
                request_scan_cancel(timeframe)
            return {"code": code, "name": name, "no_signal_flag": True}

        async def _fake_persist_scan_history(**kwargs):
            return None

        monkeypatch.setattr(scanner_module, "_select_candidates", _fake_select_candidates)
        monkeypatch.setattr(scanner_module, "_analyze_one", _fake_analyze_one)
        monkeypatch.setattr(scanner_module, "persist_scan_history", _fake_persist_scan_history)

        results = await scanner_module.run_scan(
            timeframe="1wk", limit=6, batch_size=2, force_refresh=True, source="manual",
        )

        # 취소가 반영됐다면 3배치(6종목) 전부가 아니라 첫 배치(2종목)만 처리되고 멈춰야 한다.
        assert len(call_log) == 2
        assert len(results) == 2
        assert {row["code"] for row in results} == {"000000", "000001"}

        status = _scan_status["1wk"]
        assert status["is_running"] is False
        assert status["scanned_count"] == 2

    @pytest.mark.anyio
    async def test_without_cancellation_all_batches_run(self, monkeypatch):
        universe = [(f"{i:06d}", f"Stock{i}", "KOSPI") for i in range(6)]

        async def _fake_select_candidates(limit, timeframe):
            return universe, "test_source", set(), "neutral"

        call_log: list[str] = []

        async def _fake_analyze_one(code, name, market, timeframe, *, force_refresh, allow_live_intraday):
            call_log.append(code)
            return {"code": code, "name": name, "no_signal_flag": True}

        async def _fake_persist_scan_history(**kwargs):
            return None

        monkeypatch.setattr(scanner_module, "_select_candidates", _fake_select_candidates)
        monkeypatch.setattr(scanner_module, "_analyze_one", _fake_analyze_one)
        monkeypatch.setattr(scanner_module, "persist_scan_history", _fake_persist_scan_history)

        results = await scanner_module.run_scan(
            timeframe="1wk", limit=6, batch_size=2, force_refresh=True, source="manual",
        )

        assert len(call_log) == 6
        assert len(results) == 6


class TestFdrCircuitBreaker:
    """FDR(FinanceDataReader)이 반복 실패하면 다음 요청부터는 실제 호출 없이
    즉시 건너뛰는지 확인한다 -- krx_in_cooldown()과 짝을 이루는 새 서킷브레이커.
    """

    @pytest.mark.anyio
    async def test_not_in_cooldown_initially(self):
        assert await fdr_in_cooldown() is False

    @pytest.mark.anyio
    async def test_mark_cooldown_makes_it_active(self):
        await mark_fdr_cooldown("boom")
        assert await fdr_in_cooldown() is True

    @pytest.mark.anyio
    async def test_fdr_fallback_marks_cooldown_on_failure_and_skips_next_call(self, monkeypatch):
        fetcher = KRXDataFetcher(
            kis_client=FakeKIS(configured=False), toss_client=FakeToss(configured=False),
        )
        monkeypatch.setattr(data_fetcher_module, "get_intraday_store", lambda: FakeIntradayStore())

        call_count = 0

        class _FakeFdrModule:
            @staticmethod
            def DataReader(code, start, end):
                nonlocal call_count
                call_count += 1
                raise RuntimeError("network down")

        import sys

        monkeypatch.setitem(sys.modules, "FinanceDataReader", _FakeFdrModule())

        import datetime as dt

        start, end = dt.date(2026, 1, 1), dt.date(2026, 1, 31)

        first = await fetcher._fdr_fallback("005930", start, end)
        assert first.empty
        assert first.attrs["fetch_status"] == "daily_error"
        assert call_count == 1
        assert await fdr_in_cooldown() is True

        # 두 번째 호출은 쿨다운 중이라 FinanceDataReader.DataReader를 아예 안 불러야 한다.
        second = await fetcher._fdr_fallback("000660", start, end)
        assert second.empty
        assert call_count == 1


class TestUniverseFetchPartialMarketFailure:
    """KOSPI/KOSDAQ 중 한쪽 조회가 실패해도 다른 쪽 결과는 살아남는지 확인한다
    -- 이전엔 한쪽만 실패해도 전체 유니버스 조회가 raise 하나로 통째로 죽었다.
    """

    def _fake_universe_df(self) -> pd.DataFrame:
        return pd.DataFrame(
            [{"code": "035720", "name": "Kakao", "market": "KOSDAQ", "market_cap": None}]
        )

    @pytest.mark.anyio
    async def test_kospi_failure_does_not_discard_kosdaq_results(self, monkeypatch):
        class _FakeFetcher:
            async def get_universe(self):
                return self._df

        fetcher = _FakeFetcher()
        fetcher._df = self._fake_universe_df()
        monkeypatch.setattr(scanner_module, "get_data_fetcher", lambda: fetcher)

        def _fake_get_market_cap_by_ticker(date_str, market=None):
            if market == "KOSPI":
                raise RuntimeError("kospi endpoint boom")
            return pd.DataFrame({"시가총액": [1_000_000_000_000], "거래대금": [0]}, index=["035720"])

        monkeypatch.setattr("pykrx.stock.get_market_cap_by_ticker", _fake_get_market_cap_by_ticker)

        codes, source = await scanner_module._fetch_universe_codes(limit=10)

        assert source == "krx_universe"
        assert any(code == "035720" for code, _, _ in codes)

    @pytest.mark.anyio
    async def test_both_markets_failing_falls_back_without_crashing(self, monkeypatch):
        class _FakeFetcher:
            async def get_universe(self):
                return self._df

        fetcher = _FakeFetcher()
        fetcher._df = self._fake_universe_df()
        monkeypatch.setattr(scanner_module, "get_data_fetcher", lambda: fetcher)

        def _fake_get_market_cap_by_ticker(date_str, market=None):
            raise RuntimeError(f"{market} endpoint boom")

        monkeypatch.setattr("pykrx.stock.get_market_cap_by_ticker", _fake_get_market_cap_by_ticker)

        # 아래로 떨어지지 않고(raise 전파 없이) FDR 유니버스 폴백 경로로 넘어가야 한다.
        codes, source = await scanner_module._fetch_universe_codes(limit=10)

        assert source in {"krx_universe_fdr", "static_fallback"}
        assert await data_fetcher_module.krx_in_cooldown() is True
