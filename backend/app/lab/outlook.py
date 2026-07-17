"""확률적 전망 — 점 예측 대신 "구간 + 그 구간의 실측 적중률".

"내일 몇% 오른다"는 점 예측은 어떤 모델로도 정직하게 불가능하다 (자체 실측:
1,531건 학습 모델의 특징 계수가 전부 0 근처). 정직하게 가능한 것은:
1. 과거 선행수익률 분포의 분위수로 "80% 확률 구간"을 제시하고
2. 그 구간이 실제로 80%를 맞췄는지(coverage)를 walk-forward로 측정해 함께 표시.
적중률이 명목(80%)에서 벗어나면 그 자체가 "지금 분포가 과거와 다르다"는 경고다.

전부 순수 함수 — 시세 로딩은 라우터가 담당한다.
"""
from __future__ import annotations

from typing import Sequence

import numpy as np

QUANTILE_KEYS = ("q10", "q25", "q50", "q75", "q90")
_QUANTILE_LEVELS = (0.10, 0.25, 0.50, 0.75, 0.90)
_MIN_SAMPLES = 60


def _forward_returns(closes: Sequence[float], horizon: int) -> np.ndarray:
    """겹치는 h일 선행수익률 r_i = c[i+h]/c[i] - 1. 0가격 오염 표본은 제외."""
    arr = np.asarray(closes, dtype=float)
    if len(arr) <= horizon:
        return np.empty(0)
    base = arr[:-horizon]
    future = arr[horizon:]
    valid = (base > 0) & (future > 0)
    return future[valid] / base[valid] - 1


def forward_return_quantiles(
    closes: Sequence[float], horizon: int, min_samples: int = _MIN_SAMPLES
) -> dict[str, float] | None:
    """h일 선행수익률 분포의 분위수 (q10/q25/q50/q75/q90). 표본 부족이면 None."""
    returns = _forward_returns(closes, horizon)
    if len(returns) < min_samples:
        return None
    values = np.quantile(returns, _QUANTILE_LEVELS)
    return {key: float(v) for key, v in zip(QUANTILE_KEYS, values)}


def interval_coverage(
    closes: Sequence[float],
    horizon: int,
    lookback: int = 252,
    q_low: float = 0.10,
    q_high: float = 0.90,
    min_samples: int = _MIN_SAMPLES,
) -> dict[str, float | int] | None:
    """walk-forward로 "과거 lookback일 분포의 [q_low, q_high] 구간"이 실제
    h일 뒤 수익률을 몇 %나 포함했는지 측정한다.

    시점 t의 구간은 t까지의 데이터로만 추정한다(미래 참조 없음): 구간 추정에
    쓰는 선행수익률은 i+h <= t 인 표본뿐이다. 평가 시점은 horizon 간격으로
    건너뛰어(stride=horizon) 겹침 상관을 줄인다.
    """
    arr = np.asarray(closes, dtype=float)
    n = len(arr)
    # 첫 평가 시점: 추정 표본 min_samples개 확보에 lookback+horizon 필요
    start = lookback + horizon
    if n < start + horizon + 1:
        return None

    hits = 0
    total = 0
    for t in range(start, n - horizon, horizon):
        window = arr[t - lookback: t + 1]
        estimation_returns = _forward_returns(window, horizon)
        if len(estimation_returns) < min_samples:
            continue
        low, high = np.quantile(estimation_returns, [q_low, q_high])
        if arr[t] <= 0 or arr[t + horizon] <= 0:
            continue
        realized = arr[t + horizon] / arr[t] - 1
        total += 1
        # 부동소수점 허용오차 — 결정적 시계열에서 경계값이 1e-15 수준으로 어긋나
        # 가짜 미스가 나는 것 방지 (수익률 스케일 대비 무시 가능한 크기)
        eps = 1e-9
        if low - eps <= realized <= high + eps:
            hits += 1

    if total < 10:
        return None
    return {
        "coverage": round(hits / total, 3),
        "hits": hits,
        "n": total,
        "nominal": round(q_high - q_low, 3),
    }
