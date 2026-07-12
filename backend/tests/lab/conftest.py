"""lab 테스트 공용 합성 시세 — 결정적(시드 고정)이고 날짜가 명시적이다."""
from __future__ import annotations

import pandas as pd
import pytest


def make_bars(rows: list[tuple[str, float, float, float, float]]) -> pd.DataFrame:
    """(date_str, open, high, low, close) 목록으로 bars DataFrame 생성."""
    return pd.DataFrame(
        [
            {
                "date": pd.Timestamp(d),
                "open": o,
                "high": h,
                "low": lo,
                "close": c,
                "volume": 1_000_000,
            }
            for d, o, h, lo, c in rows
        ]
    )


@pytest.fixture
def flat_bars() -> pd.DataFrame:
    """10거래일(영업일) 동안 100 부근 횡보 — 시간 청산 테스트용.

    2025-01-02(목)부터: 01-02, 01-03, 01-06, 01-07, ... (주말 제외)
    """
    dates = pd.bdate_range("2025-01-02", periods=10)
    return make_bars([(str(d.date()), 100.0, 101.0, 99.0, 100.0) for d in dates])
