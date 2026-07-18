from datetime import date, timedelta

import pandas as pd

from app.lab.regime_gate import RegimeGatedStrategy, build_regime_lookup
from app.lab.types import Signal


def _index_bars(closes: list[float], start: str = "2020-01-01") -> pd.DataFrame:
    dates = pd.bdate_range(start, periods=len(closes))
    return pd.DataFrame({"date": dates.date, "close": closes})


class TestBuildRegimeLookup:
    def test_above_ma_is_ok_below_is_blocked(self):
        # 100봉 상승 후 급락 — 상승 구간 끝은 MA 위(ok), 급락 끝은 MA 아래(blocked)
        closes = [100 + i for i in range(100)] + [50.0] * 30
        lookup = build_regime_lookup(_index_bars(closes), ma_window=50)
        dates = pd.bdate_range("2020-01-01", periods=130).date
        assert lookup(dates[99]) is True    # 상승 정점 — 종가 199 > MA50
        assert lookup(dates[129]) is False  # 급락 후 — 종가 50 < MA50

    def test_uses_last_known_index_date_for_gaps(self):
        # 지수 달력에 없는 날(주말 등)은 직전 지수일 기준으로 판정
        closes = [100 + i for i in range(60)]
        lookup = build_regime_lookup(_index_bars(closes), ma_window=50)
        last = pd.bdate_range("2020-01-01", periods=60).date[-1]
        weekend = last + timedelta(days=1)
        assert lookup(weekend) is True

    def test_before_warmup_is_blocked(self):
        # MA를 만들 이력이 없으면 보수적으로 차단 (모르면 안 산다)
        closes = [100 + i for i in range(60)]
        lookup = build_regime_lookup(_index_bars(closes), ma_window=50)
        assert lookup(date(2019, 12, 1)) is False


class _StubStrategy:
    id = "stub"
    label = "스텁"
    causal_signals = True

    def fit(self, train_bars):
        return {"fitted": True}

    def signals(self, code, bars, params):
        return [
            Signal(code=code, signal_date=date(2020, 6, 1), stop_price=90.0),
            Signal(code=code, signal_date=date(2020, 7, 1), stop_price=91.0),
        ]

    def panel_signals(self, bars_by_code, params):
        return [Signal(code=c, signal_date=date(2020, 6, 1), stop_price=90.0) for c in sorted(bars_by_code)]


class TestRegimeGatedStrategy:
    def _gated(self, ok_dates: set[date]) -> RegimeGatedStrategy:
        return RegimeGatedStrategy(_StubStrategy(), lambda d: d in ok_dates)

    def test_filters_signals_outside_regime(self):
        gated = self._gated({date(2020, 6, 1)})
        out = gated.signals("A", pd.DataFrame(), {})
        assert [s.signal_date for s in out] == [date(2020, 6, 1)]

    def test_panel_signals_filtered_too(self):
        gated = self._gated(set())
        assert gated.panel_signals({"A": pd.DataFrame()}, {}) == []

    def test_metadata_passthrough(self):
        gated = self._gated(set())
        assert gated.causal_signals is True
        assert gated.id == "stub"          # 리포트 비교를 위해 id는 유지
        assert "체제" in gated.label        # 라벨로만 구분
        assert gated.fit({}) == {"fitted": True}

    def test_non_panel_inner_does_not_expose_panel_path(self):
        # 하네스가 hasattr로 경로를 고르므로, 원본에 panel_signals가 없으면
        # 래퍼도 노출하면 안 된다 (없으면 종목 단위 경로로 가야 함)
        class _PerCodeOnly:
            id = "percode"
            label = "종목단위"

            def fit(self, train_bars):
                return {}

            def signals(self, code, bars, params):
                return []

        gated = RegimeGatedStrategy(_PerCodeOnly(), lambda d: True)
        assert not hasattr(gated, "panel_signals")
