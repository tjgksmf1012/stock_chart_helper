"""Probability calibration: do the shown probabilities match reality?

The scanner stores every signal's ``p_up_at_signal`` alongside the eventual
``outcome`` in :class:`SignalOutcome`. This module closes the loop: it bins the
predicted win probabilities and compares each bin against the *realized* win
rate, producing a reliability curve, Brier score, and Expected Calibration
Error (ECE).

Everything here is pure: ``build_calibration_report`` takes ``(predicted, won)``
pairs, so it is fully unit-testable without a database or pandas.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

# Below this many resolved signals the report is not statistically meaningful.
MIN_CALIBRATION_SAMPLES = 20

# Below this many samples *within a single bin*, that bin's observed win rate is too
# noisy to trust (e.g. 1 win out of 1 trade reads as "100% observed"). Bins under this
# threshold are excluded from the ECE/reliability verdict, though still returned in
# `bins` (flagged via `low_confidence`) so callers can render them distinctly.
MIN_BIN_SAMPLES = 5

# Outcomes that represent a closed trade we can score. "pending"/"cancelled"
# are excluded because they have no realized result.
_RESOLVED_OUTCOMES = {"win", "loss", "stopped_out"}


@dataclass
class CalibrationBin:
    """One probability bucket: predicted vs. observed win rate."""

    lower: float
    upper: float
    count: int
    predicted: float  # mean predicted win probability inside the bin
    observed: float  # realized win rate inside the bin
    gap: float  # observed - predicted (negative => overconfident)
    low_confidence: bool = False  # count < MIN_BIN_SAMPLES -- observed is noisy


@dataclass
class CalibrationReport:
    sample_size: int
    resolved_wins: int
    base_rate: float  # overall realized win rate
    mean_predicted: float  # overall mean predicted win probability
    brier_score: float  # mean squared error of the probabilities (lower is better)
    ece: float  # expected calibration error (sample-weighted |observed-predicted|)
    mean_gap: float  # base_rate - mean_predicted (negative => overconfident)
    reliability: str  # human-readable verdict (Korean)
    bins: list[CalibrationBin]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def outcome_to_pair(record: dict[str, Any]) -> tuple[float, bool] | None:
    """Map a serialized :class:`SignalOutcome` to a ``(predicted, won)`` pair.

    Returns ``None`` for records that cannot be scored (still pending/cancelled
    or missing the probability that was shown at signal time).

    Direction handling: ``p_up_at_signal`` is the probability price goes *up*.
    For a short setup (target below entry) the trade wins when price falls, so
    the probability for the taken direction is ``1 - p_up``.
    """
    outcome = str(record.get("outcome") or "").strip().lower()
    if outcome not in _RESOLVED_OUTCOMES:
        return None

    p_up = record.get("p_up_at_signal")
    if p_up is None:
        return None
    p_up = float(p_up)

    entry = record.get("entry_price")
    target = record.get("target_price")
    is_short = entry is not None and target is not None and float(target) < float(entry)
    predicted = (1.0 - p_up) if is_short else p_up
    predicted = min(1.0, max(0.0, predicted))

    won = outcome == "win"
    return predicted, won


def _reliability_label(
    sample_size: int,
    ece: float,
    mean_gap: float,
    min_samples: int,
    *,
    reliable_bin_count: int = 0,
    thin_bin_count: int = 0,
) -> str:
    if sample_size < min_samples:
        return f"표본 부족 (n={sample_size}, 최소 {min_samples})"
    # 전체 표본은 min_samples를 넘겨도, bin_count(기본 10)개 구간에 고르게 나뉘면 구간당
    # 표본이 몇 건뿐일 수 있다. 그런 상태에서 "잘 보정됨"이라고 하면 1~2건짜리 관측을
    # 근거로 신뢰도를 보증하는 셈이다 — 신뢰할 만한 구간이 하나도 없으면 그 사실을
    # 먼저 알린다.
    if reliable_bin_count == 0:
        return f"구간별 표본 부족 (전체 n={sample_size}이지만 구간당 표본이 {MIN_BIN_SAMPLES}건 미만)"
    if ece <= 0.05:
        if thin_bin_count > 0:
            return f"양호하나 일부 구간 표본 부족 (구간 {thin_bin_count}개는 참고용)"
        return "양호 (잘 보정됨)"
    if mean_gap <= -0.05:
        return "과신 경향 (예측 확률이 실제보다 높음)"
    if mean_gap >= 0.05:
        return "과소 경향 (예측 확률이 실제보다 낮음)"
    return "보통 (소폭 편차)"


def build_calibration_report(
    pairs: list[tuple[float, bool]],
    *,
    bin_count: int = 10,
    min_samples: int = MIN_CALIBRATION_SAMPLES,
    min_bin_samples: int = MIN_BIN_SAMPLES,
) -> CalibrationReport:
    """Aggregate ``(predicted, won)`` pairs into a calibration report."""
    clean = [(float(p), bool(w)) for p, w in pairs if p is not None]
    n = len(clean)
    if n == 0:
        return CalibrationReport(
            sample_size=0,
            resolved_wins=0,
            base_rate=0.0,
            mean_predicted=0.0,
            brier_score=0.0,
            ece=0.0,
            mean_gap=0.0,
            reliability=_reliability_label(0, 0.0, 0.0, min_samples),
            bins=[],
        )

    wins = sum(1 for _, w in clean if w)
    base_rate = wins / n
    mean_pred = sum(p for p, _ in clean) / n
    brier = sum((p - (1.0 if w else 0.0)) ** 2 for p, w in clean) / n

    buckets: list[list[tuple[float, bool]]] = [[] for _ in range(bin_count)]
    for p, w in clean:
        idx = int(p * bin_count)
        idx = max(0, min(bin_count - 1, idx))
        buckets[idx].append((p, w))

    bins: list[CalibrationBin] = []
    # ECE는 표본이 충분한 구간만으로 계산한다 — 구간당 1~2건짜리 관측을 근거로 "잘
    # 보정됨"을 보증하지 않기 위해서다. 얇은 구간은 제외한 만큼 남은 구간들의 가중치
    # 합으로 다시 정규화한다(reliable_weight로 나눔).
    ece_numerator = 0.0
    reliable_weight = 0.0
    reliable_bin_count = 0
    thin_bin_count = 0
    for i, bucket in enumerate(buckets):
        if not bucket:
            continue
        count = len(bucket)
        predicted = sum(p for p, _ in bucket) / count
        observed = sum(1 for _, w in bucket if w) / count
        low_confidence = count < min_bin_samples
        bins.append(
            CalibrationBin(
                lower=round(i / bin_count, 4),
                upper=round((i + 1) / bin_count, 4),
                count=count,
                predicted=round(predicted, 4),
                observed=round(observed, 4),
                gap=round(observed - predicted, 4),
                low_confidence=low_confidence,
            )
        )
        if low_confidence:
            thin_bin_count += 1
            continue
        reliable_bin_count += 1
        weight = count / n
        reliable_weight += weight
        ece_numerator += weight * abs(observed - predicted)

    ece = (ece_numerator / reliable_weight) if reliable_weight > 0 else 0.0

    mean_gap = base_rate - mean_pred
    return CalibrationReport(
        sample_size=n,
        resolved_wins=wins,
        base_rate=round(base_rate, 4),
        mean_predicted=round(mean_pred, 4),
        brier_score=round(brier, 4),
        ece=round(ece, 4),
        mean_gap=round(mean_gap, 4),
        reliability=_reliability_label(
            n,
            round(ece, 4),
            round(mean_gap, 4),
            min_samples,
            reliable_bin_count=reliable_bin_count,
            thin_bin_count=thin_bin_count,
        ),
        bins=bins,
    )
