"""
Probability engine for pattern-based scoring.
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
    empirical_win_rate: float
    sample_reliability: float


_STATE_CONFIRMATION_SCORE = {
    "confirmed": 1.0,
    "armed": 0.68,
    "forming": 0.34,
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
    similarity = pattern.textbook_similarity
    base_up = 0.50
    base_down = 0.50

    if pattern.pattern_type in _BULLISH_PATTERNS:
        base_up = 0.55 + similarity * 0.20
        base_down = 1 - base_up
    elif pattern.pattern_type in _BEARISH_PATTERNS:
        base_down = 0.55 + similarity * 0.20
        base_up = 1 - base_down

    if pattern.state == "confirmed":
        if pattern.pattern_type in _BULLISH_PATTERNS:
            base_up = min(0.86, base_up * 1.08)
            base_down = 1 - base_up
        elif pattern.pattern_type in _BEARISH_PATTERNS:
            base_down = min(0.86, base_down * 1.08)
            base_up = 1 - base_down
    elif pattern.state == "armed":
        if pattern.pattern_type in _BULLISH_PATTERNS:
            base_up = min(0.80, base_up * 1.03)
            base_down = 1 - base_up
        elif pattern.pattern_type in _BEARISH_PATTERNS:
            base_down = min(0.80, base_down * 1.03)
            base_up = 1 - base_down

    return base_up, base_down


def _logistic_calibrate(raw: float) -> float:
    return 0.5 + (raw - 0.5) * 0.85


def _sample_size_score(sample_size: int) -> float:
    if sample_size <= 0:
        return 0.0
    return min(1.0, math.log(sample_size + 1) / math.log(401))


def _sample_reliability(sample_size: int, win_rate: float) -> float:
    if sample_size <= 0:
        return 0.0

    coverage = min(1.0, math.log(sample_size + 1) / math.log(251))
    variance = max(0.0001, win_rate * (1 - win_rate))
    interval_width = 1.96 * math.sqrt(variance / max(sample_size, 1)) * 2
    stability = max(0.0, min(1.0, 1 - interval_width / 0.55))
    return max(0.0, min(1.0, 0.55 * coverage + 0.45 * stability))


def _bayesian_success_rate(successes: int | None, total: int | None, prior_rate: float, prior_strength: float = 18.0) -> float:
    if not total or total <= 0 or successes is None:
        return prior_rate
    return (successes + prior_rate * prior_strength) / (total + prior_strength)


def _directional_empirical_prob(pattern: PatternResult, posterior_success_rate: float) -> tuple[float, float]:
    if pattern.pattern_type in _BULLISH_PATTERNS:
        return posterior_success_rate, 1 - posterior_success_rate
    if pattern.pattern_type in _BEARISH_PATTERNS:
        return 1 - posterior_success_rate, posterior_success_rate
    neutral = 0.5 + (posterior_success_rate - 0.5) * 0.35
    return neutral, 1 - neutral


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
    wins: int | None = None,
    total: int | None = None,
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
            no_signal_reason=f"패턴 상태가 {pattern.state}로 재판정되었습니다.",
            reason_summary=f"{pattern.pattern_type} 패턴은 이미 {pattern.state} 상태로 평가되어 현재 유효 신호로 보기 어렵습니다.",
            sample_size=sample_size,
            empirical_win_rate=similar_win_rate,
            sample_reliability=0.0,
        )

    if sample_size < 6:
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
            no_signal_reason="유사 패턴 표본 수가 아직 너무 적습니다.",
            reason_summary=f"현재 통계에 잡힌 유사 패턴 표본이 {sample_size}건이라 확률을 강하게 제시하기에는 근거가 부족합니다.",
            sample_size=sample_size,
            empirical_win_rate=similar_win_rate,
            sample_reliability=0.0,
        )

    rule_up, rule_down = _rule_engine_prob(pattern)
    pattern_confirmation = _STATE_CONFIRMATION_SCORE.get(pattern.state, 0.3)
    posterior_success_rate = _bayesian_success_rate(wins, total, similar_win_rate)
    empirical_up, empirical_down = _directional_empirical_prob(pattern, posterior_success_rate)
    sample_reliability = _sample_reliability(sample_size, posterior_success_rate)
    size_score = _sample_size_score(sample_size)

    p_up_raw = (
        0.30 * rule_up
        + 0.28 * empirical_up
        + 0.14 * pattern_confirmation
        + 0.08 * regime_match
        + 0.07 * completion_proximity
        + 0.07 * recency_score
        + 0.06 * data_quality
    )
    p_down_raw = (
        0.30 * rule_down
        + 0.28 * empirical_down
        + 0.14 * (1 - pattern_confirmation)
        + 0.08 * (1 - regime_match)
        + 0.07 * (1 - completion_proximity)
        + 0.07 * (1 - recency_score)
        + 0.06 * (1 - data_quality)
    )

    p_up = _logistic_calibrate(p_up_raw)
    p_down = _logistic_calibrate(p_down_raw)
    total_prob = p_up + p_down
    p_up, p_down = p_up / total_prob, p_down / total_prob

    confidence = (
        0.20 * sample_reliability
        + 0.14 * size_score
        + 0.18 * pattern.textbook_similarity
        + 0.14 * multi_tf_agreement
        + 0.10 * regime_match
        + 0.10 * data_quality
        + 0.14 * recency_score
    )
    confidence = max(0.0, min(1.0, confidence))

    direction_prob = max(p_up, p_down)
    entry_score = (
        0.22 * direction_prob
        + 0.14 * pattern.textbook_similarity
        + 0.12 * pattern_confirmation
        + 0.10 * posterior_success_rate
        + 0.10 * liquidity_score
        + 0.08 * multi_tf_agreement
        + 0.07 * data_quality
        + 0.07 * sample_reliability
        + 0.10 * completion_proximity
        + 0.10 * recency_score
        - 0.16 * risk_penalty
    )
    entry_score = max(0.0, min(1.0, entry_score))

    wins_text = f"{wins}/{total}" if wins is not None and total is not None and total > 0 else f"{sample_size}건"
    summary = (
        f"{pattern.pattern_type} 패턴 / 교과서 유사도 {pattern.textbook_similarity:.0%} / "
        f"상태 {pattern.state} / 완성 임박도 {completion_proximity:.0%} / "
        f"신호 신선도 {recency_score:.0%} / 표본 {wins_text} / "
        f"보정 승률 {posterior_success_rate:.0%} / 표본 신뢰도 {sample_reliability:.0%} / "
        f"신뢰도 {confidence:.0%}"
    )

    no_signal = (
        confidence < 0.32
        or pattern.textbook_similarity < 0.40
        or recency_score < 0.15
        or sample_reliability < 0.16
        or (data_quality < 0.60 and confidence < 0.74)
    )
    no_signal_reason = (
        ""
        if not no_signal
        else "표본 신뢰도, 신호 최신성, 데이터 품질을 합산했을 때 기준치를 넘지 못해 보수적으로 No Signal로 분류했습니다."
    )

    return ProbabilityOutput(
        p_up=round(p_up, 3),
        p_down=round(p_down, 3),
        textbook_similarity=pattern.textbook_similarity,
        pattern_confirmation_score=round(pattern_confirmation, 3),
        confidence=round(confidence, 3),
        entry_score=round(entry_score, 3),
        completion_proximity=round(completion_proximity, 3),
        recency_score=round(recency_score, 3),
        no_signal_flag=no_signal,
        no_signal_reason=no_signal_reason,
        reason_summary=summary,
        sample_size=sample_size,
        empirical_win_rate=round(posterior_success_rate, 3),
        sample_reliability=round(sample_reliability, 3),
    )
