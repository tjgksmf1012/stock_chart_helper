"""전략 레지스트리 — CLI(run_lab)와 라이브 신호 서비스가 공유하는 단일 출처.

새 전략을 추가하면 여기 한 곳만 등록하면 검증 CLI와 신호 게이트 양쪽에 반영된다.
"""
from __future__ import annotations

from .high52_breakout import High52BreakoutStrategy
from .legacy_patterns import LegacyPatternStrategy
from .trend_tsmom import TrendTsmomStrategy
from .vol_breakout import VolBreakoutStrategy
from .xs_momentum import XsMomentumStrategy

STRATEGY_REGISTRY: dict[str, type] = {
    "legacy_patterns": LegacyPatternStrategy,
    "vol_breakout": VolBreakoutStrategy,
    "high52_breakout": High52BreakoutStrategy,
    "trend_tsmom": TrendTsmomStrategy,
    "xs_momentum": XsMomentumStrategy,
}


def make_strategy(strategy_id: str):
    """등록된 전략 인스턴스 생성. 미등록이면 KeyError."""
    return STRATEGY_REGISTRY[strategy_id]()
