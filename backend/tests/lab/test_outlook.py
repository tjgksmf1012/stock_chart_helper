import numpy as np
import pytest

from app.lab.outlook import forward_return_quantiles, interval_coverage


def _constant_growth(n: int, rate: float = 0.01, start: float = 100.0) -> list[float]:
    return [start * (1 + rate) ** i for i in range(n)]


def _random_walk(n: int, sigma: float = 0.02, seed: int = 7) -> list[float]:
    rng = np.random.default_rng(seed)
    return (100.0 * np.cumprod(1 + rng.normal(0, sigma, n))).tolist()


class TestForwardReturnQuantiles:
    def test_constant_growth_all_quantiles_equal(self):
        closes = _constant_growth(120, rate=0.01)
        q = forward_return_quantiles(closes, horizon=5)
        expected = (1.01 ** 5) - 1
        assert q is not None
        for v in q.values():
            assert abs(v - expected) < 1e-9

    def test_quantiles_are_monotonic(self):
        q = forward_return_quantiles(_random_walk(400), horizon=20)
        assert q is not None
        assert q["q10"] <= q["q25"] <= q["q50"] <= q["q75"] <= q["q90"]

    def test_too_short_series_returns_none(self):
        assert forward_return_quantiles(_constant_growth(30), horizon=20) is None

    def test_ignores_nonpositive_prices(self):
        closes = _constant_growth(200)
        closes[50] = 0.0  # 거래정지 등 0가격 봉
        q = forward_return_quantiles(closes, horizon=5)
        assert q is not None  # 오염 표본만 빼고 계산


class TestIntervalCoverage:
    def test_deterministic_series_full_coverage(self):
        # 수익률이 일정하면 과거 분위수 == 미래 실현값 → 적중률 100%
        closes = _constant_growth(500, rate=0.005)
        cov = interval_coverage(closes, horizon=5, lookback=120)
        assert cov is not None
        assert cov["coverage"] == 1.0
        assert cov["n"] >= 20
        assert abs(cov["nominal"] - 0.8) < 1e-9

    def test_stationary_random_walk_near_nominal(self):
        # 정상성 있는 랜덤워크에서 80% 구간의 실측 적중률은 0.8 근처여야 한다
        closes = _random_walk(1500, sigma=0.015, seed=11)
        cov = interval_coverage(closes, horizon=5, lookback=252)
        assert cov is not None
        assert cov["n"] >= 50
        assert 0.6 <= cov["coverage"] <= 0.95

    def test_insufficient_data_returns_none(self):
        assert interval_coverage(_constant_growth(100), horizon=20, lookback=252) is None

    def test_no_lookahead_estimation_window(self):
        # 급변 직후 구간: 추정에 미래(급락 후) 데이터가 쓰였다면 앞 구간 적중률이
        # 왜곡된다 — 전반부(평온)의 커버리지는 전반부 데이터만으로 계산돼야 한다.
        calm = _constant_growth(400, rate=0.002)
        crash = [calm[-1] * (0.9 ** (i + 1)) for i in range(100)]  # 급락 구간
        cov_calm_only = interval_coverage(calm, horizon=5, lookback=120)
        cov_with_crash = interval_coverage(calm + crash, horizon=5, lookback=120)
        assert cov_calm_only is not None and cov_with_crash is not None
        # 평온 구간에서 잡힌 hit 수는 뒤에 급락이 붙어도 달라지지 않는다 (인과성)
        assert cov_with_crash["n"] > cov_calm_only["n"]
        assert cov_with_crash["hits"] >= cov_calm_only["hits"]
