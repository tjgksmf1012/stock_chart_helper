"""
Probability engine for pattern-based scoring.
"""

from __future__ import annotations

from dataclasses import dataclass
import math

from .pattern_engine import PatternResult
from .timeframe_service import probability_threshold_profile


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
    reward_risk_ratio: float
    headroom_score: float
    target_distance_pct: float
    stop_distance_pct: float
    avg_mfe_pct: float
    avg_mae_pct: float
    avg_bars_to_outcome: float
    historical_edge_score: float
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
    "vcp",
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
    formation_quality = _formation_quality(pattern)

    if pattern.pattern_type in _BULLISH_PATTERNS:
        base_up = 0.55 + similarity * 0.20
        base_up = 0.5 + (base_up - 0.5) * (0.40 + 0.60 * formation_quality)
        base_down = 1 - base_up
    elif pattern.pattern_type in _BEARISH_PATTERNS:
        base_down = 0.55 + similarity * 0.20
        base_down = 0.5 + (base_down - 0.5) * (0.40 + 0.60 * formation_quality)
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


def _formation_quality(pattern: PatternResult) -> float:
    return max(
        0.0,
        min(
            1.0,
            0.24 * pattern.leg_balance_fit
            + 0.21 * pattern.reversal_energy_fit
            + 0.19 * pattern.breakout_quality_fit
            + 0.17 * pattern.retest_quality_fit
            + 0.11 * pattern.variant_fit
            + 0.08 * pattern.candlestick_confirmation_fit,
        ),
    )


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


def _historical_edge(avg_mfe_pct: float, avg_mae_pct: float, avg_bars_to_outcome: float, sample_size: int) -> float:
    rr = avg_mfe_pct / max(avg_mae_pct, 0.01)
    rr_score = max(0.0, min(1.0, rr / 2.5))
    mfe_score = max(0.0, min(1.0, avg_mfe_pct / 0.18))
    expected_bars = 18.0 if sample_size >= 20 else 10.0 if sample_size >= 10 else 6.0
    speed_score = max(0.0, min(1.0, 1 - (avg_bars_to_outcome / max(expected_bars, 1.0))))
    return max(0.0, min(1.0, 0.45 * rr_score + 0.30 * mfe_score + 0.25 * speed_score))


def _summary(
    pattern: PatternResult,
    completion_proximity: float,
    recency_score: float,
    sample_text: str,
    reward_risk_ratio: float,
    target_distance_pct: float,
    avg_mfe_pct: float,
    avg_mae_pct: float,
    avg_bars_to_outcome: float,
    edge_score: float,
    posterior_success_rate: float,
    sample_reliability: float,
    confidence: float,
) -> str:
    return (
        f"{pattern.pattern_type} 패턴 / 교과서 유사도 {pattern.textbook_similarity:.0%} / "
        f"상태 {pattern.state} / 완성 임박도 {completion_proximity:.0%} / "
        f"신호 신선도 {recency_score:.0%} / 표본 {sample_text} / "
        f"기대 손익비 {reward_risk_ratio:.2f} / 목표까지 여지 {target_distance_pct:.1%} / "
        f"평균 MFE {avg_mfe_pct:.1%} / 평균 MAE {avg_mae_pct:.1%} / "
        f"평균 결과 바 수 {avg_bars_to_outcome:.1f} / 백테스트 edge {edge_score:.0%} / "
        f"보정 승률 {posterior_success_rate:.0%} / 표본 신뢰도 {sample_reliability:.0%} / "
        f"신뢰도 {confidence:.0%}"
    )


def _probability_cap(
    pattern: PatternResult,
    timeframe: str | None,
    no_signal: bool,
    reward_risk_ratio: float,
    headroom_score: float,
    target_distance_pct: float,
    avg_mfe_pct: float,
    edge_score: float,
    confidence: float,
    sample_reliability: float,
) -> float:
    profile = probability_threshold_profile(timeframe)
    cap = 0.78
    if pattern.state == "forming":
        cap = min(cap, profile.forming_direction_cap)
    elif pattern.state == "armed":
        cap = min(cap, profile.armed_direction_cap)
    elif pattern.state == "confirmed":
        cap = min(cap, profile.confirmed_direction_cap)

    if no_signal:
        cap = min(cap, profile.no_signal_direction_cap)
    if pattern.textbook_similarity < 0.55:
        cap = min(cap, 0.59)
    if pattern.variant_fit < 0.52 or _formation_quality(pattern) < 0.46:
        cap = min(cap, 0.58)
    if reward_risk_ratio < 1.15 or headroom_score < 0.18:
        cap = min(cap, 0.57)
    if edge_score < 0.34 or confidence < 0.45 or sample_reliability < 0.22:
        cap = min(cap, 0.60)

    if target_distance_pct >= profile.extreme_target_warn_pct:
        cap = min(cap, 0.58 if pattern.state == "forming" else 0.62)
    elif target_distance_pct >= profile.far_target_warn_pct and pattern.state == "forming":
        cap = min(cap, 0.59)

    if avg_mfe_pct > 0 and target_distance_pct > max(profile.far_target_warn_pct * 0.75, avg_mfe_pct * profile.mfe_soft_multiplier):
        cap = min(cap, 0.59)
    if avg_mfe_pct > 0 and target_distance_pct > max(profile.extreme_target_warn_pct * 0.7, avg_mfe_pct * profile.mfe_hard_multiplier):
        cap = min(cap, 0.56)

    return max(0.51, min(0.78, cap))


def _readable_summary(
    pattern: PatternResult,
    completion_proximity: float,
    recency_score: float,
    sample_text: str,
    reward_risk_ratio: float,
    target_distance_pct: float,
    avg_mfe_pct: float,
    avg_mae_pct: float,
    avg_bars_to_outcome: float,
    edge_score: float,
    posterior_success_rate: float,
    sample_reliability: float,
    confidence: float,
) -> str:
    return (
        f"{pattern.pattern_type} pattern / textbook similarity {pattern.textbook_similarity:.0%} / "
        f"state {pattern.state} / completion {completion_proximity:.0%} / "
        f"signal freshness {recency_score:.0%} / sample {sample_text} / "
        f"reward-risk {reward_risk_ratio:.2f} / target distance {target_distance_pct:.1%} / "
        f"avg MFE {avg_mfe_pct:.1%} / avg MAE {avg_mae_pct:.1%} / "
        f"avg bars to outcome {avg_bars_to_outcome:.1f} / backtest edge {edge_score:.0%} / "
        f"calibrated win rate {posterior_success_rate:.0%} / sample reliability {sample_reliability:.0%} / "
        f"confidence {confidence:.0%}"
    )


def _apply_directional_cap(p_up: float, p_down: float, cap: float) -> tuple[float, float]:
    if p_up >= p_down and p_up > cap:
        return cap, 1 - cap
    if p_down > p_up and p_down > cap:
        return 1 - cap, cap
    return p_up, p_down


def compute_probability(
    pattern: PatternResult,
    timeframe: str | None = None,
    similar_win_rate: float = 0.55,
    sample_size: int = 0,
    liquidity_score: float = 0.7,
    multi_tf_agreement: float = 0.5,
    regime_match: float = 0.5,
    data_quality: float = 0.9,
    risk_penalty: float = 0.0,
    completion_proximity: float = 0.5,
    recency_score: float = 0.5,
    reward_risk_ratio: float = 1.0,
    headroom_score: float = 0.5,
    target_distance_pct: float = 0.0,
    stop_distance_pct: float = 0.0,
    avg_mfe_pct: float = 0.0,
    avg_mae_pct: float = 0.0,
    avg_bars_to_outcome: float = 0.0,
    historical_edge_score: float = 0.5,
    wins: int | None = None,
    total: int | None = None,
) -> ProbabilityOutput:
    profile = probability_threshold_profile(timeframe)
    base_kwargs = {
        "textbook_similarity": pattern.textbook_similarity,
        "reward_risk_ratio": round(reward_risk_ratio, 3),
        "headroom_score": round(headroom_score, 3),
        "target_distance_pct": round(target_distance_pct, 4),
        "stop_distance_pct": round(stop_distance_pct, 4),
        "avg_mfe_pct": round(avg_mfe_pct, 4),
        "avg_mae_pct": round(avg_mae_pct, 4),
        "avg_bars_to_outcome": round(avg_bars_to_outcome, 2),
        "historical_edge_score": round(historical_edge_score, 3),
        "sample_size": sample_size,
        "empirical_win_rate": similar_win_rate,
        "sample_reliability": 0.0,
    }

    if pattern.state in ("invalidated", "played_out"):
        return ProbabilityOutput(
            p_up=0.5,
            p_down=0.5,
            pattern_confirmation_score=0.0,
            confidence=0.0,
            entry_score=0.0,
            completion_proximity=0.0,
            recency_score=0.0,
            no_signal_flag=True,
            no_signal_reason=f"패턴 상태가 이미 {pattern.state}로 판정되었습니다.",
            reason_summary=f"{pattern.pattern_type} 패턴은 이미 {pattern.state} 상태라 현재 활성 진입 신호로 보지 않습니다.",
            **base_kwargs,
        )

    if sample_size < 6:
        return ProbabilityOutput(
            p_up=0.5,
            p_down=0.5,
            pattern_confirmation_score=_STATE_CONFIRMATION_SCORE.get(pattern.state, 0.3),
            confidence=0.0,
            entry_score=0.0,
            completion_proximity=completion_proximity,
            recency_score=recency_score,
            no_signal_flag=True,
            no_signal_reason="유사 패턴 표본 수가 아직 충분하지 않습니다.",
            reason_summary=f"현재 확인된 유사 표본이 {sample_size}건 수준이라 신호를 보수적으로 해석합니다.",
            **base_kwargs,
        )

    rule_up, rule_down = _rule_engine_prob(pattern)
    formation_quality = _formation_quality(pattern)
    pattern_confirmation = _STATE_CONFIRMATION_SCORE.get(pattern.state, 0.3) * (0.55 + 0.45 * formation_quality)
    posterior_success_rate = _bayesian_success_rate(wins, total, similar_win_rate)
    empirical_up, empirical_down = _directional_empirical_prob(pattern, posterior_success_rate)
    sample_reliability = _sample_reliability(sample_size, posterior_success_rate)
    size_score = _sample_size_score(sample_size)
    rr_score = min(1.0, reward_risk_ratio / 2.5)
    edge_score = max(
        0.0,
        min(
            1.0,
            0.55 * historical_edge_score + 0.45 * _historical_edge(avg_mfe_pct, avg_mae_pct, avg_bars_to_outcome, sample_size),
        ),
    )

    p_up_raw = (
        0.27 * rule_up
        + 0.25 * empirical_up
        + 0.13 * pattern_confirmation
        + 0.08 * regime_match
        + 0.07 * completion_proximity
        + 0.07 * recency_score
        + 0.05 * data_quality
        + 0.04 * rr_score
        + 0.04 * edge_score
    )
    p_down_raw = (
        0.27 * rule_down
        + 0.25 * empirical_down
        + 0.13 * (1 - pattern_confirmation)
        + 0.08 * (1 - regime_match)
        + 0.07 * (1 - completion_proximity)
        + 0.07 * (1 - recency_score)
        + 0.05 * (1 - data_quality)
        + 0.04 * (1 - rr_score)
        + 0.04 * (1 - edge_score)
    )

    p_up = _logistic_calibrate(p_up_raw)
    p_down = _logistic_calibrate(p_down_raw)
    total_prob = max(p_up + p_down, 1e-9)
    p_up, p_down = p_up / total_prob, p_down / total_prob

    confidence = (
        0.18 * sample_reliability
        + 0.13 * size_score
        + 0.17 * pattern.textbook_similarity
        + 0.08 * formation_quality
        + 0.12 * multi_tf_agreement
        + 0.10 * regime_match
        + 0.06 * data_quality
        + 0.07 * recency_score
        + 0.07 * headroom_score
        + 0.06 * edge_score
    )
    confidence = max(0.0, min(1.0, confidence))

    direction_prob = max(p_up, p_down)
    entry_score = (
        0.16 * direction_prob
        + 0.12 * pattern.textbook_similarity
        + 0.10 * pattern_confirmation
        + 0.08 * formation_quality
        + 0.09 * posterior_success_rate
        + 0.08 * liquidity_score
        + 0.08 * multi_tf_agreement
        + 0.06 * data_quality
        + 0.06 * sample_reliability
        + 0.07 * completion_proximity
        + 0.07 * recency_score
        + 0.12 * rr_score
        + 0.09 * headroom_score
        + 0.06 * edge_score
        - 0.12 * risk_penalty
    )
    entry_score *= max(0.22, 0.35 + 0.65 * rr_score)
    entry_score *= max(0.25, 0.30 + 0.70 * headroom_score)
    entry_score = max(0.0, min(1.0, entry_score))

    wins_text = f"{wins}/{total}" if wins is not None and total is not None and total > 0 else str(sample_size)
    summary = _readable_summary(
        pattern=pattern,
        completion_proximity=completion_proximity,
        recency_score=recency_score,
        sample_text=wins_text,
        reward_risk_ratio=reward_risk_ratio,
        target_distance_pct=target_distance_pct,
        avg_mfe_pct=avg_mfe_pct,
        avg_mae_pct=avg_mae_pct,
        avg_bars_to_outcome=avg_bars_to_outcome,
        edge_score=edge_score,
        posterior_success_rate=posterior_success_rate,
        sample_reliability=sample_reliability,
        confidence=confidence,
    )

    unrealistic_target = (
        target_distance_pct >= profile.extreme_target_warn_pct
        or (avg_mfe_pct > 0 and target_distance_pct > max(profile.far_target_warn_pct, avg_mfe_pct * ((profile.mfe_soft_multiplier + profile.mfe_hard_multiplier) / 2)))
    )
    no_signal = (
        confidence < 0.32
        or pattern.textbook_similarity < 0.40
        or recency_score < 0.15
        or sample_reliability < 0.16
        or (data_quality < 0.60 and confidence < 0.74)
        or reward_risk_ratio < 1.15
        or headroom_score < 0.18
        or edge_score < 0.22
        or formation_quality < 0.34
        or pattern.variant_fit < 0.42
        or (pattern.state == "forming" and pattern.textbook_similarity < 0.58 and completion_proximity < 0.56)
        or (unrealistic_target and pattern.state in {"forming", "armed"} and confidence < 0.82)
    )
    no_signal_reason = (
        ""
        if not no_signal
        else "패턴 품질, 목표까지 남은 여지, 데이터 품질, 백테스트 edge 중 하나 이상이 기준에 못 미쳐 보수적으로 No Signal로 분류했습니다."
    )

    if no_signal:
        no_signal_reason = "패턴 품질, 목표까지 남은 거리, 데이터 신뢰도, 백테스트 edge 중 하나 이상이 기준을 못 채워 보수적으로 No Signal로 분류했습니다."
    cap = _probability_cap(
        pattern=pattern,
        timeframe=timeframe,
        no_signal=no_signal,
        reward_risk_ratio=reward_risk_ratio,
        headroom_score=headroom_score,
        target_distance_pct=target_distance_pct,
        avg_mfe_pct=avg_mfe_pct,
        edge_score=edge_score,
        confidence=confidence,
        sample_reliability=sample_reliability,
    )
    p_up, p_down = _apply_directional_cap(p_up, p_down, cap)

    return ProbabilityOutput(
        p_up=round(p_up, 3),
        p_down=round(p_down, 3),
        textbook_similarity=pattern.textbook_similarity,
        pattern_confirmation_score=round(pattern_confirmation, 3),
        confidence=round(confidence, 3),
        entry_score=round(entry_score, 3),
        completion_proximity=round(completion_proximity, 3),
        recency_score=round(recency_score, 3),
        reward_risk_ratio=round(reward_risk_ratio, 3),
        headroom_score=round(headroom_score, 3),
        target_distance_pct=round(target_distance_pct, 4),
        stop_distance_pct=round(stop_distance_pct, 4),
        avg_mfe_pct=round(avg_mfe_pct, 4),
        avg_mae_pct=round(avg_mae_pct, 4),
        avg_bars_to_outcome=round(avg_bars_to_outcome, 2),
        historical_edge_score=round(edge_score, 3),
        no_signal_flag=no_signal,
        no_signal_reason=no_signal_reason,
        reason_summary=summary,
        sample_size=sample_size,
        empirical_win_rate=round(posterior_success_rate, 3),
        sample_reliability=round(sample_reliability, 3),
    )
