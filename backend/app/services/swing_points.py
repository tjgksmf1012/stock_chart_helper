"""
Swing point detection: pivot high/low using fractal-based algorithm.

A pivot high at index i: high[i] is the highest among a window of N bars on each side.
A pivot low at index i: low[i] is the lowest among a window of N bars on each side.
"""

from dataclasses import dataclass
from datetime import datetime
import numpy as np
import pandas as pd


@dataclass
class SwingPoint:
    index: int
    datetime: datetime
    price: float
    kind: str  # "high" | "low"
    strength: int  # window size used


def detect_swing_points(df: pd.DataFrame, window: int = 5) -> list[SwingPoint]:
    """
    df must have columns: [date/datetime, high, low, close]
    Returns list of SwingPoint sorted by index.
    """
    highs = df["high"].values
    lows = df["low"].values
    dates = df["date"].values if "date" in df.columns else df["datetime"].values
    n = len(df)
    points: list[SwingPoint] = []

    for i in range(window, n - window):
        left_h = highs[i - window: i]
        right_h = highs[i + 1: i + window + 1]
        if highs[i] > left_h.max() and highs[i] > right_h.max():
            points.append(SwingPoint(i, pd.Timestamp(dates[i]).to_pydatetime(), float(highs[i]), "high", window))

        left_l = lows[i - window: i]
        right_l = lows[i + 1: i + window + 1]
        if lows[i] < left_l.min() and lows[i] < right_l.min():
            points.append(SwingPoint(i, pd.Timestamp(dates[i]).to_pydatetime(), float(lows[i]), "low", window))

    points.sort(key=lambda p: p.index)
    return points


def get_significant_swings(df: pd.DataFrame, min_window: int = 3, max_window: int = 10) -> list[SwingPoint]:
    """
    Multi-window swing detection. Uses adaptive window based on df length.
    For long series, uses larger window to avoid micro-noise.
    """
    n = len(df)
    if n < 20:
        return []
    window = min(max(min_window, n // 20), max_window)
    return detect_swing_points(df, window)


def alternating_swings(points: list[SwingPoint]) -> list[SwingPoint]:
    """
    Ensure highs and lows alternate (no two consecutive highs or lows).
    Keeps the more extreme of consecutive same-kind points.
    """
    if not points:
        return []
    result = [points[0]]
    for p in points[1:]:
        last = result[-1]
        if p.kind == last.kind:
            if p.kind == "high" and p.price >= last.price:
                result[-1] = p
            elif p.kind == "low" and p.price <= last.price:
                result[-1] = p
        else:
            result.append(p)
    return result
