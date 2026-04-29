from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import select

from ..core.database import AsyncSessionLocal
from ..models.outcome import SignalOutcome
from .timeframe_service import timeframe_label

COMPLETED_OUTCOMES = {"win", "loss", "stopped_out"}

INTENT_META: dict[str, dict[str, str]] = {
    "breakout_wait": {
        "label": "돌파 대기",
        "style_key": "breakout",
        "style_label": "돌파형",
    },
    "pullback_candidate": {
        "label": "눌림 매수",
        "style_key": "pullback",
        "style_label": "눌림형",
    },
    "observe": {
        "label": "관망",
        "style_key": "watchful",
        "style_label": "관망형",
    },
    "invalidation_watch": {
        "label": "손절 구간 감시",
        "style_key": "risk_manager",
        "style_label": "리스크 관리형",
    },
}


def _normalize_intent(intent: str | None) -> str:
    value = (intent or "breakout_wait").strip().lower()
    return value if value in INTENT_META else "breakout_wait"


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _bucket_stats(records: list[SignalOutcome], key_name: str) -> dict[str, dict[str, float | int]]:
    buckets: dict[str, dict[str, float | int]] = {}
    for record in records:
        key = getattr(record, key_name, None) or "unknown"
        if key_name == "intent":
            key = _normalize_intent(str(key))
        bucket = buckets.setdefault(str(key), {"wins": 0, "total": 0, "win_rate": 0.0})
        bucket["total"] = int(bucket["total"]) + 1
        if record.outcome == "win":
            bucket["wins"] = int(bucket["wins"]) + 1

    for bucket in buckets.values():
        total = max(int(bucket["total"]), 1)
        bucket["win_rate"] = round(int(bucket["wins"]) / total, 3)
    return dict(sorted(buckets.items(), key=lambda item: (-int(item[1]["total"]), -float(item[1]["win_rate"]), item[0])))


def _pick_top_bucket(
    buckets: dict[str, dict[str, float | int]],
    *,
    min_total: int = 1,
) -> tuple[str | None, dict[str, float | int] | None]:
    eligible = [(key, value) for key, value in buckets.items() if int(value["total"]) >= min_total]
    if not eligible:
        eligible = list(buckets.items())
    if not eligible:
        return None, None
    eligible.sort(key=lambda item: (float(item[1]["win_rate"]), int(item[1]["total"])), reverse=True)
    return eligible[0]


def _intent_strength(intent: str, stats: dict[str, float | int], completed_count: int) -> float:
    sample_share = int(stats["total"]) / max(completed_count, 1)
    style_bonus = 0.06 if intent in {"breakout_wait", "pullback_candidate"} else 0.03
    return float(stats["win_rate"]) * 0.72 + min(sample_share, 0.35) * 0.28 + style_bonus


def build_personalization_snapshot(records: list[SignalOutcome]) -> dict[str, Any]:
    completed = [record for record in records if record.outcome in COMPLETED_OUTCOMES]
    wins = [record for record in completed if record.outcome == "win"]
    pending = [record for record in records if record.outcome == "pending"]
    cancelled = [record for record in records if record.outcome == "cancelled"]

    hold_days: list[int] = []
    for record in completed:
        if not record.signal_date or not record.exit_date:
            continue
        try:
            start = record.signal_date[:10]
            end = record.exit_date[:10]
            hold_days.append(max((date.fromisoformat(end) - date.fromisoformat(start)).days, 0))
        except ValueError:
            continue

    by_pattern = _bucket_stats(completed, "pattern_type")
    by_intent = _bucket_stats(completed, "intent")
    by_timeframe = _bucket_stats(completed, "timeframe")

    completed_count = len(completed)
    style_profile = {
        "style_key": "developing",
        "style_label": "학습 중",
        "summary": "아직 저장된 종료 판단이 충분하지 않아 개인화가 학습 중입니다.",
        "confidence": 0.0,
        "sample_count": completed_count,
        "primary_intent": "breakout_wait",
        "primary_intent_label": INTENT_META["breakout_wait"]["label"],
        "secondary_intent": None,
        "secondary_intent_label": None,
        "best_pattern": None,
        "best_pattern_win_rate": 0.0,
        "best_timeframe": None,
        "best_timeframe_label": None,
        "best_timeframe_win_rate": 0.0,
        "focus_points": [
            f"종료 기록 {completed_count}건이 쌓이면 개인화 우선순위가 더 또렷해집니다.",
        ],
    }

    if completed_count > 0:
        ranked_intents = sorted(
            by_intent.items(),
            key=lambda item: (_intent_strength(item[0], item[1], completed_count), float(item[1]["win_rate"]), int(item[1]["total"])),
            reverse=True,
        )
        primary_intent, primary_stats = ranked_intents[0]
        secondary = ranked_intents[1][0] if len(ranked_intents) > 1 else None
        best_pattern, best_pattern_stats = _pick_top_bucket(by_pattern, min_total=1)
        best_timeframe, best_timeframe_stats = _pick_top_bucket(by_timeframe, min_total=1)
        confidence = _clamp(
            float(primary_stats["win_rate"]) * 0.55
            + min(int(primary_stats["total"]) / 8, 1.0) * 0.25
            + min(completed_count / 12, 1.0) * 0.20
        )
        primary_meta = INTENT_META[primary_intent]
        secondary_meta = INTENT_META.get(secondary or "", {})
        focus_points = [
            f"주된 판단은 {primary_meta['label']}이고, 종료 기록 {int(primary_stats['total'])}건 기준 승률 {float(primary_stats['win_rate']) * 100:.0f}%입니다.",
        ]
        if best_pattern and best_pattern_stats:
            focus_points.append(
                f"가장 잘 맞는 패턴은 {best_pattern}이며 승률 {float(best_pattern_stats['win_rate']) * 100:.0f}%입니다."
            )
        if best_timeframe and best_timeframe_stats:
            focus_points.append(
                f"가장 잘 맞는 타임프레임은 {timeframe_label(best_timeframe)}이며 승률 {float(best_timeframe_stats['win_rate']) * 100:.0f}%입니다."
            )

        style_profile = {
            "style_key": primary_meta["style_key"],
            "style_label": primary_meta["style_label"],
            "summary": (
                f"저장된 종료 판단 {completed_count}건 기준으로 {primary_meta['style_label']} 성향이 가장 강합니다. "
                f"{secondary_meta.get('label', '보조 성향 없음')}도 보조적으로 나타납니다."
                if secondary
                else f"저장된 종료 판단 {completed_count}건 기준으로 {primary_meta['style_label']} 성향이 가장 강합니다."
            ),
            "confidence": round(confidence, 3),
            "sample_count": completed_count,
            "primary_intent": primary_intent,
            "primary_intent_label": primary_meta["label"],
            "secondary_intent": secondary,
            "secondary_intent_label": secondary_meta.get("label"),
            "best_pattern": best_pattern,
            "best_pattern_win_rate": round(float(best_pattern_stats["win_rate"]), 3) if best_pattern_stats else 0.0,
            "best_timeframe": best_timeframe,
            "best_timeframe_label": timeframe_label(best_timeframe) if best_timeframe else None,
            "best_timeframe_win_rate": round(float(best_timeframe_stats["win_rate"]), 3) if best_timeframe_stats else 0.0,
            "focus_points": focus_points,
        }

    return {
        "total_records": len(records),
        "completed": completed_count,
        "wins": len(wins),
        "win_rate": round(len(wins) / max(completed_count, 1), 3),
        "avg_hold_days": round(sum(hold_days) / len(hold_days), 2) if hold_days else 0.0,
        "pending": len(pending),
        "cancelled": len(cancelled),
        "by_pattern": by_pattern,
        "by_intent": by_intent,
        "by_timeframe": by_timeframe,
        "style_profile": style_profile,
    }


async def load_personalization_snapshot() -> dict[str, Any]:
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(SignalOutcome))
        records = result.scalars().all()
    return build_personalization_snapshot(records)


def infer_candidate_intent(row: dict[str, Any]) -> str:
    if row.get("no_signal_flag") or row.get("action_plan") == "recheck" or len(row.get("risk_flags") or []) >= 3:
        return "invalidation_watch"
    if float(row.get("reentry_score", 0.0)) >= 0.52:
        return "pullback_candidate"
    if float(row.get("entry_window_score", 0.0)) >= 0.52 or float(row.get("trade_readiness_score", 0.0)) >= 0.58:
        return "breakout_wait"
    if float(row.get("freshness_score", 0.0)) >= 0.45:
        return "observe"
    return "observe"


def score_personal_fit(row: dict[str, Any], snapshot: dict[str, Any] | None) -> tuple[float, str, list[str]]:
    if not snapshot:
        return 0.0, "학습 전", []

    style_profile = snapshot.get("style_profile") or {}
    by_intent = snapshot.get("by_intent") or {}
    by_pattern = snapshot.get("by_pattern") or {}
    by_timeframe = snapshot.get("by_timeframe") or {}
    sample_count = int(style_profile.get("sample_count") or 0)
    if sample_count <= 0:
        return 0.0, "학습 전", []

    inferred_intent = infer_candidate_intent(row)
    intent_stats = by_intent.get(inferred_intent) or {"win_rate": 0.5, "total": 0}
    pattern_key = str(row.get("pattern_type") or "unknown")
    pattern_stats = by_pattern.get(pattern_key) or {"win_rate": 0.5, "total": 0}
    timeframe_key = str(row.get("timeframe") or "1d")
    timeframe_stats = by_timeframe.get(timeframe_key) or {"win_rate": 0.5, "total": 0}

    score = (
        0.34 * float(intent_stats.get("win_rate", 0.5))
        + 0.22 * float(pattern_stats.get("win_rate", 0.5))
        + 0.12 * float(timeframe_stats.get("win_rate", 0.5))
        + 0.12 * float(style_profile.get("confidence", 0.0))
        + 0.12 * float(row.get("trade_readiness_score", 0.0))
        + 0.08 * float(row.get("data_quality", 0.0))
    )

    reasons: list[str] = []
    intent_label = INTENT_META[inferred_intent]["label"]
    reasons.append(
        f"내 기록 기준 {intent_label} 판단 {int(intent_stats.get('total', 0))}건, 승률 {float(intent_stats.get('win_rate', 0.0)) * 100:.0f}%입니다."
    )
    if int(pattern_stats.get("total", 0)) > 0:
        reasons.append(
            f"{pattern_key} 패턴은 내 기록 {int(pattern_stats.get('total', 0))}건에서 승률 {float(pattern_stats.get('win_rate', 0.0)) * 100:.0f}%입니다."
        )
    if int(timeframe_stats.get("total", 0)) > 0:
        reasons.append(
            f"{timeframe_label(timeframe_key)} 타임프레임은 승률 {float(timeframe_stats.get('win_rate', 0.0)) * 100:.0f}%입니다."
        )

    if inferred_intent == style_profile.get("primary_intent"):
        score += 0.10
        reasons.append(f"현재 후보는 내 주 성향인 {style_profile.get('primary_intent_label')}과 잘 맞습니다.")
    elif inferred_intent == style_profile.get("secondary_intent"):
        score += 0.05
        reasons.append(f"현재 후보는 보조 성향인 {style_profile.get('secondary_intent_label')}과도 맞닿아 있습니다.")

    if pattern_key and pattern_key == style_profile.get("best_pattern"):
        score += 0.05
        reasons.append("가장 잘 맞던 패턴과 같은 구조입니다.")
    if timeframe_key and timeframe_key == style_profile.get("best_timeframe"):
        score += 0.04
        reasons.append("내가 가장 잘 맞췄던 타임프레임과 같습니다.")

    score = round(_clamp(score) * 100, 1)
    if score >= 76:
        label = "매우 잘 맞음"
    elif score >= 62:
        label = "잘 맞음"
    elif score >= 48:
        label = "보통"
    else:
        label = "보수 접근"
    return score, label, reasons[:4]
