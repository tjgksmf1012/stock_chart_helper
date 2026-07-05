"""
Probability engine for pattern-based scoring.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any

from .pattern_engine import PatternResult, pattern_direction_is_bullish
from .probability_calibration import calibrate_probability
from .probability_model import predict_directional_probability
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

_STATE_LABELS_KR: dict[str, str] = {
    "forming": "진행 중",
    "armed": "돌파 직전",
    "confirmed": "돌파 완료",
    "invalidated": "패턴 실패",
    "played_out": "익절 기준가 도달",
}

_PATTERN_NAMES_KR: dict[str, str] = {
    "double_bottom": "이중 바닥",
    "double_top": "이중 천장",
    "head_and_shoulders": "헤드앤숄더",
    "inverse_head_and_shoulders": "역 헤드앤숄더",
    "ascending_triangle": "상승 삼각형",
    "descending_triangle": "하강 삼각형",
    "symmetric_triangle": "대칭 삼각형",
    "rectangle": "직사각형 박스",
    "vcp": "VCP",
    "cup_and_handle": "컵앤핸들",
    "rounding_bottom": "원형 바닥",
    "momentum_breakout": "모멘텀 브레이크아웃",
}


def _rule_engine_prob(pattern: PatternResult) -> tuple[float, float]:
    similarity = pattern.textbook_similarity
    base_up = 0.50
    base_down = 0.50
    formation_quality = _formation_quality(pattern)

    bullish = pattern_direction_is_bullish(pattern)
    if bullish:
        base_up = 0.55 + similarity * 0.20
        base_up = 0.5 + (base_up - 0.5) * (0.40 + 0.60 * formation_quality)
        base_down = 1 - base_up
    else:
        base_down = 0.55 + similarity * 0.20
        base_down = 0.5 + (base_down - 0.5) * (0.40 + 0.60 * formation_quality)
        base_up = 1 - base_down

    if pattern.state == "confirmed":
        if bullish:
            base_up = min(0.86, base_up * 1.08)
            base_down = 1 - base_up
        else:
            base_down = min(0.86, base_down * 1.08)
            base_up = 1 - base_down
    elif pattern.state == "armed":
        if bullish:
            base_up = min(0.80, base_up * 1.03)
            base_down = 1 - base_up
        else:
            base_down = min(0.80, base_down * 1.03)
            base_up = 1 - base_down

    return base_up, base_down


def _formation_quality(pattern: PatternResult) -> float:
    if pattern.state in ("forming", "armed"):
        # Mirrors pattern_engine._formation_quality_score: breakout/retest quality are
        # undefined pre-breakout, so scoring them here would structurally cap forming/armed
        # patterns low regardless of how well-formed the setup actually is.
        return max(
            0.0,
            min(
                1.0,
                0.36 * pattern.leg_balance_fit
                + 0.32 * pattern.reversal_energy_fit
                + 0.20 * pattern.variant_fit
                + 0.12 * pattern.candlestick_confirmation_fit,
            ),
        )
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


def _shrink_toward_even(raw: float) -> float:
    # Linear shrink of a probability toward 0.5 — conservative regularization so the
    # blend never over-commits. (Not a logistic transform, despite the old name.)
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
    if pattern_direction_is_bullish(pattern):
        return posterior_success_rate, 1 - posterior_success_rate
    return 1 - posterior_success_rate, posterior_success_rate


def _historical_edge(avg_mfe_pct: float, avg_mae_pct: float, avg_bars_to_outcome: float, sample_size: int) -> float:
    rr = avg_mfe_pct / max(avg_mae_pct, 0.01)
    rr_score = max(0.0, min(1.0, rr / 2.5))
    mfe_score = max(0.0, min(1.0, avg_mfe_pct / 0.18))
    expected_bars = 18.0 if sample_size >= 20 else 10.0 if sample_size >= 10 else 6.0
    speed_score = max(0.0, min(1.0, 1 - (avg_bars_to_outcome / max(expected_bars, 1.0))))
    return max(0.0, min(1.0, 0.45 * rr_score + 0.30 * mfe_score + 0.25 * speed_score))


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
        # A well-formed setup (tight, symmetric legs + strong reversal energy) shouldn't be
        # capped identically to a weak one just because it hasn't broken out yet — let quality
        # earn up to half the gap toward the armed-state cap.
        quality_bonus = (profile.armed_direction_cap - profile.forming_direction_cap) * 0.5 * _formation_quality(pattern)
        cap = min(cap, profile.forming_direction_cap + quality_bonus)
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
    pattern_name = _PATTERN_NAMES_KR.get(pattern.pattern_type, pattern.pattern_type)
    state_kr = _STATE_LABELS_KR.get(pattern.state, pattern.state)
    return (
        f"{pattern_name} 패턴 / 교과서 유사도 {pattern.textbook_similarity:.0%} / "
        f"상태 {state_kr} / 완성 임박도 {completion_proximity:.0%} / "
        f"신호 신선도 {recency_score:.0%} / 표본 {sample_text} / "
        f"기대 손익비 {reward_risk_ratio:.2f} / 목표까지 여지 {target_distance_pct:.1%} / "
        f"평균 MFE {avg_mfe_pct:.1%} / 평균 MAE {avg_mae_pct:.1%} / "
        f"평균 결과 바 수 {avg_bars_to_outcome:.1f} / 백테스트 우위 {edge_score:.0%} / "
        f"보정 승률 {posterior_success_rate:.0%} / 표본 신뢰도 {sample_reliability:.0%} / "
        f"신뢰도 {confidence:.0%}"
    )


def _apply_directional_cap(p_up: float, p_down: float, cap: float) -> tuple[float, float]:
    if p_up >= p_down and p_up > cap:
        return cap, 1 - cap
    if p_down > p_up and p_down > cap:
        return 1 - cap, cap
    return p_up, p_down


def compute_probability(pattern: PatternResult, **kwargs: Any) -> ProbabilityOutput:
    output, _ = _compute_probability_impl(pattern, **kwargs)
    return output


def compute_probability_with_features(
    pattern: PatternResult, **kwargs: Any
) -> tuple[ProbabilityOutput, dict[str, float] | None]:
    """compute_probability()와 완전히 같은 계산이지만, p_up/p_down을 섞을 때 쓴
    10개 방향정렬 하위 점수(rule/empirical/confirmation/volume/...)를 함께 반환한다.

    scripts/fit_probability_model.py가 이 하위 점수들을 (특징, 승패) 학습
    데이터로 모아서 로지스틱 회귀를 학습하는 데 쓴다 — 지금의 감으로 정한
    가중치 합(0.25, 0.23, 0.13...)이 실제로 변별력이 있는지 데이터로
    검증하기 위해서다.
    """
    return _compute_probability_impl(pattern, **kwargs)


def _compute_probability_impl(
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
) -> tuple[ProbabilityOutput, dict[str, float] | None]:
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
            no_signal_reason=f"패턴 상태가 이미 {_STATE_LABELS_KR.get(pattern.state, pattern.state)}로 판정되었습니다.",
            reason_summary=f"{_PATTERN_NAMES_KR.get(pattern.pattern_type, pattern.pattern_type)} 패턴은 이미 {_STATE_LABELS_KR.get(pattern.state, pattern.state)} 상태라 현재 활성 진입 신호로 보지 않습니다.",
            **base_kwargs,
        ), None

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
        ), None

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

    # rule_* and empirical_* already encode the pattern's direction. The remaining
    # terms measure how strong/reliable the signal is, not which way it points, so
    # they must reinforce the pattern's *own* direction. For a bullish pattern this
    # is identical to "higher == more up"; for a bearish pattern it mirrors, so a
    # well-formed double top correctly pushes p_down instead of p_up.
    toward_up = 1.0 if pattern_direction_is_bullish(pattern) else 0.0

    def _dir(quality: float) -> tuple[float, float]:
        up = toward_up * quality + (1 - toward_up) * (1 - quality)
        return up, 1 - up

    conf_up, conf_down = _dir(pattern_confirmation)
    volume_up, volume_down = _dir(pattern.volume_context_fit)
    regime_up, regime_down = _dir(regime_match)
    comp_up, comp_down = _dir(completion_proximity)
    rec_up, rec_down = _dir(recency_score)
    dq_up, dq_down = _dir(data_quality)
    rr_up, rr_down = _dir(rr_score)
    edge_up, edge_down = _dir(edge_score)

    # 학습 데이터(collect_symbol_pairs)의 (predicted, won)은 "패턴 자체 방향이
    # 이겼는가" 기준이라, 여기 특징도 같은 기준(own-direction)으로 맞춰야 한다.
    # _up 값은 방향에 따라 의미가 뒤집힌다 — bullish면 rule_up=자기 방향 확신도지만
    # bearish면 rule_up=반대 방향 확신도(=1-자기 방향)다. rule_down/empirical_down도
    # 마찬가지로 각각 own-direction 값을 골라야 한다.
    bullish = toward_up >= 0.5
    features = {
        "rule": rule_up if bullish else rule_down,
        "empirical": empirical_up if bullish else empirical_down,
        "confirmation": conf_up if bullish else conf_down,
        "volume": volume_up if bullish else volume_down,
        "regime": regime_up if bullish else regime_down,
        "completion": comp_up if bullish else comp_down,
        "recency": rec_up if bullish else rec_down,
        "data_quality": dq_up if bullish else dq_down,
        "reward_risk": rr_up if bullish else rr_down,
        "edge": edge_up if bullish else edge_down,
    }

    # scripts/fit_probability_model.py로 학습된 모델이 있으면 감으로 정한 가중치
    # 합 대신 그걸 쓴다 — 없으면(기본 상태) None이 반환되어 기존 공식 그대로
    # 동작한다(무보정과 동일한 안전한 폴백). 모델 출력은 own-direction 확률이므로
    # p_up_raw/p_down_raw(항상 "실제 위/아래" 기준) 공간으로 다시 변환해야 한다.
    model_own_direction_p = predict_directional_probability(features)
    if model_own_direction_p is not None:
        if bullish:
            p_up_raw = model_own_direction_p
            p_down_raw = 1.0 - model_own_direction_p
        else:
            p_down_raw = model_own_direction_p
            p_up_raw = 1.0 - model_own_direction_p
    else:
        p_up_raw = (
            0.25 * rule_up
            + 0.23 * empirical_up
            + 0.13 * conf_up
            + 0.05 * volume_up
            + 0.08 * regime_up
            + 0.07 * comp_up
            + 0.06 * rec_up
            + 0.05 * dq_up
            + 0.04 * rr_up
            + 0.04 * edge_up
        )
        p_down_raw = (
            0.25 * rule_down
            + 0.23 * empirical_down
            + 0.13 * conf_down
            + 0.05 * volume_down
            + 0.08 * regime_down
            + 0.07 * comp_down
            + 0.06 * rec_down
            + 0.05 * dq_down
            + 0.04 * rr_down
            + 0.04 * edge_down
        )

    p_up = _shrink_toward_even(p_up_raw)
    p_down = _shrink_toward_even(p_down_raw)
    total_prob = max(p_up + p_down, 1e-9)
    p_up, p_down = p_up / total_prob, p_down / total_prob

    # 사후 확률 보정 — "이 휴리스틱이 X%라고 할 때 실제 승률은 몇 %였나"를 과거
    # 데이터로 학습한 매핑(scripts/fit_probability_calibration.py)이 있으면 적용.
    # 매핑이 없으면 calibrate_probability()가 원값을 그대로 돌려주므로 무보정과
    # 동일하게 동작한다. 패턴이 가리키는 방향(taken direction)의 확률만 보정하고
    # 반대쪽은 1-보정값으로 재구성해 두 값의 합이 항상 1을 유지하게 한다.
    if toward_up >= 0.5:
        p_up = calibrate_probability(p_up)
        p_down = 1.0 - p_up
    else:
        p_down = calibrate_probability(p_down)
        p_up = 1.0 - p_down

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
    ), features
