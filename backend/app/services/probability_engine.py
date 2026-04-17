"""
Probability engine for pattern-based scoring.

This module converts a detected chart pattern into:
  - bullish / bearish probability
  - confidence
  - entry suitability score
  - short human-readable reasoning
"""

from __future__ import annotations

from dataclasses import dataclass
import math

from .pattern_engine import PatternResult


@dataclass
class ProbabilityOutput:
    p_up: float
    p_down: float
    textbook_similarity: float
    pattern_confirmation_score: float
    confidence: float
    entry_score: float
    completion_proximity: float
    recency_score: float
    no_signal_flag: bool
    no_signal_reason: str
    reason_summary: str
    sample_size: int


_STATE_CONFIRMATION_SCORE = {
    "confirmed": 1.0,
    "armed": 0.65,
    "forming": 0.30,
    "invalidated": 0.0,
    "played_out": 0.0,
}

_BULLISH_PATTERNS = {
    "double_bottom",
    "inverse_head_and_shoulders",
    "ascending_triangle",
    "rectangle",
    "cup_and_handle",
    "rounding_bottom",
}
_BEARISH_PATTERNS = {
    "double_top",
    "head_and_shoulders",
    "descending_triangle",
}


def _rule_engine_prob(pattern: PatternResult) -> tuple[float, float]:
    sim = pattern.textbook_similarity

    base_up = 0.50
    base_down = 0.50

    if pattern.pattern_type in _BULLISH_PATTERNS:
        base_up = 0.55 + sim * 0.20
        base_down = 1 - base_up
    elif pattern.pattern_type in _BEARISH_PATTERNS:
        base_down = 0.55 + sim * 0.20
        base_up = 1 - base_down

    if pattern.state == "confirmed":
        base_up = min(0.85, base_up * 1.10)
        base_down = max(0.15, 1 - base_up)
    elif pattern.state == "invalidated":
        if pattern.pattern_type in _BULLISH_PATTERNS:
            base_up, base_down = 0.40, 0.60
        else:
            base_up, base_down = 0.60, 0.40

    return base_up, base_down


def _logistic_calibrate(raw: float) -> float:
    return 0.5 + (raw - 0.5) * 0.85


def _sample_size_score(sample_size: int) -> float:
    if sample_size <= 0:
        return 0.0
    return min(1.0, math.log(sample_size + 1) / math.log(401))


def compute_probability(
    pattern: PatternResult,
    similar_win_rate: float = 0.55,
    sample_size: int = 0,
    liquidity_score: float = 0.7,
    multi_tf_agreement: float = 0.5,
    regime_match: float = 0.5,
    data_quality: float = 0.9,
    risk_penalty: float = 0.0,
    completion_proximity: float = 0.5,
    recency_score: float = 0.5,
) -> ProbabilityOutput:
    if pattern.state in ("invalidated", "played_out"):
        return ProbabilityOutput(
            p_up=0.5,
            p_down=0.5,
            textbook_similarity=pattern.textbook_similarity,
            pattern_confirmation_score=0.0,
            confidence=0.0,
            entry_score=0.0,
            completion_proximity=0.0,
            recency_score=0.0,
            no_signal_flag=True,
            no_signal_reason=f"패턴 상태: {pattern.state}",
            reason_summary=f"{pattern.pattern_type} 패턴은 현재 {pattern.state} 상태라 유효 신호로 보기 어렵습니다.",
            sample_size=sample_size,
        )

    if sample_size < 10:
        return ProbabilityOutput(
            p_up=0.5,
            p_down=0.5,
            textbook_similarity=pattern.textbook_similarity,
            pattern_confirmation_score=_STATE_CONFIRMATION_SCORE.get(pattern.state, 0.3),
            confidence=0.0,
            entry_score=0.0,
            completion_proximity=completion_proximity,
            recency_score=recency_score,
            no_signal_flag=True,
            no_signal_reason="유사 패턴 표본 부족",
            reason_summary=f"현재 확보된 유사 패턴 표본은 {sample_size}건이라 통계적으로 신뢰하기엔 부족합니다.",
            sample_size=sample_size,
        )

    rule_up, rule_down = _rule_engine_prob(pattern)
    pat_conf = _STATE_CONFIRMATION_SCORE.get(pattern.state, 0.3)
    ml_prob = 0.5

    p_up_raw = (
        0.30 * rule_up
        + 0.25 * similar_win_rate
        + 0.20 * ml_prob
        + 0.15 * pat_conf
        + 0.05 * regime_match
        + 0.05 * completion_proximity
    )
    p_down_raw = (
        0.30 * rule_down
        + 0.25 * (1 - similar_win_rate)
        + 0.20 * (1 - ml_prob)
        + 0.15 * (1 - pat_conf)
        + 0.05 * (1 - regime_match)
        + 0.05 * (1 - completion_proximity)
    )

    p_up = _logistic_calibrate(p_up_raw)
    p_down = _logistic_calibrate(p_down_raw)
    total = p_up + p_down
    p_up, p_down = p_up / total, p_down / total

    size_score = _sample_size_score(sample_size)
    confidence = (
        0.22 * size_score
        + 0.22 * pattern.textbook_similarity
        + 0.16 * multi_tf_agreement
        + 0.12 * regime_match
        + 0.10 * data_quality
        + 0.18 * recency_score
    )

    direction_prob = max(p_up, p_down)
    entry_score = (
        0.24 * direction_prob
        + 0.15 * pattern.textbook_similarity
        + 0.15 * pat_conf
        + 0.10 * similar_win_rate
        + 0.10 * liquidity_score
        + 0.08 * multi_tf_agreement
        + 0.06 * data_quality
        + 0.12 * completion_proximity
        + 0.12 * recency_score
        - 0.15 * risk_penalty
    )
    entry_score = max(0.0, min(1.0, entry_score))

    summary = (
        f"{pattern.pattern_type} 패턴 / 교과서 유사도 {pattern.textbook_similarity:.0%} / "
        f"상태 {pattern.state} / 완성 임박도 {completion_proximity:.0%} / "
        f"신호 신선도 {recency_score:.0%} / 유사 패턴 {sample_size}건 중 승률 {similar_win_rate:.0%} / "
        f"신뢰도 {confidence:.0%}"
    )

    no_signal = (
        confidence < 0.3
        or pattern.textbook_similarity < 0.4
        or recency_score < 0.15
        or (data_quality < 0.6 and confidence < 0.72)
    )
    no_signal_reason = "" if not no_signal else "신호 최신성 또는 신뢰도가 기준치에 미달합니다."

    return ProbabilityOutput(
        p_up=round(p_up, 3),
        p_down=round(p_down, 3),
        textbook_similarity=pattern.textbook_similarity,
        pattern_confirmation_score=round(pat_conf, 3),
        confidence=round(confidence, 3),
        entry_score=round(entry_score, 3),
        completion_proximity=round(completion_proximity, 3),
        recency_score=round(recency_score, 3),
        no_signal_flag=no_signal,
        no_signal_reason=no_signal_reason,
        reason_summary=summary,
        sample_size=sample_size,
    )
