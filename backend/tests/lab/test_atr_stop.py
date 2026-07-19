from datetime import date

import pandas as pd

from app.lab.atr_stop import AtrStopStrategy, compute_atr
from app.lab.types import Signal


def make_bars(n: int, spread: float = 2.0, start: str = "2023-01-02") -> pd.DataFrame:
    """종가 100 고정, 고저 폭 spread — TR이 정확히 spread인 합성 봉."""
    dates = pd.bdate_range(start, periods=n)
    return pd.DataFrame({
        "date": dates.date,
        "open": [100.0] * n,
        "high": [100.0 + spread / 2] * n,
        "low": [100.0 - spread / 2] * n,
        "close": [100.0] * n,
        "volume": [1000] * n,
    })


class TestComputeAtr:
    def test_constant_range_atr_equals_range(self):
        bars = make_bars(60, spread=2.0)
        atr = compute_atr(bars, window=20)
        assert abs(atr.iloc[-1] - 2.0) < 1e-9

    def test_warmup_is_nan(self):
        bars = make_bars(10, spread=2.0)
        atr = compute_atr(bars, window=20)
        assert atr.isna().all()

    def test_gap_included_in_true_range(self):
        # 갭 상승: TR은 고저폭이 아니라 전일 종가 대비 거리를 포함해야 한다
        bars = make_bars(30, spread=2.0)
        bars.loc[29, ["open", "high", "low", "close"]] = [110.0, 111.0, 109.0, 110.0]
        atr = compute_atr(bars, window=20)
        # 마지막 봉 TR = max(2, |111-100|, |109-100|) = 11 → ATR이 2보다 커야 함
        assert atr.iloc[-1] > 2.0


class _FixedStopStrategy:
    id = "fixed"
    label = "고정 손절"
    causal_signals = True

    def fit(self, train_bars):
        return {}

    def signals(self, code, bars, params):
        dates = pd.to_datetime(bars["date"]).dt.date.tolist()
        # 마지막 봉에서 고정 15% 손절 신호
        return [Signal(code=code, signal_date=dates[-1], stop_price=85.0, max_holding_days=40)]


class TestAtrStopStrategy:
    def test_replaces_stop_with_atr_multiple(self):
        bars = make_bars(60, spread=2.0)
        wrapped = AtrStopStrategy(_FixedStopStrategy(), atr_window=20, atr_mult=2.5)
        out = wrapped.signals("A", bars, {})
        # 종가 100, ATR 2.0 → 손절 100 − 2.5×2 = 95.0 (고정 85 대체)
        assert len(out) == 1
        assert abs(out[0].stop_price - 95.0) < 1e-9
        assert out[0].max_holding_days == 40  # 손절 외에는 불변

    def test_keeps_original_stop_when_atr_unavailable(self):
        bars = make_bars(10, spread=2.0)  # ATR 워밍업 부족
        wrapped = AtrStopStrategy(_FixedStopStrategy(), atr_window=20, atr_mult=2.5)
        out = wrapped.signals("A", bars, {})
        assert out[0].stop_price == 85.0

    def test_metadata_passthrough(self):
        wrapped = AtrStopStrategy(_FixedStopStrategy())
        assert wrapped.id == "fixed"
        assert "ATR" in wrapped.label
        assert wrapped.causal_signals is True
        assert not hasattr(wrapped, "panel_signals")  # 원본에 없으면 노출 금지

    def test_panel_strategy_stops_replaced_per_code(self):
        class _PanelFixed(_FixedStopStrategy):
            def panel_signals(self, bars_by_code, params):
                out = []
                for code, bars in sorted(bars_by_code.items()):
                    d = pd.to_datetime(bars["date"]).dt.date.iloc[-1]
                    out.append(Signal(code=code, signal_date=d, stop_price=85.0))
                return out

        panel = {"WIDE": make_bars(60, spread=4.0), "NARROW": make_bars(60, spread=1.0)}
        wrapped = AtrStopStrategy(_PanelFixed(), atr_window=20, atr_mult=2.5)
        by_code = {s.code: s for s in wrapped.panel_signals(panel, {})}
        assert abs(by_code["WIDE"].stop_price - 90.0) < 1e-9    # 100 − 2.5×4
        assert abs(by_code["NARROW"].stop_price - 97.5) < 1e-9  # 100 − 2.5×1
