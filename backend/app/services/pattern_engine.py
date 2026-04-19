"""
Chart pattern detection engine.

Implements Grade-A structural patterns:
  - Double Bottom (W)
  - Double Top (M)
  - Head and Shoulders (H&S)
  - Inverse Head and Shoulders
  - Ascending / Descending / Symmetric Triangle
  - Rectangle (Box)
  - Rising / Falling Channel

Pattern state lifecycle: FORMING → ARMED → CONFIRMED | INVALIDATED → PLAYED_OUT

TextbookSimilarity = weighted blend of geometry, swing structure, volume context,
volatility contraction, regime fit, breakout quality, and retest quality.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal
import numpy as np
import pandas as pd

from .swing_points import SwingPoint, get_significant_swings, alternating_swings

PatternType = Literal[
    "double_bottom", "double_top",
    "head_and_shoulders", "inverse_head_and_shoulders",
    "ascending_triangle", "descending_triangle", "symmetric_triangle",
    "rectangle",
    "rising_channel", "falling_channel",
    "cup_and_handle",
    "rounding_bottom",
    "vcp",
]


@dataclass
class PatternResult:
    pattern_type: PatternType
    state: str          # forming | armed | confirmed | invalidated | played_out
    grade: str          # A | B | C
    start_dt: datetime
    end_dt: datetime | None
    variant: str | None = None

    # key price levels
    neckline: float | None = None
    invalidation_level: float | None = None
    target_level: float | None = None

    # scores (0.0 – 1.0)
    geometry_fit: float = 0.0
    swing_structure_fit: float = 0.0
    volume_context_fit: float = 0.0
    volatility_context_fit: float = 0.0
    regime_fit: float = 0.0
    leg_balance_fit: float = 0.5
    reversal_energy_fit: float = 0.5
    variant_fit: float = 0.5
    breakout_quality_fit: float = 0.0
    retest_quality_fit: float = 0.0
    candlestick_confirmation_fit: float = 0.5
    candlestick_label: str | None = None
    candlestick_note: str | None = None
    textbook_similarity: float = 0.0

    key_points: list[dict] = field(default_factory=list)
    is_provisional: bool = True


def _compute_textbook_similarity(r: PatternResult) -> float:
    return (
        0.25 * r.geometry_fit
        + 0.14 * r.swing_structure_fit
        + 0.10 * r.volume_context_fit
        + 0.07 * r.volatility_context_fit
        + 0.07 * r.regime_fit
        + 0.08 * r.leg_balance_fit
        + 0.07 * r.reversal_energy_fit
        + 0.03 * r.variant_fit
        + 0.10 * r.breakout_quality_fit
        + 0.06 * r.retest_quality_fit
        + 0.03 * r.candlestick_confirmation_fit
    )


def _formation_quality_score(r: PatternResult) -> float:
    return float(
        np.clip(
            0.25 * r.leg_balance_fit
            + 0.22 * r.reversal_energy_fit
            + 0.19 * r.breakout_quality_fit
            + 0.16 * r.retest_quality_fit
            + 0.10 * r.variant_fit
            + 0.08 * r.candlestick_confirmation_fit,
            0.0,
            1.0,
        )
    )


def _finalize_textbook_similarity(r: PatternResult) -> float:
    raw_similarity = _compute_textbook_similarity(r)
    formation_quality = _formation_quality_score(r)

    cap = 0.50 + 0.44 * formation_quality
    if r.state == "forming":
        cap -= 0.10
    elif r.state == "armed":
        cap -= 0.04

    adjusted = raw_similarity
    if formation_quality < 0.38:
        adjusted *= 0.84
    elif formation_quality < 0.52:
        adjusted *= 0.92

    return round(float(np.clip(min(adjusted, cap), 0.0, 1.0)), 3)


def _volume_context_score(df: pd.DataFrame, start_idx: int, end_idx: int) -> float:
    if "volume" not in df.columns or end_idx - start_idx < 8:
        return 0.5
    formation = pd.to_numeric(df["volume"].iloc[start_idx:end_idx], errors="coerce").dropna()
    if len(formation) < 6:
        return 0.5

    split = max(2, len(formation) // 3)
    early = formation.iloc[:split].mean()
    middle = formation.iloc[split: len(formation) - split].mean() if len(formation) > split * 2 else formation.iloc[split:].mean()
    late = formation.iloc[-split:].mean()
    if early <= 0:
        return 0.5

    contraction_1 = 1 - (middle / max(early, 1.0))
    contraction_2 = 1 - (late / max(middle, 1.0))
    contraction_score = np.clip(0.5 + 0.35 * contraction_1 + 0.25 * contraction_2, 0.0, 1.0)
    return float(round(contraction_score, 3))


def _symmetry_score(v1: float, v2: float) -> float:
    """How symmetric are two price levels? Returns 0-1."""
    if max(v1, v2) == 0:
        return 0.0
    diff_ratio = abs(v1 - v2) / max(v1, v2)
    return float(max(0.0, 1.0 - diff_ratio * 5))


def _safe_ratio(numerator: float, denominator: float, default: float = 0.0) -> float:
    if denominator == 0:
        return default
    return numerator / denominator


def _time_symmetry_score(span_a: int, span_b: int) -> float:
    if span_a <= 0 or span_b <= 0:
        return 0.35
    diff_ratio = abs(span_a - span_b) / max(span_a, span_b)
    return float(np.clip(1.0 - diff_ratio * 1.6, 0.0, 1.0))


def _leg_balance_score(price_a: float, price_b: float, span_a: int, span_b: int) -> float:
    price_score = _symmetry_score(price_a, price_b)
    time_score = _time_symmetry_score(span_a, span_b)
    return round(float(np.clip(0.6 * price_score + 0.4 * time_score, 0.0, 1.0)), 3)


def _reversal_energy_score(
    df: pd.DataFrame,
    reference_idx: int,
    pivot_idx: int,
    confirm_idx: int,
    bullish: bool,
) -> float:
    closes = pd.to_numeric(df["close"], errors="coerce")
    if reference_idx < 0 or pivot_idx <= reference_idx or confirm_idx <= pivot_idx:
        return 0.45

    ref_price = float(closes.iloc[reference_idx])
    pivot_price = float(closes.iloc[pivot_idx])
    confirm_price = float(closes.iloc[min(confirm_idx, len(closes) - 1)])

    left_span = max(1, pivot_idx - reference_idx)
    right_span = max(1, confirm_idx - pivot_idx)

    if bullish:
        decline_rate = max(0.0, _safe_ratio(ref_price - pivot_price, max(ref_price, 1.0)) / left_span)
        rebound_rate = max(0.0, _safe_ratio(confirm_price - pivot_price, max(pivot_price, 1.0)) / right_span)
    else:
        decline_rate = max(0.0, _safe_ratio(pivot_price - ref_price, max(ref_price, 1.0)) / left_span)
        rebound_rate = max(0.0, _safe_ratio(pivot_price - confirm_price, max(pivot_price, 1.0)) / right_span)

    if decline_rate <= 0 and rebound_rate <= 0:
        return 0.45

    slope_ratio = rebound_rate / max(decline_rate, 1e-6)
    velocity_score = float(np.clip((slope_ratio - 0.65) / 0.85, 0.0, 1.0))
    impulse_score = float(np.clip(rebound_rate / 0.012, 0.0, 1.0))
    return round(float(np.clip(0.65 * velocity_score + 0.35 * impulse_score, 0.0, 1.0)), 3)


def _pivot_shape_profile(
    df: pd.DataFrame,
    pivot_idx: int,
    pivot_kind: Literal["low", "high"],
    left_boundary: int | None = None,
    right_boundary: int | None = None,
) -> dict[str, float | str]:
    if pivot_idx < 0 or pivot_idx >= len(df):
        return {"shape": "hybrid", "adam_score": 0.5, "eve_score": 0.5}

    window_radius = 6
    start = max(0, left_boundary if left_boundary is not None else pivot_idx - window_radius)
    end = min(len(df) - 1, right_boundary if right_boundary is not None else pivot_idx + window_radius)
    if start >= end:
        start = max(0, pivot_idx - window_radius)
        end = min(len(df) - 1, pivot_idx + window_radius)
    pivot_pos = pivot_idx - start
    window = df.iloc[start : end + 1].copy()

    if pivot_kind == "low":
        series = pd.to_numeric(window["low"], errors="coerce")
        pivot_price = float(pd.to_numeric(df["low"], errors="coerce").iloc[pivot_idx])
    else:
        series = pd.to_numeric(window["high"], errors="coerce")
        pivot_price = float(pd.to_numeric(df["high"], errors="coerce").iloc[pivot_idx])

    if not np.isfinite(pivot_price) or pivot_price <= 0:
        return {"shape": "hybrid", "adam_score": 0.5, "eve_score": 0.5}

    distance_ratio = (series - pivot_price).abs() / pivot_price
    near_mask = (distance_ratio <= 0.012).tolist()

    left = pivot_pos
    right = pivot_pos
    while left - 1 >= 0 and near_mask[left - 1]:
        left -= 1
    while right + 1 < len(near_mask) and near_mask[right + 1]:
        right += 1
    pivot_width = right - left + 1
    linger_ratio = float(sum(1 for flag in near_mask if flag) / max(len(near_mask), 1))
    width_score = float(np.clip((pivot_width - 1) / 4.0, 0.0, 1.0))
    linger_score = float(np.clip((linger_ratio - 0.12) / 0.30, 0.0, 1.0))
    total_span = max(1, end - start)
    span_score = float(np.clip((total_span - 7) / 16.0, 0.0, 1.0))
    shortness_score = float(np.clip((11 - total_span) / 8.0, 0.0, 1.0))

    closes = pd.to_numeric(df["close"], errors="coerce")
    lookback_idx = max(0, pivot_idx - 3)
    lookahead_idx = min(len(df) - 1, pivot_idx + 3)
    bars_left = max(1, pivot_idx - lookback_idx)
    bars_right = max(1, lookahead_idx - pivot_idx)

    left_ref = float(closes.iloc[lookback_idx])
    right_ref = float(closes.iloc[lookahead_idx])
    if pivot_kind == "low":
        left_rate = max(0.0, _safe_ratio(left_ref - pivot_price, max(left_ref, 1.0)) / bars_left)
        right_rate = max(0.0, _safe_ratio(right_ref - pivot_price, max(pivot_price, 1.0)) / bars_right)
    else:
        left_rate = max(0.0, _safe_ratio(pivot_price - left_ref, max(left_ref, 1.0)) / bars_left)
        right_rate = max(0.0, _safe_ratio(pivot_price - right_ref, max(pivot_price, 1.0)) / bars_right)

    steepness = float(np.clip(((left_rate + right_rate) / 2.0) / 0.02, 0.0, 1.0))
    adam_score = float(
        np.clip(
            0.34 * steepness + 0.24 * (1.0 - width_score) + 0.18 * (1.0 - linger_score) + 0.24 * shortness_score,
            0.0,
            1.0,
        )
    )
    eve_score = float(
        np.clip(
            0.30 * width_score + 0.24 * linger_score + 0.18 * (1.0 - steepness) + 0.28 * span_score,
            0.0,
            1.0,
        )
    )

    if adam_score >= eve_score + 0.06:
        shape = "adam"
    elif eve_score >= adam_score + 0.06:
        shape = "eve"
    else:
        shape = "hybrid"

    return {
        "shape": shape,
        "adam_score": round(adam_score, 3),
        "eve_score": round(eve_score, 3),
    }


def _double_pattern_variant(
    first_shape: str,
    second_shape: str,
    bullish: bool,
) -> tuple[str, float]:
    variant = f"{first_shape}_{second_shape}"
    if bullish:
        first_bonus = {"adam": 0.16, "hybrid": 0.12, "eve": 0.10}
        second_bonus = {"eve": 0.22, "hybrid": 0.12, "adam": 0.05}
    else:
        first_bonus = {"eve": 0.16, "hybrid": 0.12, "adam": 0.08}
        second_bonus = {"adam": 0.22, "hybrid": 0.12, "eve": 0.05}

    score = 0.56 + first_bonus.get(first_shape, 0.10) + second_bonus.get(second_shape, 0.10)
    return variant, round(float(np.clip(score, 0.0, 1.0)), 3)


def _breakout_index(df: pd.DataFrame, level: float, start_idx: int, bullish: bool, threshold: float = 0.005) -> int | None:
    closes = pd.to_numeric(df["close"], errors="coerce")
    for idx in range(max(0, start_idx), len(df)):
        close = float(closes.iloc[idx])
        if bullish and close >= level * (1 + threshold):
            return idx
        if not bullish and close <= level * (1 - threshold):
            return idx
    return None


def _breakout_quality_score(df: pd.DataFrame, breakout_idx: int | None, level: float, bullish: bool) -> float:
    if breakout_idx is None or breakout_idx <= 0 or breakout_idx >= len(df):
        return 0.35

    close = float(df["close"].iloc[breakout_idx])
    volume = pd.to_numeric(df["volume"], errors="coerce")
    recent_volume = volume.iloc[max(0, breakout_idx - 20):breakout_idx].dropna()
    breakout_volume = float(volume.iloc[breakout_idx]) if pd.notna(volume.iloc[breakout_idx]) else 0.0
    volume_ratio = breakout_volume / max(float(recent_volume.mean()) if not recent_volume.empty else breakout_volume or 1.0, 1.0)
    volume_score = float(np.clip((volume_ratio - 0.8) / 1.0, 0.0, 1.0))

    if bullish:
        close_strength = _safe_ratio(close - level, level, default=0.0)
    else:
        close_strength = _safe_ratio(level - close, level, default=0.0)
    close_score = float(np.clip(close_strength / 0.04, 0.0, 1.0))
    return round(float(np.clip(0.55 * close_score + 0.45 * volume_score, 0.0, 1.0)), 3)


def _retest_quality_score(df: pd.DataFrame, breakout_idx: int | None, level: float, bullish: bool) -> float:
    if breakout_idx is None or breakout_idx >= len(df) - 1:
        return 0.45

    window = df.iloc[breakout_idx + 1:min(len(df), breakout_idx + 9)].copy()
    if window.empty:
        return 0.55

    closes = pd.to_numeric(window["close"], errors="coerce")
    highs = pd.to_numeric(window["high"], errors="coerce")
    lows = pd.to_numeric(window["low"], errors="coerce")

    if bullish:
        deepest_pullback = max(0.0, _safe_ratio(level - float(lows.min()), level, default=0.0))
        hold_score = float(np.clip(1.0 - deepest_pullback / 0.03, 0.0, 1.0))
        close_hold = float(np.clip((float(closes.iloc[-1]) - level) / max(level * 0.03, 1.0), 0.0, 1.0))
        revisit = abs(float(lows.min()) - level) / max(level, 1.0)
    else:
        deepest_pullback = max(0.0, _safe_ratio(float(highs.max()) - level, level, default=0.0))
        hold_score = float(np.clip(1.0 - deepest_pullback / 0.03, 0.0, 1.0))
        close_hold = float(np.clip((level - float(closes.iloc[-1])) / max(level * 0.03, 1.0), 0.0, 1.0))
        revisit = abs(float(highs.max()) - level) / max(level, 1.0)

    revisit_score = float(np.clip(1.0 - revisit / 0.03, 0.0, 1.0))
    return round(float(np.clip(0.45 * hold_score + 0.30 * close_hold + 0.25 * revisit_score, 0.0, 1.0)), 3)


def _volatility_context_score(df: pd.DataFrame, start_idx: int, end_idx: int) -> float:
    if end_idx - start_idx < 10:
        return 0.5

    window = df.iloc[start_idx:end_idx].copy()
    highs = pd.to_numeric(window["high"], errors="coerce")
    lows = pd.to_numeric(window["low"], errors="coerce")
    closes = pd.to_numeric(window["close"], errors="coerce")
    prev_close = closes.shift(1)
    tr = pd.concat(
        [
            highs - lows,
            (highs - prev_close).abs(),
            (lows - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1).dropna()

    if len(tr) < 8:
        return 0.5

    split = max(3, len(tr) // 3)
    early_atr = tr.iloc[:split].mean()
    late_atr = tr.iloc[-split:].mean()
    if early_atr <= 0:
        return 0.5

    contraction = 1 - (late_atr / early_atr)
    return float(round(np.clip(0.5 + contraction * 0.55, 0.0, 1.0), 3))


def _tight_range_score(df: pd.DataFrame, start_idx: int, end_idx: int) -> float:
    if end_idx <= start_idx:
        return 0.4
    window = df.iloc[start_idx : end_idx + 1].copy()
    highs = pd.to_numeric(window["high"], errors="coerce").dropna()
    lows = pd.to_numeric(window["low"], errors="coerce").dropna()
    closes = pd.to_numeric(window["close"], errors="coerce").dropna()
    if highs.empty or lows.empty or closes.empty:
        return 0.4
    span_ratio = (float(highs.max()) - float(lows.min())) / max(float(closes.iloc[-1]), 1.0)
    if span_ratio <= 0.025:
        return 1.0
    if span_ratio <= 0.04:
        return 0.84
    if span_ratio <= 0.06:
        return 0.66
    if span_ratio <= 0.08:
        return 0.48
    return 0.28


def _sequence_contraction_score(depths: list[float]) -> float:
    if len(depths) < 2:
        return 0.45
    pair_scores: list[float] = []
    for prev, curr in zip(depths, depths[1:]):
        if prev <= 0:
            continue
        contraction = 1.0 - (curr / prev)
        pair_scores.append(float(np.clip((contraction + 0.05) / 0.55, 0.0, 1.0)))
    if not pair_scores:
        return 0.45
    return round(float(np.clip(sum(pair_scores) / len(pair_scores), 0.0, 1.0)), 3)


def _grade_from_quality(similarity: float, breakout_quality: float, retest_quality: float, volume_context: float) -> str:
    weighted = 0.55 * similarity + 0.20 * breakout_quality + 0.15 * retest_quality + 0.10 * volume_context
    if weighted >= 0.76 and breakout_quality >= 0.55:
        return "A"
    if weighted >= 0.58:
        return "B"
    return "C"


def _normalize_state(state: str, breakout_quality: float, retest_quality: float) -> str:
    if state != "confirmed":
        return state
    if breakout_quality < 0.42:
        return "armed"
    if retest_quality < 0.28:
        return "armed"
    return state


def _body_size(open_price: float, close_price: float) -> float:
    return abs(close_price - open_price)


def _candle_range(high_price: float, low_price: float) -> float:
    return max(high_price - low_price, 1e-6)


def _bullish_engulfing(prev_row: pd.Series, row: pd.Series) -> bool:
    prev_open = float(prev_row["open"])
    prev_close = float(prev_row["close"])
    open_price = float(row["open"])
    close_price = float(row["close"])
    return (
        prev_close < prev_open
        and close_price > open_price
        and open_price <= prev_close
        and close_price >= prev_open
    )


def _bearish_engulfing(prev_row: pd.Series, row: pd.Series) -> bool:
    prev_open = float(prev_row["open"])
    prev_close = float(prev_row["close"])
    open_price = float(row["open"])
    close_price = float(row["close"])
    return (
        prev_close > prev_open
        and close_price < open_price
        and open_price >= prev_close
        and close_price <= prev_open
    )


def _hammer_like(row: pd.Series, bullish: bool) -> bool:
    open_price = float(row["open"])
    high_price = float(row["high"])
    low_price = float(row["low"])
    close_price = float(row["close"])
    candle_range = _candle_range(high_price, low_price)
    body = _body_size(open_price, close_price)
    lower_shadow = min(open_price, close_price) - low_price
    upper_shadow = high_price - max(open_price, close_price)
    if bullish:
        return lower_shadow >= body * 1.8 and upper_shadow <= candle_range * 0.25 and close_price >= open_price
    return upper_shadow >= body * 1.8 and lower_shadow <= candle_range * 0.25 and close_price <= open_price


def _strong_directional_close(row: pd.Series, bullish: bool) -> bool:
    open_price = float(row["open"])
    high_price = float(row["high"])
    low_price = float(row["low"])
    close_price = float(row["close"])
    candle_range = _candle_range(high_price, low_price)
    body = _body_size(open_price, close_price)
    close_location = (close_price - low_price) / candle_range
    if bullish:
        return close_price > open_price and body / candle_range >= 0.58 and close_location >= 0.72
    return close_price < open_price and body / candle_range >= 0.58 and close_location <= 0.28


def _candlestick_confirmation(df: pd.DataFrame, pattern: PatternResult) -> tuple[float, str, str]:
    if len(df) < 3:
        return 0.5, "neutral", "캔들 확인 정보가 아직 부족합니다."

    bullish = pattern.pattern_type in {
        "double_bottom",
        "inverse_head_and_shoulders",
        "ascending_triangle",
        "rectangle",
        "cup_and_handle",
        "rounding_bottom",
        "vcp",
    }
    bearish = pattern.pattern_type in {
        "double_top",
        "head_and_shoulders",
        "descending_triangle",
    }
    if not bullish and not bearish:
        return 0.5, "neutral", "캔들 확인 필터를 적용하지 않는 패턴입니다."

    recent = df.tail(3).reset_index(drop=True)
    prev_row = recent.iloc[-2]
    row = recent.iloc[-1]

    open_price = float(row["open"])
    high_price = float(row["high"])
    low_price = float(row["low"])
    close_price = float(row["close"])
    candle_range = _candle_range(high_price, low_price)
    body = _body_size(open_price, close_price)
    upper_shadow = high_price - max(open_price, close_price)
    lower_shadow = min(open_price, close_price) - low_price
    close_location = (close_price - low_price) / candle_range

    if bullish:
        positives = [
            _bullish_engulfing(prev_row, row),
            _hammer_like(row, bullish=True),
            _strong_directional_close(row, bullish=True),
            bool(float(recent.iloc[-1]["close"]) > float(recent.iloc[-2]["close"]) > float(recent.iloc[-3]["close"])),
        ]
        negatives = [
            _bearish_engulfing(prev_row, row),
            upper_shadow / candle_range >= 0.42 and close_location < 0.55,
            close_price < open_price and body / candle_range >= 0.45,
        ]
        raw = 0.5 + 0.12 * sum(1 for flag in positives if flag) - 0.14 * sum(1 for flag in negatives if flag)
        raw += 0.06 * np.clip(close_location - 0.55, -0.4, 0.4)
        raw += 0.04 * np.clip((lower_shadow - upper_shadow) / candle_range, -0.5, 0.5)
        score = float(np.clip(raw, 0.0, 1.0))
        if score >= 0.74:
            return round(score, 3), "bullish_confirmation", "최근 캔들이 돌파 확인형에 가깝고 종가 마감 강도도 양호합니다."
        if score <= 0.34:
            return round(score, 3), "bearish_rejection", "최근 캔들에서 윗꼬리 저항 또는 약한 종가 마감이 보여 추격 진입에 불리합니다."
        return round(score, 3), "mixed", "최근 캔들 흐름은 중립에 가깝고, 추가 확인 캔들이 더 필요합니다."

    positives = [
        _bearish_engulfing(prev_row, row),
        _hammer_like(row, bullish=False),
        _strong_directional_close(row, bullish=False),
        bool(float(recent.iloc[-1]["close"]) < float(recent.iloc[-2]["close"]) < float(recent.iloc[-3]["close"])),
    ]
    negatives = [
        _bullish_engulfing(prev_row, row),
        lower_shadow / candle_range >= 0.42 and close_location > 0.45,
        close_price > open_price and body / candle_range >= 0.45,
    ]
    raw = 0.5 + 0.12 * sum(1 for flag in positives if flag) - 0.14 * sum(1 for flag in negatives if flag)
    raw += 0.06 * np.clip(0.45 - close_location, -0.4, 0.4)
    raw += 0.04 * np.clip((upper_shadow - lower_shadow) / candle_range, -0.5, 0.5)
    score = float(np.clip(raw, 0.0, 1.0))
    if score >= 0.74:
        return round(score, 3), "bearish_confirmation", "최근 캔들이 하락 확인형에 가깝고 종가 마감 강도도 양호합니다."
    if score <= 0.34:
        return round(score, 3), "bullish_rejection", "최근 캔들에서 아래꼬리 방어 또는 강한 되받음이 보여 하락 추세 해석을 약하게 만듭니다."
    return round(score, 3), "mixed", "최근 캔들 흐름은 중립에 가깝고, 추가 확인 캔들이 더 필요합니다."


class PatternEngine:
    """
    Detects structural chart patterns from a price DataFrame.

    df must have: date (or datetime), open, high, low, close, volume
    """

    def detect_all(self, df: pd.DataFrame, regime_fit: float = 0.5) -> list[PatternResult]:
        if len(df) < 20:
            return []
        swings = alternating_swings(get_significant_swings(df))
        results: list[PatternResult] = []

        for detector in [
            self._detect_double_bottom,
            self._detect_double_top,
            self._detect_head_and_shoulders,
            self._detect_inverse_head_and_shoulders,
            self._detect_triangles,
            self._detect_vcp,
            self._detect_rectangle,
        ]:
            found = detector(df, swings, regime_fit)
            if found:
                results.extend(found)

        for result in results:
            candle_score, candle_label, candle_note = _candlestick_confirmation(df, result)
            result.candlestick_confirmation_fit = candle_score
            result.candlestick_label = candle_label
            result.candlestick_note = candle_note
            result.textbook_similarity = _finalize_textbook_similarity(result)

        return results

    # ── Double Bottom (W) ────────────────────────────────────────────────────

    def _detect_double_bottom(
        self, df: pd.DataFrame, swings: list[SwingPoint], regime_fit: float
    ) -> list[PatternResult]:
        lows = [s for s in swings if s.kind == "low"]
        highs = [s for s in swings if s.kind == "high"]
        results = []
        dates = df["date"].values if "date" in df.columns else df["datetime"].values

        for i in range(len(lows) - 1):
            L1, L2 = lows[i], lows[i + 1]
            # Find neckline high between the two lows
            mid_highs = [h for h in highs if L1.index < h.index < L2.index]
            if not mid_highs:
                continue
            neckline_swing = max(mid_highs, key=lambda h: h.price)
            neckline = neckline_swing.price

            price_sym = _symmetry_score(L1.price, L2.price)
            if price_sym < 0.6:
                continue

            # Second low must not be significantly lower than first
            low_diff = _safe_ratio(L2.price - L1.price, L1.price)
            if low_diff < -0.05:  # more than 5% lower = not W, possible downtrend
                continue

            # Determine state
            current_close = float(df["close"].iloc[-1])
            last_dt = pd.Timestamp(dates[-1]).to_pydatetime()
            if current_close >= neckline:
                state = "confirmed"
            elif current_close >= neckline * 0.98:
                state = "armed"
            else:
                state = "forming"

            invalidation = L2.price * 0.99
            target = neckline + (neckline - min(L1.price, L2.price))

            vol_score = _volume_context_score(df, L1.index, L2.index)
            volat_score = _volatility_context_score(df, L1.index, L2.index)
            left_span = max(1, neckline_swing.index - L1.index)
            right_span = max(1, L2.index - neckline_swing.index)
            leg_balance = _leg_balance_score(L1.price, L2.price, left_span, right_span)
            breakout_idx = _breakout_index(df, neckline, L2.index, bullish=True)
            reversal_energy = _reversal_energy_score(
                df,
                neckline_swing.index,
                L2.index,
                breakout_idx if breakout_idx is not None else len(df) - 1,
                bullish=True,
            )
            previous_highs = [h for h in highs if h.index < L1.index]
            next_highs = [h for h in highs if h.index > L2.index]
            first_left_boundary = previous_highs[-1].index if previous_highs else max(0, L1.index - left_span)
            second_right_boundary = (
                next_highs[0].index
                if next_highs
                else breakout_idx if breakout_idx is not None else min(len(df) - 1, L2.index + right_span)
            )
            first_shape = _pivot_shape_profile(
                df,
                L1.index,
                "low",
                left_boundary=first_left_boundary,
                right_boundary=neckline_swing.index,
            )
            second_shape = _pivot_shape_profile(
                df,
                L2.index,
                "low",
                left_boundary=neckline_swing.index,
                right_boundary=second_right_boundary,
            )
            variant, variant_fit = _double_pattern_variant(
                str(first_shape["shape"]),
                str(second_shape["shape"]),
                bullish=True,
            )
            geom_fit = (
                price_sym * 0.38
                + max(0, 1 - abs(low_diff) * 10) * 0.20
                + leg_balance * 0.18
                + reversal_energy * 0.16
                + variant_fit * 0.08
            )
            breakout_quality = _breakout_quality_score(df, breakout_idx, neckline, bullish=True)
            retest_quality = _retest_quality_score(df, breakout_idx, neckline, bullish=True)
            state = _normalize_state(state, breakout_quality, retest_quality)
            if state == "confirmed" and (leg_balance < 0.46 or reversal_energy < 0.44 or variant_fit < 0.66):
                state = "armed"
            elif state == "armed" and (leg_balance < 0.34 or reversal_energy < 0.30 or variant_fit < 0.58):
                state = "forming"
            grade = _grade_from_quality(geom_fit, breakout_quality, retest_quality, vol_score)

            r = PatternResult(
                pattern_type="double_bottom",
                state=state,
                grade=grade,
                start_dt=L1.datetime,
                end_dt=last_dt if state == "confirmed" else None,
                variant=variant,
                neckline=neckline,
                invalidation_level=invalidation,
                target_level=target,
                geometry_fit=round(geom_fit, 3),
                swing_structure_fit=round(min(1.0, (L2.index - L1.index) / 10), 3),
                volume_context_fit=round(vol_score, 3),
                volatility_context_fit=round(volat_score, 3),
                regime_fit=regime_fit,
                leg_balance_fit=leg_balance,
                reversal_energy_fit=reversal_energy,
                variant_fit=variant_fit,
                breakout_quality_fit=breakout_quality,
                retest_quality_fit=retest_quality,
                key_points=[
                    {"dt": L1.datetime.isoformat(), "price": L1.price, "type": "low1"},
                    {"dt": neckline_swing.datetime.isoformat(), "price": neckline, "type": "neckline"},
                    {"dt": L2.datetime.isoformat(), "price": L2.price, "type": "low2"},
                ],
                is_provisional=(state != "confirmed"),
            )
            r.textbook_similarity = _finalize_textbook_similarity(r)
            results.append(r)

        return results[-1:] if results else []  # return most recent only

    # ── Double Top (M) ───────────────────────────────────────────────────────

    def _detect_double_top(
        self, df: pd.DataFrame, swings: list[SwingPoint], regime_fit: float
    ) -> list[PatternResult]:
        highs = [s for s in swings if s.kind == "high"]
        lows = [s for s in swings if s.kind == "low"]
        results = []
        dates = df["date"].values if "date" in df.columns else df["datetime"].values

        for i in range(len(highs) - 1):
            H1, H2 = highs[i], highs[i + 1]
            mid_lows = [l for l in lows if H1.index < l.index < H2.index]
            if not mid_lows:
                continue
            neckline_swing = min(mid_lows, key=lambda l: l.price)
            neckline = neckline_swing.price

            price_sym = _symmetry_score(H1.price, H2.price)
            if price_sym < 0.6:
                continue

            high_diff = _safe_ratio(H2.price - H1.price, H1.price)
            if high_diff > 0.05:
                continue

            current_close = float(df["close"].iloc[-1])
            last_dt = pd.Timestamp(dates[-1]).to_pydatetime()
            if current_close <= neckline:
                state = "confirmed"
            elif current_close <= neckline * 1.02:
                state = "armed"
            else:
                state = "forming"

            invalidation = H2.price * 1.01
            target = neckline - (max(H1.price, H2.price) - neckline)

            vol_score = _volume_context_score(df, H1.index, H2.index)
            volat_score = _volatility_context_score(df, H1.index, H2.index)
            left_span = max(1, neckline_swing.index - H1.index)
            right_span = max(1, H2.index - neckline_swing.index)
            leg_balance = _leg_balance_score(H1.price, H2.price, left_span, right_span)
            breakout_idx = _breakout_index(df, neckline, H2.index, bullish=False)
            reversal_energy = _reversal_energy_score(
                df,
                neckline_swing.index,
                H2.index,
                breakout_idx if breakout_idx is not None else len(df) - 1,
                bullish=False,
            )
            previous_lows = [l for l in lows if l.index < H1.index]
            next_lows = [l for l in lows if l.index > H2.index]
            first_left_boundary = previous_lows[-1].index if previous_lows else max(0, H1.index - left_span)
            second_right_boundary = (
                next_lows[0].index
                if next_lows
                else breakout_idx if breakout_idx is not None else min(len(df) - 1, H2.index + right_span)
            )
            first_shape = _pivot_shape_profile(
                df,
                H1.index,
                "high",
                left_boundary=first_left_boundary,
                right_boundary=neckline_swing.index,
            )
            second_shape = _pivot_shape_profile(
                df,
                H2.index,
                "high",
                left_boundary=neckline_swing.index,
                right_boundary=second_right_boundary,
            )
            variant, variant_fit = _double_pattern_variant(
                str(first_shape["shape"]),
                str(second_shape["shape"]),
                bullish=False,
            )
            geom_fit = (
                price_sym * 0.38
                + max(0, 1 - abs(high_diff) * 10) * 0.20
                + leg_balance * 0.18
                + reversal_energy * 0.16
                + variant_fit * 0.08
            )
            breakout_quality = _breakout_quality_score(df, breakout_idx, neckline, bullish=False)
            retest_quality = _retest_quality_score(df, breakout_idx, neckline, bullish=False)
            state = _normalize_state(state, breakout_quality, retest_quality)
            if state == "confirmed" and (leg_balance < 0.46 or reversal_energy < 0.44 or variant_fit < 0.66):
                state = "armed"
            elif state == "armed" and (leg_balance < 0.34 or reversal_energy < 0.30 or variant_fit < 0.58):
                state = "forming"
            grade = _grade_from_quality(geom_fit, breakout_quality, retest_quality, vol_score)

            r = PatternResult(
                pattern_type="double_top",
                state=state,
                grade=grade,
                start_dt=H1.datetime,
                end_dt=last_dt if state == "confirmed" else None,
                variant=variant,
                neckline=neckline,
                invalidation_level=invalidation,
                target_level=target,
                geometry_fit=round(geom_fit, 3),
                swing_structure_fit=round(min(1.0, (H2.index - H1.index) / 10), 3),
                volume_context_fit=round(vol_score, 3),
                volatility_context_fit=round(volat_score, 3),
                regime_fit=regime_fit,
                leg_balance_fit=leg_balance,
                reversal_energy_fit=reversal_energy,
                variant_fit=variant_fit,
                breakout_quality_fit=breakout_quality,
                retest_quality_fit=retest_quality,
                key_points=[
                    {"dt": H1.datetime.isoformat(), "price": H1.price, "type": "high1"},
                    {"dt": neckline_swing.datetime.isoformat(), "price": neckline, "type": "neckline"},
                    {"dt": H2.datetime.isoformat(), "price": H2.price, "type": "high2"},
                ],
                is_provisional=(state != "confirmed"),
            )
            r.textbook_similarity = _finalize_textbook_similarity(r)
            results.append(r)

        return results[-1:] if results else []

    # ── Head and Shoulders ───────────────────────────────────────────────────

    def _detect_head_and_shoulders(
        self, df: pd.DataFrame, swings: list[SwingPoint], regime_fit: float
    ) -> list[PatternResult]:
        highs = [s for s in swings if s.kind == "high"]
        lows = [s for s in swings if s.kind == "low"]
        dates = df["date"].values if "date" in df.columns else df["datetime"].values

        for i in range(len(highs) - 2):
            LS, H, RS = highs[i], highs[i + 1], highs[i + 2]
            if H.price <= LS.price or H.price <= RS.price:
                continue
            shoulder_sym = _symmetry_score(LS.price, RS.price)
            if shoulder_sym < 0.5:
                continue

            left_lows = [l for l in lows if LS.index < l.index < H.index]
            right_lows = [l for l in lows if H.index < l.index < RS.index]
            if not left_lows or not right_lows:
                continue
            LN = min(left_lows, key=lambda l: l.price)
            RN = min(right_lows, key=lambda l: l.price)
            neckline = (LN.price + RN.price) / 2

            current_close = float(df["close"].iloc[-1])
            last_dt = pd.Timestamp(dates[-1]).to_pydatetime()
            if current_close <= neckline:
                state = "confirmed"
            elif current_close <= neckline * 1.02:
                state = "armed"
            else:
                state = "forming"

            invalidation = H.price * 1.01
            target = neckline - (H.price - neckline)

            vol_score = _volume_context_score(df, LS.index, RS.index)
            volat_score = _volatility_context_score(df, LS.index, RS.index)
            leg_balance = _leg_balance_score(LS.price, RS.price, H.index - LS.index, RS.index - H.index)
            breakout_idx = _breakout_index(df, neckline, RS.index, bullish=False)
            reversal_energy = _reversal_energy_score(
                df,
                H.index,
                RS.index,
                breakout_idx if breakout_idx is not None else len(df) - 1,
                bullish=False,
            )
            geom_fit = shoulder_sym * 0.5 + min(
                1.0,
                _safe_ratio(H.price - max(LS.price, RS.price), H.price) * 10,
            ) * 0.5
            breakout_quality = _breakout_quality_score(df, breakout_idx, neckline, bullish=False)
            retest_quality = _retest_quality_score(df, breakout_idx, neckline, bullish=False)
            state = _normalize_state(state, breakout_quality, retest_quality)
            if state == "confirmed" and (leg_balance < 0.42 or reversal_energy < 0.40):
                state = "armed"
            grade = _grade_from_quality(geom_fit, breakout_quality, retest_quality, vol_score)

            r = PatternResult(
                pattern_type="head_and_shoulders",
                state=state,
                grade=grade,
                start_dt=LS.datetime,
                end_dt=last_dt if state == "confirmed" else None,
                neckline=neckline,
                invalidation_level=invalidation,
                target_level=target,
                geometry_fit=round(geom_fit, 3),
                swing_structure_fit=round(shoulder_sym, 3),
                volume_context_fit=round(vol_score, 3),
                volatility_context_fit=round(volat_score, 3),
                regime_fit=regime_fit,
                leg_balance_fit=leg_balance,
                reversal_energy_fit=reversal_energy,
                breakout_quality_fit=breakout_quality,
                retest_quality_fit=retest_quality,
                key_points=[
                    {"dt": LS.datetime.isoformat(), "price": LS.price, "type": "left_shoulder"},
                    {"dt": H.datetime.isoformat(), "price": H.price, "type": "head"},
                    {"dt": RS.datetime.isoformat(), "price": RS.price, "type": "right_shoulder"},
                    {"dt": LN.datetime.isoformat(), "price": LN.price, "type": "left_neckline"},
                    {"dt": RN.datetime.isoformat(), "price": RN.price, "type": "right_neckline"},
                ],
                is_provisional=(state != "confirmed"),
            )
            r.textbook_similarity = _finalize_textbook_similarity(r)
            return [r]

        return []

    def _detect_inverse_head_and_shoulders(
        self, df: pd.DataFrame, swings: list[SwingPoint], regime_fit: float
    ) -> list[PatternResult]:
        lows = [s for s in swings if s.kind == "low"]
        highs = [s for s in swings if s.kind == "high"]
        dates = df["date"].values if "date" in df.columns else df["datetime"].values

        for i in range(len(lows) - 2):
            LS, H, RS = lows[i], lows[i + 1], lows[i + 2]
            if H.price >= LS.price or H.price >= RS.price:
                continue
            shoulder_sym = _symmetry_score(LS.price, RS.price)
            if shoulder_sym < 0.5:
                continue

            left_highs = [h for h in highs if LS.index < h.index < H.index]
            right_highs = [h for h in highs if H.index < h.index < RS.index]
            if not left_highs or not right_highs:
                continue
            LN = max(left_highs, key=lambda h: h.price)
            RN = max(right_highs, key=lambda h: h.price)
            neckline = (LN.price + RN.price) / 2

            current_close = float(df["close"].iloc[-1])
            last_dt = pd.Timestamp(dates[-1]).to_pydatetime()
            if current_close >= neckline:
                state = "confirmed"
            elif current_close >= neckline * 0.98:
                state = "armed"
            else:
                state = "forming"

            invalidation = H.price * 0.99
            target = neckline + (neckline - H.price)
            vol_score = _volume_context_score(df, LS.index, RS.index)
            volat_score = _volatility_context_score(df, LS.index, RS.index)
            leg_balance = _leg_balance_score(LS.price, RS.price, H.index - LS.index, RS.index - H.index)
            breakout_idx = _breakout_index(df, neckline, RS.index, bullish=True)
            reversal_energy = _reversal_energy_score(
                df,
                H.index,
                RS.index,
                breakout_idx if breakout_idx is not None else len(df) - 1,
                bullish=True,
            )
            geom_fit = shoulder_sym * 0.5 + min(
                1.0,
                _safe_ratio(min(LS.price, RS.price) - H.price, H.price) * 10,
            ) * 0.5
            breakout_quality = _breakout_quality_score(df, breakout_idx, neckline, bullish=True)
            retest_quality = _retest_quality_score(df, breakout_idx, neckline, bullish=True)
            state = _normalize_state(state, breakout_quality, retest_quality)
            if state == "confirmed" and (leg_balance < 0.42 or reversal_energy < 0.40):
                state = "armed"
            grade = _grade_from_quality(geom_fit, breakout_quality, retest_quality, vol_score)

            r = PatternResult(
                pattern_type="inverse_head_and_shoulders",
                state=state, grade=grade,
                start_dt=LS.datetime,
                end_dt=last_dt if state == "confirmed" else None,
                neckline=neckline, invalidation_level=invalidation, target_level=target,
                geometry_fit=round(geom_fit, 3),
                swing_structure_fit=round(shoulder_sym, 3),
                volume_context_fit=round(vol_score, 3),
                volatility_context_fit=round(volat_score, 3),
                regime_fit=regime_fit,
                leg_balance_fit=leg_balance,
                reversal_energy_fit=reversal_energy,
                breakout_quality_fit=breakout_quality,
                retest_quality_fit=retest_quality,
                key_points=[
                    {"dt": LS.datetime.isoformat(), "price": LS.price, "type": "left_shoulder"},
                    {"dt": H.datetime.isoformat(), "price": H.price, "type": "head"},
                    {"dt": RS.datetime.isoformat(), "price": RS.price, "type": "right_shoulder"},
                ],
                is_provisional=(state != "confirmed"),
            )
            r.textbook_similarity = _finalize_textbook_similarity(r)
            return [r]
        return []

    # ── Triangles ────────────────────────────────────────────────────────────

    def _detect_triangles(
        self, df: pd.DataFrame, swings: list[SwingPoint], regime_fit: float
    ) -> list[PatternResult]:
        highs = [s for s in swings if s.kind == "high"]
        lows = [s for s in swings if s.kind == "low"]
        results = []
        dates = df["date"].values if "date" in df.columns else df["datetime"].values

        if len(highs) < 2 or len(lows) < 2:
            return []

        # Use last 2-3 highs and lows
        h_series = highs[-3:]
        l_series = lows[-3:]

        high_descending = len(h_series) >= 2 and h_series[-1].price < h_series[0].price
        low_ascending = len(l_series) >= 2 and l_series[-1].price > l_series[0].price
        low_descending = len(l_series) >= 2 and l_series[-1].price < l_series[0].price
        high_flat = len(h_series) >= 2 and abs(h_series[-1].price - h_series[0].price) / h_series[0].price < 0.02

        current_close = float(df["close"].iloc[-1])
        last_dt = pd.Timestamp(dates[-1]).to_pydatetime()

        if high_descending and low_ascending:
            pattern_type = "symmetric_triangle"
            apex = (h_series[-1].price + l_series[-1].price) / 2
            state = "armed" if abs(current_close - apex) / apex < 0.03 else "forming"
            breakout_level = apex
            bullish_breakout = current_close >= apex
        elif high_flat and low_ascending:
            pattern_type = "ascending_triangle"
            resistance = sum(h.price for h in h_series) / len(h_series)
            state = "confirmed" if current_close > resistance * 1.005 else (
                "armed" if current_close > resistance * 0.99 else "forming"
            )
            breakout_level = resistance
            bullish_breakout = True
        elif high_descending and not low_ascending:
            pattern_type = "descending_triangle"
            support = sum(l.price for l in l_series) / len(l_series)
            state = "confirmed" if current_close < support * 0.995 else (
                "armed" if current_close < support * 1.01 else "forming"
            )
            breakout_level = support
            bullish_breakout = False
        else:
            return []

        start_dt = min(h_series[0].datetime, l_series[0].datetime)
        vol_score = _volume_context_score(df, min(h_series[0].index, l_series[0].index), len(df) - 1)
        volat_score = _volatility_context_score(df, min(h_series[0].index, l_series[0].index), len(df) - 1)
        breakout_idx = _breakout_index(df, breakout_level, max(h_series[-1].index, l_series[-1].index), bullish=bullish_breakout)
        breakout_quality = _breakout_quality_score(df, breakout_idx, breakout_level, bullish=bullish_breakout)
        retest_quality = _retest_quality_score(df, breakout_idx, breakout_level, bullish=bullish_breakout)
        state = _normalize_state(state, breakout_quality, retest_quality)
        grade = _grade_from_quality(0.65, breakout_quality, retest_quality, vol_score)

        r = PatternResult(
            pattern_type=pattern_type,
            state=state, grade=grade,
            start_dt=start_dt,
            end_dt=last_dt if state == "confirmed" else None,
            geometry_fit=0.65, swing_structure_fit=0.60,
            volume_context_fit=round(vol_score, 3),
            volatility_context_fit=round(volat_score, 3), regime_fit=regime_fit,
            leg_balance_fit=0.55,
            reversal_energy_fit=0.52,
            breakout_quality_fit=breakout_quality,
            retest_quality_fit=retest_quality,
            is_provisional=(state != "confirmed"),
        )
        r.textbook_similarity = _finalize_textbook_similarity(r)
        return [r]

    # ── Rectangle (Box) ─────────────────────────────────────────────────────

    def _detect_vcp(
        self, df: pd.DataFrame, swings: list[SwingPoint], regime_fit: float
    ) -> list[PatternResult]:
        if len(df) < 50:
            return []

        ordered = sorted(swings, key=lambda s: s.index)
        recent = [s for s in ordered if s.index >= max(0, len(df) - 140)]
        if len(recent) < 6:
            return []

        pullbacks: list[tuple[SwingPoint, SwingPoint, float]] = []
        for current, nxt in zip(recent, recent[1:]):
            if current.kind == "high" and nxt.kind == "low" and nxt.index > current.index:
                depth = _safe_ratio(current.price - nxt.price, current.price)
                if 0.015 <= depth <= 0.35:
                    pullbacks.append((current, nxt, depth))

        if len(pullbacks) < 3:
            return []

        segment = pullbacks[-3:]
        highs = [item[0] for item in segment]
        lows = [item[1] for item in segment]
        depths = [item[2] for item in segment]
        pivot = max(high.price for high in highs)
        high_tightness = float(
            np.clip(
                1.0 - ((max(high.price for high in highs) - min(high.price for high in highs)) / max(pivot, 1.0)) / 0.14,
                0.0,
                1.0,
            )
        )
        base_range = max(abs(highs[0].price - lows[0].price), 1.0)
        low_rising = float(np.clip((lows[-1].price - lows[0].price) / base_range, 0.0, 1.0))
        contraction_score = _sequence_contraction_score(depths)
        tight_range = _tight_range_score(df, max(0, len(df) - 10), len(df) - 1)

        closes = pd.to_numeric(df["close"], errors="coerce")
        if len(closes) < 60:
            return []
        ma20 = float(closes.rolling(20).mean().iloc[-1])
        ma60 = float(closes.rolling(60).mean().iloc[-1])
        current_close = float(closes.iloc[-1])
        if not (current_close > ma20 > ma60):
            return []

        latest_low = lows[-1]
        if latest_low.price >= highs[-1].price:
            return []

        dates = df["date"].values if "date" in df.columns else df["datetime"].values
        last_dt = pd.Timestamp(dates[-1]).to_pydatetime()
        if current_close >= pivot * 1.005:
            state = "confirmed"
        elif current_close >= pivot * 0.985 and contraction_score >= 0.45 and tight_range >= 0.50:
            state = "armed"
        else:
            state = "forming"

        vol_score = _volume_context_score(df, highs[0].index, latest_low.index)
        volat_score = _volatility_context_score(df, highs[0].index, latest_low.index)
        breakout_idx = _breakout_index(df, pivot, latest_low.index, bullish=True, threshold=0.003)
        breakout_quality = _breakout_quality_score(df, breakout_idx, pivot, bullish=True)
        retest_quality = _retest_quality_score(df, breakout_idx, pivot, bullish=True)
        state = _normalize_state(state, breakout_quality, retest_quality)
        if state == "confirmed" and (contraction_score < 0.45 or tight_range < 0.45):
            state = "armed"
        elif state == "armed" and (contraction_score < 0.30 or high_tightness < 0.30):
            state = "forming"

        invalidation = latest_low.price * 0.99
        target_span = max(pivot - latest_low.price, pivot * 0.08)
        target = pivot + target_span
        geometry_fit = round(
            float(
                np.clip(
                    0.30 * contraction_score
                    + 0.24 * high_tightness
                    + 0.18 * low_rising
                    + 0.16 * tight_range
                    + 0.12 * volat_score,
                    0.0,
                    1.0,
                )
            ),
            3,
        )
        swing_fit = round(float(np.clip(0.60 * contraction_score + 0.40 * low_rising, 0.0, 1.0)), 3)
        grade = _grade_from_quality(geometry_fit, breakout_quality, retest_quality, vol_score)
        contraction_count = len(segment)

        r = PatternResult(
            pattern_type="vcp",
            state=state,
            grade=grade,
            start_dt=highs[0].datetime,
            end_dt=last_dt if state == "confirmed" else None,
            variant=f"{contraction_count}_contractions",
            neckline=pivot,
            invalidation_level=invalidation,
            target_level=target,
            geometry_fit=geometry_fit,
            swing_structure_fit=swing_fit,
            volume_context_fit=round(vol_score, 3),
            volatility_context_fit=round(volat_score, 3),
            regime_fit=max(regime_fit, 0.72),
            leg_balance_fit=round(high_tightness, 3),
            reversal_energy_fit=round(contraction_score, 3),
            variant_fit=round(min(1.0, 0.55 + 0.15 * contraction_count), 3),
            breakout_quality_fit=breakout_quality,
            retest_quality_fit=retest_quality,
            key_points=[
                {"dt": highs[0].datetime.isoformat(), "price": highs[0].price, "type": "pivot_high_1"},
                {"dt": lows[0].datetime.isoformat(), "price": lows[0].price, "type": "pullback_1"},
                {"dt": highs[1].datetime.isoformat(), "price": highs[1].price, "type": "pivot_high_2"},
                {"dt": lows[1].datetime.isoformat(), "price": lows[1].price, "type": "pullback_2"},
                {"dt": highs[2].datetime.isoformat(), "price": highs[2].price, "type": "pivot_high_3"},
                {"dt": lows[2].datetime.isoformat(), "price": lows[2].price, "type": "pullback_3"},
            ],
            is_provisional=(state != "confirmed"),
        )
        r.textbook_similarity = _finalize_textbook_similarity(r)
        return [r]

    def _detect_rectangle(
        self, df: pd.DataFrame, swings: list[SwingPoint], regime_fit: float
    ) -> list[PatternResult]:
        highs = [s for s in swings if s.kind == "high"]
        lows = [s for s in swings if s.kind == "low"]
        dates = df["date"].values if "date" in df.columns else df["datetime"].values

        if len(highs) < 2 or len(lows) < 2:
            return []

        h_series = highs[-3:]
        l_series = lows[-3:]
        h_std = np.std([h.price for h in h_series]) / np.mean([h.price for h in h_series])
        l_std = np.std([l.price for l in l_series]) / np.mean([l.price for l in l_series])

        if h_std > 0.03 or l_std > 0.03:
            return []

        resistance = np.mean([h.price for h in h_series])
        support = np.mean([l.price for l in l_series])
        if (resistance - support) / support < 0.03:
            return []

        current_close = float(df["close"].iloc[-1])
        last_dt = pd.Timestamp(dates[-1]).to_pydatetime()
        if current_close > resistance * 1.005:
            state = "confirmed"
        elif current_close > resistance * 0.995:
            state = "armed"
        else:
            state = "forming"
        breakout_idx = _breakout_index(df, resistance, max(h.index for h in h_series[-2:] + l_series[-2:]), bullish=True)
        breakout_quality = _breakout_quality_score(df, breakout_idx, resistance, bullish=True)
        retest_quality = _retest_quality_score(df, breakout_idx, resistance, bullish=True)
        vol_score = _volume_context_score(df, min(h_series[0].index, l_series[0].index), len(df) - 1)
        volat_score = _volatility_context_score(df, min(h_series[0].index, l_series[0].index), len(df) - 1)
        state = _normalize_state(state, breakout_quality, retest_quality)
        grade = _grade_from_quality(max(0.0, 1 - (h_std + l_std) * 10), breakout_quality, retest_quality, vol_score)

        r = PatternResult(
            pattern_type="rectangle",
            state=state, grade=grade,
            start_dt=min(h_series[0].datetime, l_series[0].datetime),
            end_dt=last_dt if state == "confirmed" else None,
            neckline=resistance,
            invalidation_level=support * 0.99,
            target_level=resistance + (resistance - support),
            geometry_fit=round(1 - (h_std + l_std) * 10, 3),
            swing_structure_fit=0.7,
            volume_context_fit=round(vol_score, 3),
            volatility_context_fit=round(volat_score, 3),
            regime_fit=regime_fit,
            leg_balance_fit=0.58,
            reversal_energy_fit=0.55,
            breakout_quality_fit=breakout_quality,
            retest_quality_fit=retest_quality,
            key_points=[
                {"price": resistance, "type": "resistance"},
                {"price": support, "type": "support"},
            ],
            is_provisional=(state != "confirmed"),
        )
        r.textbook_similarity = _finalize_textbook_similarity(r)
        return [r]
