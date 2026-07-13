from datetime import date

from app.lab.metrics import bootstrap_ci, decide_verdict, summarize
from app.lab.types import Trade


def _trade(net: float, exit_day: int = 1) -> Trade:
    return Trade(
        code="A", strategy_id="t",
        entry_date=date(2025, 1, 1), entry_price=100.0,
        exit_date=date(2025, 1, 1 + exit_day), exit_price=100.0 * (1 + net),
        exit_reason="time", gross_return_pct=net, net_return_pct=net,
    )


class TestSummarize:
    def test_empty_trades(self):
        s = summarize([])
        assert s.n == 0 and s.ev_pct == 0.0

    def test_ev_win_rate_payoff(self):
        trades = [_trade(0.10), _trade(0.10), _trade(-0.05), _trade(-0.05)]
        s = summarize(trades)
        assert s.n == 4
        assert abs(s.ev_pct - 0.025) < 1e-12
        assert abs(s.win_rate - 0.5) < 1e-12
        assert abs(s.payoff_ratio - 2.0) < 1e-12  # 평균이익 0.10 / 평균손실 0.05

    def test_mdd_from_sequential_equity(self):
        # +10% → -20% → +5%: 고점 1.10에서 0.88까지 → MDD = 20%
        trades = [_trade(0.10, 1), _trade(-0.20, 2), _trade(0.05, 3)]
        s = summarize(trades)
        assert abs(s.mdd_pct - 0.20) < 1e-9


class TestBootstrap:
    def test_deterministic_with_seed(self):
        values = [0.01, -0.02, 0.03, 0.01, -0.01] * 10
        assert bootstrap_ci(values, seed=42) == bootstrap_ci(values, seed=42)

    def test_ci_contains_mean_for_reasonable_sample(self):
        values = [0.01] * 50 + [-0.005] * 50
        lo, hi = bootstrap_ci(values, seed=1)
        mean = sum(values) / len(values)
        assert lo <= mean <= hi

    def test_tight_positive_sample_excludes_zero(self):
        lo, _ = bootstrap_ci([0.01] * 100, seed=1)
        assert lo > 0


class TestVerdict:
    def test_fail_when_ev_not_positive(self):
        assert decide_verdict(ev_pct=-0.001, ci_low=-0.01, random_ev_pct=0.0) == "fail"
        assert decide_verdict(ev_pct=0.0, ci_low=-0.01, random_ev_pct=0.0) == "fail"

    def test_pass_needs_ci_above_zero_and_beats_random(self):
        assert decide_verdict(ev_pct=0.01, ci_low=0.002, random_ev_pct=0.001) == "pass"

    def test_watch_when_ci_includes_zero(self):
        assert decide_verdict(ev_pct=0.01, ci_low=-0.001, random_ev_pct=0.0) == "watch"

    def test_watch_when_random_not_beaten(self):
        assert decide_verdict(ev_pct=0.01, ci_low=0.002, random_ev_pct=0.02) == "watch"

    def test_random_none_means_only_ci_gate(self):
        assert decide_verdict(ev_pct=0.01, ci_low=0.002, random_ev_pct=None) == "pass"
