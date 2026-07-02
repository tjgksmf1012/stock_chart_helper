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


@pytest.fixture(autouse=True)
def _neutral_market_regime(monkeypatch):
    # analyze_symbol_dataframe() now calls get_market_regime() for real (regime_fit/rs_fit
    # used to be dead-wired to a hardcoded 0.5). Pin it to "unknown" so this pinned
    # characterization test doesn't silently drift if a real regime happens to be cached
    # in Redis by something else (e.g. a manually-run dev server sharing the same instance).
    async def _fixed_regime():
        return {
            "kospi": {"regime": "unknown", "return_63d_pct": None},
            "kosdaq": {"regime": "unknown", "return_63d_pct": None},
            "overall_regime": "unknown",
        }

    monkeypatch.setattr("app.services.analysis_service.get_market_regime", _fixed_regime)


def _stale_double_bottom_df() -> pd.DataFrame:
    """Same W as `_double_bottom_df` but followed by a ~70-bar flat tail.

    The second low ends >45 bars before the last bar, so for the 1d timeframe
    the pattern's last structural point is past the stale cutoff.
    The tail stays between neckline (9,000) and target (10,000) so the pattern
    would otherwise remain "confirmed" (not played_out / invalidated).
    """
    rng = np.random.default_rng(0)
    closes = (
        list(np.linspace(10_000, 9_000, 30))
        + list(np.linspace(9_000, 8_000, 15))
        + list(np.linspace(8_000, 9_000, 15))
        + list(np.linspace(9_000, 8_050, 15))
        + list(np.linspace(8_050, 9_400, 20))
        + [9_400 + float(rng.normal(0, 12)) for _ in range(70)]
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
    # 0.326 -> 0.334 after pattern_engine stopped demoting "confirmed" patterns to
    # "armed"/"forming" on low secondary fits (stale-pattern fix). Intentional.
    assert result.entry_score == 0.334
    # 0.48 -> 0.42: same pattern-demotion removal keeps the setup "confirmed" with
    # weak secondary fits, which trips the confirmed+low-quality risk penalty.
    assert result.trade_readiness_score == 0.42


def _old_breakout_double_bottom_df() -> pd.DataFrame:
    """W 패턴 구조는 stale 한도(45봉) 이내지만, 돌파가 30봉 전에 일어나
    이미 반응 구간이 끝난 케이스. 가격은 넥라인(9,000) 위 ~ 목표(10,000) 아래에서
    횡보해 played_out/invalidated 없이 'confirmed'로 남아 있다.
    """
    rng = np.random.default_rng(0)
    closes = (
        list(np.linspace(10_000, 9_000, 30))
        + list(np.linspace(9_000, 8_000, 15))
        + list(np.linspace(8_000, 9_000, 15))
        + list(np.linspace(9_000, 8_050, 15))
        + list(np.linspace(8_050, 9_400, 10))   # 돌파 랠리 (bar ~82에서 넥라인 상향 돌파)
        + [9_350 + float(rng.normal(0, 12)) for _ in range(28)]  # 돌파 후 28봉 횡보
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


@pytest.mark.anyio
async def test_old_breakout_pattern_is_dropped(monkeypatch):
    """돌파(트리거)가 okay 한도(일봉 20봉)보다 오래 지난 confirmed 패턴은 제외.

    구조 나이만 보면 한도 이내라도, 트리거 이후 반응 구간이 끝났으면
    '오늘까지 이어지는' 셋업이 아니므로 노출하지 않는다.
    """
    monkeypatch.setattr("app.services.analysis_service.get_pattern_stats", _fixed_stats)

    symbol = SymbolInfo(
        code="005930",
        name="Test",
        market="KOSPI",
        sector=None,
        market_cap=1e12,
        is_in_universe=True,
    )
    result = await analyze_symbol_dataframe(symbol, "1d", _old_breakout_double_bottom_df())

    assert result.no_signal_flag is True
    assert result.patterns == []


def _wide_span_double_bottom_df() -> pd.DataFrame:
    """저점 간격이 50봉인 늘어진 W. 신선하고(구조 나이 ~1봉) 돌파 전이지만,
    이중 바닥 저점 간격이 교과서 범위(2~6주 ≈ 30봉)를 한참 벗어난 구조다."""
    rng = np.random.default_rng(0)
    closes = (
        list(np.linspace(10_000, 9_000, 30))
        + list(np.linspace(9_000, 8_000, 15))
        + list(np.linspace(8_000, 9_000, 25))   # 느린 반등 (저점 간격을 벌림)
        + list(np.linspace(9_000, 8_050, 25))   # 두 번째 저점이 첫 저점 50봉 뒤
        + list(np.linspace(8_050, 8_900, 12))   # 넥라인 직전까지 회복 (돌파 전, 신선)
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


def _boundary_span_double_top_df() -> pd.DataFrame:
    """고점 간격이 정확히 30봉(=6주 교과서 상한)인 이중 천장.

    경계 포함 규칙(>=)으로 제외돼야 한다 — 기업은행 M 케이스 회귀 방지.
    돌파 전(고점2가 넥라인 위 유지)이라 다른 신선도 필터는 통과한다.
    """
    rng = np.random.default_rng(1)
    closes = (
        list(np.linspace(8_000, 10_000, 12))   # 첫 상승 (고점1 ~index 11)
        + list(np.linspace(10_000, 9_200, 8))  # 고점1 후 하락 (넥라인 ~9,200)
        + list(np.linspace(9_200, 9_900, 23))  # 두 번째 봉우리로 (고점1과 ~30봉 간격)
        + list(np.linspace(9_900, 9_400, 6))   # 고점2 후 소폭 하락 (넥라인 위 유지)
    )
    dates = pd.bdate_range("2023-01-02", periods=len(closes))
    rows = []
    for dt, close in zip(dates, closes):
        open_px = close * (1 + rng.normal(0, 0.002))
        high = max(open_px, close) * (1 + abs(rng.normal(0, 0.003)))
        low = min(open_px, close) * (1 - abs(rng.normal(0, 0.003)))
        rows.append(
            {"date": dt, "open": round(open_px), "high": round(high),
             "low": round(low), "close": round(close), "volume": 1_000_000}
        )
    return pd.DataFrame(rows)


@pytest.mark.anyio
async def test_boundary_30bar_double_top_is_dropped(monkeypatch):
    """고점 간격 정확히 30봉인 이중 천장은 경계 포함 규칙으로 제외 (기업은행 M 회귀)."""
    monkeypatch.setattr("app.services.analysis_service.get_pattern_stats", _fixed_stats)
    symbol = SymbolInfo(code="005930", name="Test", market="KOSPI", sector=None,
                        market_cap=1e12, is_in_universe=True)
    result = await analyze_symbol_dataframe(symbol, "1d", _boundary_span_double_top_df())
    assert all(p.pattern_type != "double_top" for p in result.patterns)


@pytest.mark.anyio
async def test_wide_formation_span_pattern_is_dropped(monkeypatch):
    """이중 바닥/천장의 구조 포인트 간격이 한도(일봉 30봉)를 넘으면 제외.

    신선도(구조 나이·트리거 나이)와 별개로, 몇 달에 걸쳐 느슨하게 그려진
    구조는 교과서 패턴으로 보지 않는다.
    """
    monkeypatch.setattr("app.services.analysis_service.get_pattern_stats", _fixed_stats)

    symbol = SymbolInfo(
        code="005930",
        name="Test",
        market="KOSPI",
        sector=None,
        market_cap=1e12,
        is_in_universe=True,
    )
    result = await analyze_symbol_dataframe(symbol, "1d", _wide_span_double_bottom_df())

    assert all(p.pattern_type != "double_bottom" for p in result.patterns)


def _spent_pullback_double_bottom_df() -> pd.DataFrame:
    """돌파가 한참 전에 일어났고, 이후 가격이 넥라인 아래로 되돌아온 케이스.

    현재가가 넥라인(9,000) 아래라 상태는 다시 forming/armed('재돌파 대기')로
    읽히지만, 첫 돌파(bar ~81)가 okay 한도(20봉)보다 오래돼 이미 에너지를 쓴
    패턴이다. 상태와 무관하게 제외돼야 한다.
    """
    rng = np.random.default_rng(0)
    closes = (
        list(np.linspace(10_000, 9_000, 30))
        + list(np.linspace(9_000, 8_000, 15))
        + list(np.linspace(8_000, 9_000, 15))
        + list(np.linspace(9_000, 8_050, 15))
        + list(np.linspace(8_050, 9_250, 10))   # 돌파 랠리 — 넥라인(~9,020)은 넘되 목표가 미달
        + list(np.linspace(9_250, 8_600, 10))   # 넥라인 한참 아래로 되돌림 (armed 버퍼 밖 → forming)
        + [8_600 + float(rng.normal(0, 12)) for _ in range(25)]  # 넥라인 아래 횡보
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


@pytest.mark.anyio
async def test_spent_pullback_pattern_is_dropped(monkeypatch):
    """돌파 후 넥라인 아래로 되돌아온 패턴: 상태가 forming/armed로 읽혀도
    첫 돌파가 okay 한도보다 오래됐으면 '재돌파 대기'로 재노출하지 않는다."""
    monkeypatch.setattr("app.services.analysis_service.get_pattern_stats", _fixed_stats)

    symbol = SymbolInfo(
        code="005930",
        name="Test",
        market="KOSPI",
        sector=None,
        market_cap=1e12,
        is_in_universe=True,
    )
    result = await analyze_symbol_dataframe(symbol, "1d", _spent_pullback_double_bottom_df())

    assert all(p.pattern_type != "double_bottom" for p in result.patterns)


@pytest.mark.anyio
async def test_stale_pattern_is_dropped(monkeypatch):
    """마지막 구조 포인트가 stale 한도(일봉 45봉)를 넘긴 패턴은 분석에서 제외돼야 한다.

    감점만 하고 목록에 남기면 차트·대시보드에 수개월 전 패턴이 계속 노출된다.
    """
    monkeypatch.setattr("app.services.analysis_service.get_pattern_stats", _fixed_stats)

    symbol = SymbolInfo(
        code="005930",
        name="Test",
        market="KOSPI",
        sector=None,
        market_cap=1e12,
        is_in_universe=True,
    )
    result = await analyze_symbol_dataframe(symbol, "1d", _stale_double_bottom_df())

    assert result.no_signal_flag is True
    assert result.patterns == []
