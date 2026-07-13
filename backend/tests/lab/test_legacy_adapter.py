import pandas as pd

from app.strategies.legacy_patterns import LegacyPatternStrategy


def _trending_bars(periods: int = 300) -> pd.DataFrame:
    """패턴이 나올 수 있는 변동 있는 합성 시세 (결정적)."""
    import numpy as np

    rng = np.random.default_rng(3)
    dates = pd.bdate_range("2023-01-02", periods=periods)
    close = 10_000 * np.cumprod(1 + rng.normal(0.0005, 0.015, periods))
    rows = []
    for i, d in enumerate(dates):
        c = float(close[i])
        rows.append({
            "date": d, "open": c * 0.995, "high": c * 1.01, "low": c * 0.985,
            "close": c, "volume": 1_000_000,
        })
    return pd.DataFrame(rows)


class TestLegacyAdapter:
    def test_interface(self):
        s = LegacyPatternStrategy()
        assert s.id == "legacy_patterns"
        assert s.fit({"A": _trending_bars(150)}) == {}  # 파라미터 학습 없음 (고정 규칙)

    def test_signals_are_long_only_with_valid_geometry(self):
        s = LegacyPatternStrategy()
        bars = _trending_bars()
        signals = s.signals("A", bars, params={})
        closes = {pd.Timestamp(r["date"]).date(): float(r["close"]) for _, r in bars.iterrows()}
        for sig in signals:
            close = closes[sig.signal_date]
            assert sig.stop_price < close  # 롱: 손절은 아래
            if sig.target_price is not None:
                assert sig.target_price > close  # 목표는 위 (퇴화 케이스 없음)

    def test_no_lookahead_truncation_consistency(self):
        # 시계열을 앞부분만 잘라 넣어도, 그 구간의 신호는 전체 넣었을 때와 같아야 한다
        s = LegacyPatternStrategy()
        full = _trending_bars(300)
        cut = full.iloc[:200].reset_index(drop=True)
        cutoff = pd.Timestamp(cut["date"].max()).date()
        sig_cut = {(x.signal_date, round(x.stop_price, 2)) for x in s.signals("A", cut, {})}
        sig_full = {
            (x.signal_date, round(x.stop_price, 2))
            for x in s.signals("A", full, {})
            if x.signal_date <= cutoff
        }
        assert sig_cut == sig_full
