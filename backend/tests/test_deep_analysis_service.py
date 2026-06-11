"""정밀분석(과거 패턴 성적표) 서비스 테스트."""
from __future__ import annotations

import numpy as np
import pandas as pd

from app.services.deep_analysis_service import (
    _long_context,
    _replay_pattern_cases_sync,
    _summarize_cases,
)


def _history_with_resolved_w() -> pd.DataFrame:
    """W 형성 → 돌파 확정 → 목표 도달 랠리가 들어 있는 ~190봉 이력."""
    rng = np.random.default_rng(0)
    closes = (
        list(np.linspace(10_200, 10_000, 40))   # 리드인
        + list(np.linspace(10_000, 9_000, 30))
        + list(np.linspace(9_000, 8_000, 15))   # 저점1
        + list(np.linspace(8_000, 9_000, 15))   # 넥라인 봉우리
        + list(np.linspace(9_000, 8_050, 15))   # 저점2
        + list(np.linspace(8_050, 9_150, 12))   # 돌파 확정 구간
        + list(np.linspace(9_150, 10_600, 20))  # 목표 도달 랠리
        + [10_500 + float(rng.normal(0, 15)) for _ in range(40)]
    )
    dates = pd.bdate_range("2022-01-03", periods=len(closes))
    rows = []
    for dt, close in zip(dates, closes):
        open_px = close * (1 + rng.normal(0, 0.002))
        high = max(open_px, close) * (1 + abs(rng.normal(0, 0.003)))
        low = min(open_px, close) * (1 - abs(rng.normal(0, 0.003)))
        rows.append(
            {"date": dt, "open": round(open_px), "high": round(high),
             "low": round(low), "close": round(close), "volume": 1_000_000}
        )
    return pd.DataFrame(rows)


class TestReplay:
    def test_finds_resolved_double_bottom(self):
        cases = _replay_pattern_cases_sync(_history_with_resolved_w())
        w_cases = [c for c in cases if c["pattern_type"] == "double_bottom"]
        assert w_cases, "W 사례가 최소 1건 잡혀야 함"
        assert any(c["outcome"] == "success" for c in w_cases)

    def test_dedups_adjacent_window_detections(self):
        cases = _replay_pattern_cases_sync(_history_with_resolved_w())
        # 같은 구조가 인접 윈도우마다 중복 수집되면 수십 건이 됨 — 시그니처 dedup 검증
        w_cases = [c for c in cases if c["pattern_type"] == "double_bottom"]
        assert len(w_cases) <= 5

    def test_case_fields_present(self):
        cases = _replay_pattern_cases_sync(_history_with_resolved_w())
        for case in cases:
            assert set(case) >= {"pattern_type", "signal_date", "outcome", "move_pct", "mfe_pct", "mae_pct"}
            assert case["outcome"] in {"success", "fail", "timeout"}


class TestSummarize:
    def test_summary_math(self):
        cases = [
            {"pattern_type": "double_bottom", "outcome": "success", "bars_to_outcome": 10, "move_pct": 0.10},
            {"pattern_type": "double_bottom", "outcome": "fail", "bars_to_outcome": 6, "move_pct": -0.05},
            {"pattern_type": "double_bottom", "outcome": "timeout", "bars_to_outcome": None, "move_pct": 0.01},
            {"pattern_type": "vcp", "outcome": "success", "bars_to_outcome": 4, "move_pct": 0.08},
        ]
        stats = {s["pattern_type"]: s for s in _summarize_cases(cases)}
        w = stats["double_bottom"]
        assert (w["total"], w["wins"], w["losses"], w["timeouts"]) == (3, 1, 1, 1)
        assert w["win_rate"] == 0.5
        assert w["avg_bars_to_outcome"] == 8.0
        assert w["avg_win_move_pct"] == 0.10
        assert stats["vcp"]["win_rate"] == 1.0


class TestLongContext:
    def test_position_and_regime(self, sample_ohlcv_df_long):
        ctx = _long_context(sample_ohlcv_df_long)
        assert 0.0 <= ctx["week52_position"] <= 1.0
        assert ctx["week52_high"] >= ctx["week52_low"]
        assert ctx["volatility_regime"] in {"확대", "수축", "보통"}

    def test_empty_frame(self):
        assert _long_context(pd.DataFrame()) == {}
