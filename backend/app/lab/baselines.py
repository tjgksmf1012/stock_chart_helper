"""랜덤 진입 벤치마크 — 귀무가설 (스펙 §2 피검체 표의 random_entry).

피검체 전략과 "동일 청산" 조건을 근사하기 위해, 피검체 신호들의 손절/목표
% 거리와 보유일의 중앙값을 그대로 쓰고 진입 시점만 무작위로 뽑는다.
이 벤치마크를 못 넘는 전략은 진입 타이밍에 엣지가 없는 것이다.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .types import Signal


def random_benchmark_signals(
    bars_by_code: dict[str, pd.DataFrame],
    subject_signals: list[Signal],
    n_signals: int,
    seed: int = 42,
) -> list[Signal]:
    if not subject_signals or not bars_by_code:
        return []

    stop_dists: list[float] = []
    target_dists: list[float] = []
    holdings: list[int] = []
    by_code_date = {
        code: {pd.Timestamp(r["date"]).date(): float(r["close"]) for _, r in df.iterrows()}
        for code, df in bars_by_code.items()
    }
    for s in subject_signals:
        close = by_code_date.get(s.code, {}).get(s.signal_date)
        if not close:
            continue
        stop_dists.append((close - s.stop_price) / close)
        if s.target_price is not None:
            target_dists.append((s.target_price - close) / close)
        holdings.append(s.max_holding_days)
    if not stop_dists:
        return []

    stop_pct = float(np.median(stop_dists))
    target_pct = float(np.median(target_dists)) if target_dists else None
    holding = int(np.median(holdings))

    rng = np.random.default_rng(seed)
    codes = sorted(bars_by_code.keys())
    out: list[Signal] = []
    for _ in range(n_signals):
        code = codes[int(rng.integers(0, len(codes)))]
        df = bars_by_code[code]
        if len(df) < 2:
            continue
        idx = int(rng.integers(0, len(df) - 1))  # 마지막 봉 제외 (다음 봉 진입 필요)
        row = df.iloc[idx]
        close = float(row["close"])
        out.append(
            Signal(
                code=code,
                signal_date=pd.Timestamp(row["date"]).date(),
                stop_price=close * (1 - stop_pct),
                target_price=(close * (1 + target_pct)) if target_pct is not None else None,
                max_holding_days=holding,
            )
        )
    return out
