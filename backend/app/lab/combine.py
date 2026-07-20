"""전략 결합 포트폴리오 — 사전 등록 실험 ③의 순수 로직.

가설: 통과 전략들의 트레이드를 한 계좌(트레이드당 리스크 1% 동일 규칙)로
합산하면, 상관이 낮은 전략의 낙폭이 서로 겹치지 않아 합산 MDD가 개별보다 작다.

여기서는 (a) 리포트 JSON의 트레이드 복원, (b) 월별 R 시계열(상관 측정 재료),
(c) 시계열 상관만 담당한다. 합산 자본곡선은 기존 risk_based_metrics를 그대로
재사용한다 — 개별과 합산이 같은 자로 측정되어야 비교가 정직하다.
"""
from __future__ import annotations

import math
from datetime import date
from typing import Any, Iterable, Mapping

from .types import Trade

_MAX_LOSS_R = 3.0  # risk_based_metrics와 동일한 갭 손실 상한


def trades_from_report_dicts(rows: Iterable[Mapping[str, Any]]) -> list[Trade]:
    """리포트 JSON의 trades 배열을 Trade 객체로 복원. 깨진 행은 건너뛴다."""
    out: list[Trade] = []
    for row in rows:
        try:
            out.append(Trade(
                code=str(row["code"]),
                strategy_id=str(row["strategy_id"]),
                entry_date=date.fromisoformat(row["entry_date"]),
                entry_price=float(row["entry_price"]),
                exit_date=date.fromisoformat(row["exit_date"]),
                exit_price=float(row["exit_price"]),
                exit_reason=str(row["exit_reason"]),
                gross_return_pct=float(row["gross_return_pct"]),
                net_return_pct=float(row["net_return_pct"]),
                stop_price=float(row["stop_price"]) if row.get("stop_price") is not None else None,
            ))
        except Exception:
            continue
    return out


def monthly_r_series(trades: Iterable[Trade], max_loss_r: float = _MAX_LOSS_R) -> dict[str, float]:
    """청산월별 R 합계 — 전략 간 상관 측정의 재료 (risk_based_metrics와 같은 R 규칙)."""
    series: dict[str, float] = {}
    for trade in trades:
        if trade.stop_price is None or trade.entry_price <= 0:
            continue
        stop_distance = (trade.entry_price - trade.stop_price) / trade.entry_price
        if stop_distance <= 0:
            continue
        r = trade.net_return_pct / stop_distance
        if r < -max_loss_r:
            r = -max_loss_r
        key = f"{trade.exit_date.year:04d}-{trade.exit_date.month:02d}"
        series[key] = series.get(key, 0.0) + r
    return series


def combine_series(series_list: Iterable[Mapping[str, float]]) -> dict[str, float]:
    """월별 R 시계열들을 월 단위로 합산 — '한 계좌로 전부 운용'의 월별 손익."""
    combined: dict[str, float] = {}
    for series in series_list:
        for month, value in series.items():
            combined[month] = combined.get(month, 0.0) + value
    return combined


def monthly_sharpe(series: Mapping[str, float]) -> float | None:
    """월별 R 시계열의 샤프 비율(평균÷모표준편차) — 리스크 크기에 불변인 비교축.

    2개월 미만이거나 변동성이 0이면 None (정의 불가).
    """
    values = [series[m] for m in sorted(series)]
    n = len(values)
    if n < 2:
        return None
    mean = sum(values) / n
    variance = sum((v - mean) ** 2 for v in values) / n
    if variance <= 0:
        return None
    return mean / math.sqrt(variance)


def pairwise_correlation(a: Mapping[str, float], b: Mapping[str, float]) -> float | None:
    """월별 R 시계열의 피어슨 상관. 한쪽만 거래한 달은 0으로 채운다 (그 달 손익 0).

    정렬된 공통 축이 2개월 미만이거나 분산이 0이면 None (상관 정의 불가).
    """
    months = sorted(set(a) | set(b))
    if len(months) < 2:
        return None
    xs = [a.get(m, 0.0) for m in months]
    ys = [b.get(m, 0.0) for m in months]
    n = len(months)
    mean_x, mean_y = sum(xs) / n, sum(ys) / n
    cov = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    var_x = sum((x - mean_x) ** 2 for x in xs)
    var_y = sum((y - mean_y) ** 2 for y in ys)
    if var_x <= 0 or var_y <= 0:
        return None
    return cov / math.sqrt(var_x * var_y)
