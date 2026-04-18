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
]


@dataclass
class PatternResult:
    pattern_type: PatternType
    state: str          # forming | armed | confirmed | invalidated | played_out
    grade: str          # A | B | C
    start_dt: datetime
    end_dt: datetime | None

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
    breakout_quality_fit: float = 0.0
    retest_quality_fit: float = 0.0
    textbook_similarity: float = 0.0

    key_points: list[dict] = field(default_factory=list)
    is_provisional: bool = True


def _compute_textbook_similarity(r: PatternResult) -> float:
    return (
        0.38 * r.geometry_fit
        + 0.18 * r.swing_structure_fit
        + 0.12 * r.volume_context_fit
        + 0.08 * r.volatility_context_fit
        + 0.08 * r.regime_fit
        + 0.10 * r.breakout_quality_fit
        + 0.06 * r.retest_quality_fit
    )


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
            self._detect_rectangle,
        ]:
            found = detector(df, swings, regime_fit)
            if found:
                results.extend(found)

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
            geom_fit = price_sym * 0.6 + max(0, 1 - abs(low_diff) * 10) * 0.4
            breakout_idx = _breakout_index(df, neckline, L2.index, bullish=True)
            breakout_quality = _breakout_quality_score(df, breakout_idx, neckline, bullish=True)
            retest_quality = _retest_quality_score(df, breakout_idx, neckline, bullish=True)
            state = _normalize_state(state, breakout_quality, retest_quality)
            grade = _grade_from_quality(geom_fit, breakout_quality, retest_quality, vol_score)

            r = PatternResult(
                pattern_type="double_bottom",
                state=state,
                grade=grade,
                start_dt=L1.datetime,
                end_dt=last_dt if state == "confirmed" else None,
                neckline=neckline,
                invalidation_level=invalidation,
                target_level=target,
                geometry_fit=round(geom_fit, 3),
                swing_structure_fit=round(min(1.0, (L2.index - L1.index) / 10), 3),
                volume_context_fit=round(vol_score, 3),
                volatility_context_fit=round(volat_score, 3),
                regime_fit=regime_fit,
                breakout_quality_fit=breakout_quality,
                retest_quality_fit=retest_quality,
                key_points=[
                    {"dt": L1.datetime.isoformat(), "price": L1.price, "type": "low1"},
                    {"dt": neckline_swing.datetime.isoformat(), "price": neckline, "type": "neckline"},
                    {"dt": L2.datetime.isoformat(), "price": L2.price, "type": "low2"},
                ],
                is_provisional=(state != "confirmed"),
            )
            r.textbook_similarity = round(_compute_textbook_similarity(r), 3)
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
            geom_fit = price_sym * 0.6 + max(0, 1 - abs(high_diff) * 10) * 0.4
            breakout_idx = _breakout_index(df, neckline, H2.index, bullish=False)
            breakout_quality = _breakout_quality_score(df, breakout_idx, neckline, bullish=False)
            retest_quality = _retest_quality_score(df, breakout_idx, neckline, bullish=False)
            state = _normalize_state(state, breakout_quality, retest_quality)
            grade = _grade_from_quality(geom_fit, breakout_quality, retest_quality, vol_score)

            r = PatternResult(
                pattern_type="double_top",
                state=state,
                grade=grade,
                start_dt=H1.datetime,
                end_dt=last_dt if state == "confirmed" else None,
                neckline=neckline,
                invalidation_level=invalidation,
                target_level=target,
                geometry_fit=round(geom_fit, 3),
                swing_structure_fit=round(min(1.0, (H2.index - H1.index) / 10), 3),
                volume_context_fit=round(vol_score, 3),
                volatility_context_fit=round(volat_score, 3),
                regime_fit=regime_fit,
                breakout_quality_fit=breakout_quality,
                retest_quality_fit=retest_quality,
                key_points=[
                    {"dt": H1.datetime.isoformat(), "price": H1.price, "type": "high1"},
                    {"dt": neckline_swing.datetime.isoformat(), "price": neckline, "type": "neckline"},
                    {"dt": H2.datetime.isoformat(), "price": H2.price, "type": "high2"},
                ],
                is_provisional=(state != "confirmed"),
            )
            r.textbook_similarity = round(_compute_textbook_similarity(r), 3)
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
            geom_fit = shoulder_sym * 0.5 + min(
                1.0,
                _safe_ratio(H.price - max(LS.price, RS.price), H.price) * 10,
            ) * 0.5
            breakout_idx = _breakout_index(df, neckline, RS.index, bullish=False)
            breakout_quality = _breakout_quality_score(df, breakout_idx, neckline, bullish=False)
            retest_quality = _retest_quality_score(df, breakout_idx, neckline, bullish=False)
            state = _normalize_state(state, breakout_quality, retest_quality)
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
            r.textbook_similarity = round(_compute_textbook_similarity(r), 3)
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
            geom_fit = shoulder_sym * 0.5 + min(
                1.0,
                _safe_ratio(min(LS.price, RS.price) - H.price, H.price) * 10,
            ) * 0.5
            breakout_idx = _breakout_index(df, neckline, RS.index, bullish=True)
            breakout_quality = _breakout_quality_score(df, breakout_idx, neckline, bullish=True)
            retest_quality = _retest_quality_score(df, breakout_idx, neckline, bullish=True)
            state = _normalize_state(state, breakout_quality, retest_quality)
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
                breakout_quality_fit=breakout_quality,
                retest_quality_fit=retest_quality,
                key_points=[
                    {"dt": LS.datetime.isoformat(), "price": LS.price, "type": "left_shoulder"},
                    {"dt": H.datetime.isoformat(), "price": H.price, "type": "head"},
                    {"dt": RS.datetime.isoformat(), "price": RS.price, "type": "right_shoulder"},
                ],
                is_provisional=(state != "confirmed"),
            )
            r.textbook_similarity = round(_compute_textbook_similarity(r), 3)
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
            breakout_quality_fit=breakout_quality,
            retest_quality_fit=retest_quality,
            is_provisional=(state != "confirmed"),
        )
        r.textbook_similarity = round(_compute_textbook_similarity(r), 3)
        return [r]

    # ── Rectangle (Box) ─────────────────────────────────────────────────────

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
            breakout_quality_fit=breakout_quality,
            retest_quality_fit=retest_quality,
            key_points=[
                {"price": resistance, "type": "resistance"},
                {"price": support, "type": "support"},
            ],
            is_provisional=(state != "confirmed"),
        )
        r.textbook_similarity = round(_compute_textbook_similarity(r), 3)
        return [r]
