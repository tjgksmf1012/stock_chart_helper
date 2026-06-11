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
