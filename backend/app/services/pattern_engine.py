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

TextbookSimilarity = 0.45*GeometryFit + 0.20*SwingFit + 0.15*VolumeContextFit
                   + 0.10*VolatilityContextFit + 0.10*RegimeFit
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
    textbook_similarity: float = 0.0

    key_points: list[dict] = field(default_factory=list)
    is_provisional: bool = True


def _compute_textbook_similarity(r: PatternResult) -> float:
    return (
        0.45 * r.geometry_fit
        + 0.20 * r.swing_structure_fit
        + 0.15 * r.volume_context_fit
        + 0.10 * r.volatility_context_fit
        + 0.10 * r.regime_fit
    )


def _volume_context_score(df: pd.DataFrame, start_idx: int, end_idx: int) -> float:
    """
    For bullish patterns: volume should decline during pattern formation
    and expand on breakout. Returns a simple heuristic score 0-1.
    """
    if "volume" not in df.columns or end_idx - start_idx < 5:
        return 0.5
    formation = df["volume"].iloc[start_idx:end_idx]
    if len(formation) < 4:
        return 0.5
    first_half = formation.iloc[: len(formation) // 2].mean()
    second_half = formation.iloc[len(formation) // 2 :].mean()
    if first_half == 0:
        return 0.5
    contraction = 1 - (second_half / first_half)  # positive if volume contracted
    return float(np.clip(0.5 + contraction * 0.5, 0.0, 1.0))


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
            geom_fit = price_sym * 0.6 + max(0, 1 - abs(low_diff) * 10) * 0.4

            r = PatternResult(
                pattern_type="double_bottom",
                state=state,
                grade="A",
                start_dt=L1.datetime,
                end_dt=last_dt if state == "confirmed" else None,
                neckline=neckline,
                invalidation_level=invalidation,
                target_level=target,
                geometry_fit=round(geom_fit, 3),
                swing_structure_fit=round(min(1.0, (L2.index - L1.index) / 10), 3),
                volume_context_fit=round(vol_score, 3),
                volatility_context_fit=0.5,
                regime_fit=regime_fit,
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
            geom_fit = price_sym * 0.6 + max(0, 1 - abs(high_diff) * 10) * 0.4

            r = PatternResult(
                pattern_type="double_top",
                state=state,
                grade="A",
                start_dt=H1.datetime,
                end_dt=last_dt if state == "confirmed" else None,
                neckline=neckline,
                invalidation_level=invalidation,
                target_level=target,
                geometry_fit=round(geom_fit, 3),
                swing_structure_fit=round(min(1.0, (H2.index - H1.index) / 10), 3),
                volume_context_fit=round(vol_score, 3),
                volatility_context_fit=0.5,
                regime_fit=regime_fit,
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
            geom_fit = shoulder_sym * 0.5 + min(
                1.0,
                _safe_ratio(H.price - max(LS.price, RS.price), H.price) * 10,
            ) * 0.5

            r = PatternResult(
                pattern_type="head_and_shoulders",
                state=state,
                grade="A",
                start_dt=LS.datetime,
                end_dt=last_dt if state == "confirmed" else None,
                neckline=neckline,
                invalidation_level=invalidation,
                target_level=target,
                geometry_fit=round(geom_fit, 3),
                swing_structure_fit=round(shoulder_sym, 3),
                volume_context_fit=round(vol_score, 3),
                volatility_context_fit=0.5,
                regime_fit=regime_fit,
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
            geom_fit = shoulder_sym * 0.5 + min(
                1.0,
                _safe_ratio(min(LS.price, RS.price) - H.price, H.price) * 10,
            ) * 0.5

            r = PatternResult(
                pattern_type="inverse_head_and_shoulders",
                state=state, grade="A",
                start_dt=LS.datetime,
                end_dt=last_dt if state == "confirmed" else None,
                neckline=neckline, invalidation_level=invalidation, target_level=target,
                geometry_fit=round(geom_fit, 3),
                swing_structure_fit=round(shoulder_sym, 3),
                volume_context_fit=round(vol_score, 3),
                volatility_context_fit=0.5,
                regime_fit=regime_fit,
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
        elif high_flat and low_ascending:
            pattern_type = "ascending_triangle"
            resistance = sum(h.price for h in h_series) / len(h_series)
            state = "confirmed" if current_close > resistance * 1.005 else (
                "armed" if current_close > resistance * 0.99 else "forming"
            )
        elif high_descending and not low_ascending:
            pattern_type = "descending_triangle"
            support = sum(l.price for l in l_series) / len(l_series)
            state = "confirmed" if current_close < support * 0.995 else (
                "armed" if current_close < support * 1.01 else "forming"
            )
        else:
            return []

        start_dt = min(h_series[0].datetime, l_series[0].datetime)
        vol_score = _volume_context_score(df, min(h_series[0].index, l_series[0].index), len(df) - 1)

        r = PatternResult(
            pattern_type=pattern_type,
            state=state, grade="A",
            start_dt=start_dt,
            end_dt=last_dt if state == "confirmed" else None,
            geometry_fit=0.65, swing_structure_fit=0.60,
            volume_context_fit=round(vol_score, 3),
            volatility_context_fit=0.5, regime_fit=regime_fit,
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

        r = PatternResult(
            pattern_type="rectangle",
            state=state, grade="A",
            start_dt=min(h_series[0].datetime, l_series[0].datetime),
            end_dt=last_dt if state == "confirmed" else None,
            neckline=resistance,
            invalidation_level=support * 0.99,
            target_level=resistance + (resistance - support),
            geometry_fit=round(1 - (h_std + l_std) * 10, 3),
            swing_structure_fit=0.7,
            volume_context_fit=0.5,
            volatility_context_fit=0.5,
            regime_fit=regime_fit,
            key_points=[
                {"price": resistance, "type": "resistance"},
                {"price": support, "type": "support"},
            ],
            is_provisional=(state != "confirmed"),
        )
        r.textbook_similarity = round(_compute_textbook_similarity(r), 3)
        return [r]
