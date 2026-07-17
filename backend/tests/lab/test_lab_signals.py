from datetime import date

import pandas as pd

from app.lab.types import Signal
from app.services.lab_signals import apply_drift_demotions, collect_recent_signals, eligible_strategy_ids


class _StubStrategy:
    id = "stub"
    label = "스텁 전략"

    def __init__(self, signals: list[Signal]):
        self._signals = signals

    def fit(self, train_bars):
        return {}

    def signals(self, code, bars, params):
        return [s for s in self._signals if s.code == code]


class TestEligibleStrategyIds:
    def test_pass_and_watch_only_ordered_by_verdict(self):
        reports = [
            {"strategy": "a", "verdict": "watch", "ev_pct": 0.02},
            {"strategy": "b", "verdict": "pass", "ev_pct": 0.05},
            {"strategy": "c", "verdict": "fail", "ev_pct": -0.01},
        ]
        assert eligible_strategy_ids(reports) == ["b", "a"]  # pass 먼저, fail 제외

    def test_custom_allowed_verdicts(self):
        reports = [
            {"strategy": "b", "verdict": "pass", "ev_pct": 0.05},
            {"strategy": "a", "verdict": "watch", "ev_pct": 0.02},
        ]
        assert eligible_strategy_ids(reports, allowed={"pass"}) == ["b"]

    def test_empty(self):
        assert eligible_strategy_ids([]) == []


class TestCollectRecentSignals:
    def _bars(self, code: str) -> pd.DataFrame:
        dates = pd.bdate_range("2026-06-01", periods=20)
        return pd.DataFrame([
            {"date": d, "open": 100, "high": 101, "low": 99, "close": 100, "volume": 1_000}
            for d in dates
        ]).assign(code=code)

    def test_keeps_only_signals_within_lookback(self):
        as_of = date(2026, 6, 26)  # 마지막 영업일 근처
        recent = Signal(code="A", signal_date=date(2026, 6, 25), stop_price=95.0)
        old = Signal(code="A", signal_date=date(2026, 6, 2), stop_price=95.0)
        strat = _StubStrategy([recent, old])
        out = collect_recent_signals(strat, {"A": self._bars("A")}, as_of=as_of, lookback_days=5)
        assert len(out) == 1
        assert out[0]["signal_date"] == "2026-06-25"
        assert out[0]["strategy_id"] == "stub"
        assert out[0]["code"] == "A"
        # 포지션 사이징용 기준가 — 신호일 종가 (진입가=다음날 시가의 근사)
        assert out[0]["reference_price"] == 100.0

    def test_dedupes_same_code_keeping_recent_then_tightest_stop(self):
        # 같은 종목이 여러 패턴으로 잡혀도 화면엔 1개만 — 최신 신호일 우선,
        # 동률이면 가장 타이트한(높은) 손절을 남긴다 (구매자 중복 피로감 방지)
        as_of = date(2026, 6, 26)
        sigs = [
            Signal(code="A", signal_date=date(2026, 6, 24), stop_price=95.0),  # 오래됨
            Signal(code="A", signal_date=date(2026, 6, 25), stop_price=96.0),  # 최신, 손절 96
            Signal(code="A", signal_date=date(2026, 6, 25), stop_price=97.0),  # 최신, 손절 97(더 타이트)
        ]
        strat = _StubStrategy(sigs)
        out = collect_recent_signals(strat, {"A": self._bars("A")}, as_of=as_of, lookback_days=5)
        assert len(out) == 1
        assert out[0]["signal_date"] == "2026-06-25"
        assert out[0]["stop_price"] == 97.0

    def test_multiple_codes(self):
        as_of = date(2026, 6, 26)
        sigs = [
            Signal(code="A", signal_date=date(2026, 6, 25), stop_price=95.0),
            Signal(code="B", signal_date=date(2026, 6, 24), stop_price=90.0),
        ]
        strat = _StubStrategy(sigs)
        bars = {"A": self._bars("A"), "B": self._bars("B")}
        out = collect_recent_signals(strat, bars, as_of=as_of, lookback_days=5)
        assert {o["code"] for o in out} == {"A", "B"}

    def test_no_recent_signals(self):
        as_of = date(2026, 6, 26)
        old = Signal(code="A", signal_date=date(2026, 6, 1), stop_price=95.0)
        strat = _StubStrategy([old])
        out = collect_recent_signals(strat, {"A": self._bars("A")}, as_of=as_of, lookback_days=5)
        assert out == []


class TestApplyDriftDemotions:
    def _reports(self):
        return [
            {"strategy": "a", "label": "전략A", "verdict": "pass", "ev_pct": 0.05},
            {"strategy": "b", "label": "전략B", "verdict": "pass", "ev_pct": 0.03},
            {"strategy": "c", "label": "전략C", "verdict": "watch", "ev_pct": 0.01},
        ]

    def test_no_paper_state_changes_nothing(self):
        adjusted, demotions = apply_drift_demotions(self._reports(), {})
        assert [r["verdict"] for r in adjusted] == ["pass", "pass", "watch"]
        assert demotions == []

    def test_drifting_positive_demotes_to_watch(self):
        state = {"a": {"drift": "drifting", "realized_ev_pct": 0.004}}
        adjusted, demotions = apply_drift_demotions(self._reports(), state)
        assert adjusted[0]["verdict"] == "watch"
        assert demotions == [{
            "strategy_id": "a", "label": "전략A", "from": "pass", "to": "watch",
            "reason": "실측 이탈 — 관찰 강등",
        }]

    def test_drifting_loss_excludes_from_eligible(self):
        state = {"b": {"drift": "drifting", "realized_ev_pct": -0.002}}
        adjusted, demotions = apply_drift_demotions(self._reports(), state)
        assert demotions[0]["to"] == "fail"
        assert "b" not in eligible_strategy_ids(adjusted)

    def test_original_reports_not_mutated(self):
        reports = self._reports()
        apply_drift_demotions(reports, {"a": {"drift": "drifting", "realized_ev_pct": -1.0}})
        assert reports[0]["verdict"] == "pass"
