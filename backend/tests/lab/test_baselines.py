from datetime import date

from app.lab.baselines import random_benchmark_signals
from app.lab.types import Signal

from .conftest import make_bars


def _bars():
    # 2025년 1월 평일만 (i%7이 4,5인 날은 토/일)
    return make_bars(
        [(f"2025-01-{i:02d}", 100.0, 101.0, 99.0, 100.0) for i in range(2, 30) if i % 7 not in (4, 5)]
    )


def _subject_signals():
    return [
        Signal(code="A", signal_date=date(2025, 1, 2), stop_price=95.0, target_price=110.0, max_holding_days=10),
        Signal(code="A", signal_date=date(2025, 1, 9), stop_price=96.0, target_price=108.0, max_holding_days=10),
    ]


class TestRandomBenchmark:
    def test_deterministic_with_seed(self):
        a = random_benchmark_signals({"A": _bars()}, _subject_signals(), n_signals=5, seed=7)
        b = random_benchmark_signals({"A": _bars()}, _subject_signals(), n_signals=5, seed=7)
        assert a == b

    def test_copies_subject_exit_geometry(self):
        # 손절/목표 % 거리와 보유일은 피검체 신호의 중앙값을 따른다 (동일 청산 근사)
        signals = random_benchmark_signals({"A": _bars()}, _subject_signals(), n_signals=3, seed=1)
        assert len(signals) == 3
        for s in signals:
            close = 100.0  # 합성 시세 종가
            assert 0.01 <= (close - s.stop_price) / close <= 0.10
            assert s.target_price is not None and s.target_price > close
            assert s.max_holding_days == 10

    def test_empty_subject_means_no_benchmark(self):
        assert random_benchmark_signals({"A": _bars()}, [], n_signals=5, seed=1) == []
