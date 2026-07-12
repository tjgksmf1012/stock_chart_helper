"""기존 패턴 엔진을 랩의 첫 피검체로 감싸는 어댑터 (스펙 §2 legacy_patterns).

기존 앱이 추천하던 방식과 같은 조건을 재현한다:
- confirmed 상태의 강세(롱) 패턴만
- 손절 = invalidation_level, 목표 = target_level, 시간 청산 40거래일
- 신호일 종가가 (손절, 목표) 사이에 없으면 퇴화 케이스로 폐기
  (deep_analysis_service의 가드와 동일)

슬라이딩 윈도우 탐지는 각 윈도우의 마지막 봉 정보까지만 쓰므로 미래 참조가
없다 — test_no_lookahead_truncation_consistency가 이를 회귀 테스트한다.
"""
from __future__ import annotations

import pandas as pd

from ..lab.types import Signal
from ..services.pattern_engine import PatternEngine, pattern_direction_is_bullish

_WINDOW = 120
_STEP = 5
_MAX_HOLDING = 40


class LegacyPatternStrategy:
    id = "legacy_patterns"
    label = "기존 패턴 엔진 (confirmed 롱)"
    # truncation 회귀 테스트로 검증된 인과성 — 하네스가 종목당 1회 계산 경로 사용
    causal_signals = True

    def fit(self, train_bars: dict[str, pd.DataFrame]) -> dict:
        return {}  # 고정 규칙 — 학습 파라미터 없음

    def signals(self, code: str, bars: pd.DataFrame, params: dict) -> list[Signal]:
        engine = PatternEngine()
        out: list[Signal] = []
        seen: set[tuple[str, object]] = set()
        n = len(bars)

        for start in range(0, max(0, n - _WINDOW) + 1, _STEP):
            window = bars.iloc[start:start + _WINDOW]
            if len(window) < _WINDOW:
                break
            window = window.copy().reset_index(drop=True)
            try:
                patterns = engine.detect_all(window, timeframe="1d")
            except Exception:
                continue
            signal_date = pd.Timestamp(window.iloc[-1]["date"]).date()
            close = float(window.iloc[-1]["close"])

            for pattern in patterns:
                if pattern.state != "confirmed":
                    continue
                if pattern.target_level is None or pattern.invalidation_level is None:
                    continue
                if not pattern_direction_is_bullish(pattern):
                    continue  # 롱 온리 (숏은 개인 실행 불가 — 스펙)
                if not (pattern.invalidation_level < close < pattern.target_level):
                    continue  # 퇴화 케이스 가드
                key = (pattern.pattern_type, signal_date)
                if key in seen:
                    continue
                seen.add(key)
                out.append(
                    Signal(
                        code=code,
                        signal_date=signal_date,
                        stop_price=float(pattern.invalidation_level),
                        target_price=float(pattern.target_level),
                        max_holding_days=_MAX_HOLDING,
                    )
                )
        return out
