from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

import pandas as pd

from ..api.schemas import AnalysisResult, ReferenceCaseItem, ReferenceCaseResponse
from ..core.redis import cache_get, cache_set
from .backtest_engine import get_backtest_config, get_backtest_universe
from .data_fetcher import get_data_fetcher
from .pattern_engine import PatternEngine, PatternResult
from .timeframe_service import timeframe_label

REFERENCE_CASES_TTL = 60 * 60 * 6


@dataclass
class _ReferenceSnapshot:
    symbol_code: str
    symbol_name: str
    timeframe: str
    pattern_type: str
    state: str
    signal_date: str
    resolution_date: str | None
    similarity_score: float
    cloud_position: str
    prior_high_structure: str
    ichimoku_summary: str
    setup_summary: str
    outcome_label: str
    outcome_summary: str
    matched_features: list[str]
    sparkline: list[float]


def _timestamp_series(df: pd.DataFrame) -> pd.Series:
    if "datetime" in df.columns:
        return pd.to_datetime(df["datetime"], errors="coerce")
    return pd.to_datetime(df["date"], errors="coerce")


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if pd.isna(value):
            return default
        return float(value)
    except Exception:
        return default


def _sparkline_from_window(df: pd.DataFrame, size: int = 24) -> list[float]:
    if df.empty:
        return []
    closes = pd.to_numeric(df["close"], errors="coerce").dropna()
    if closes.empty:
        return []
    if len(closes) > size:
        step = max(1, len(closes) // size)
        closes = closes.iloc[::step].tail(size)
    first = float(closes.iloc[0]) or 1.0
    normalized = [round(float(value) / first, 4) for value in closes]
    return normalized


def _ichimoku_profile(df: pd.DataFrame) -> dict[str, Any]:
    if df.empty or len(df) < 60:
        return {
            "score": 0.5,
            "bias": "neutral",
            "cloud_position": "unknown",
            "prior_high_structure": "unknown",
            "summary": "일목 해석에 필요한 바 수가 아직 충분하지 않습니다.",
            "signals": ["구름대 해석 전에는 패턴과 가격대 중심으로 보세요."],
            "caution": "표본이 더 쌓이면 구름 지지/이탈 해석 품질이 올라갑니다.",
        }

    high = pd.to_numeric(df["high"], errors="coerce")
    low = pd.to_numeric(df["low"], errors="coerce")
    close = pd.to_numeric(df["close"], errors="coerce")
    if high.isna().all() or low.isna().all() or close.isna().all():
        return {
            "score": 0.5,
            "bias": "neutral",
            "cloud_position": "unknown",
            "prior_high_structure": "unknown",
            "summary": "일목 계산에 필요한 가격 데이터가 부족합니다.",
            "signals": [],
            "caution": "고가/저가/종가 데이터가 더 안정적으로 들어오면 다시 평가하세요.",
        }

    conversion = (high.rolling(9).max() + low.rolling(9).min()) / 2
    base = (high.rolling(26).max() + low.rolling(26).min()) / 2
    span_a = (conversion + base) / 2
    span_b = (high.rolling(52).max() + low.rolling(52).min()) / 2
    lagging_close = close.shift(-26)

    current_close = _safe_float(close.iloc[-1], 0.0)
    current_conversion = _safe_float(conversion.iloc[-1], current_close)
    current_base = _safe_float(base.iloc[-1], current_close)
    current_span_a = _safe_float(span_a.iloc[-1], current_close)
    current_span_b = _safe_float(span_b.iloc[-1], current_close)
    current_lagging = _safe_float(lagging_close.iloc[-27] if len(lagging_close) >= 27 else close.iloc[-1], current_close)

    cloud_top = max(current_span_a, current_span_b)
    cloud_bottom = min(current_span_a, current_span_b)
    cloud_thickness = abs(current_span_a - current_span_b) / max(current_close, 1.0)

    if current_close >= cloud_top * 1.01:
        cloud_position = "above_cloud"
    elif current_close >= cloud_top * 0.995:
        cloud_position = "cloud_top_test"
    elif current_close >= cloud_bottom * 0.995:
        cloud_position = "inside_cloud"
    elif current_close >= cloud_bottom * 0.975:
        cloud_position = "cloud_bottom_test"
    else:
        cloud_position = "below_cloud"

    recent = close.tail(min(len(close), 90))
    recent_high = _safe_float(recent.iloc[:-5].max() if len(recent) > 5 else recent.max(), current_close)
    older_window = close.iloc[max(0, len(close) - 140): max(0, len(close) - 35)]
    older_high = _safe_float(older_window.max() if not older_window.empty else recent_high, recent_high)
    if current_close >= max(recent_high, older_high) * 1.005:
        prior_high_structure = "all_highs_cleared"
    elif current_close >= recent_high * 1.005 and current_close < older_high * 1.005:
        prior_high_structure = "recent_high_cleared_old_high_pending"
    elif abs(current_close - recent_high) / max(recent_high, 1.0) <= 0.015:
        prior_high_structure = "recent_high_test"
    else:
        prior_high_structure = "prior_high_below"

    lag_reference = _safe_float(close.iloc[-27] if len(close) >= 27 else current_close, current_close)
    bullish_stack = current_close >= cloud_top and current_conversion >= current_base and current_lagging >= lag_reference
    bearish_stack = current_close <= cloud_bottom and current_conversion <= current_base and current_lagging <= lag_reference

    score = 0.50
    signals: list[str] = []
    caution = ""

    if cloud_position == "above_cloud":
        score += 0.16
        signals.append("가격이 구름 위에 있어 추세 우위가 유지됩니다.")
    elif cloud_position == "cloud_top_test":
        score += 0.10
        signals.append("구름 상단 지지 여부가 핵심입니다.")
    elif cloud_position == "inside_cloud":
        score -= 0.04
        signals.append("가격이 구름 안에 있어 방향성이 아직 덜 선명합니다.")
    elif cloud_position == "cloud_bottom_test":
        score -= 0.10
        signals.append("구름 하단 이탈 여부를 먼저 확인해야 합니다.")
    elif cloud_position == "below_cloud":
        score -= 0.16
        signals.append("가격이 구름 아래에 있어 저항 부담이 큽니다.")

    if current_conversion >= current_base:
        score += 0.08
        signals.append("전환선이 기준선 위에 있어 단기 힘이 유지됩니다.")
    else:
        score -= 0.08
        signals.append("전환선이 기준선 아래라 단기 힘이 약합니다.")

    if current_lagging >= lag_reference:
        score += 0.05
        signals.append("후행스팬도 과거 가격 위에 있어 추세 확인에 우호적입니다.")
    else:
        score -= 0.05
        signals.append("후행스팬이 과거 가격 아래라 추세 확인이 약합니다.")

    if cloud_thickness >= 0.08:
        caution = "구름 두께가 두꺼워 저항 또는 지지 강도가 큰 구간입니다."
        if cloud_position in {"inside_cloud", "below_cloud"}:
            score -= 0.05
    elif cloud_thickness <= 0.03:
        caution = "구름 두께가 얇아 돌파는 쉬울 수 있지만 지지 신뢰도도 함께 얇습니다."

    if bullish_stack:
        bias = "bullish"
        score += 0.05
    elif bearish_stack:
        bias = "bearish"
        score -= 0.05
    else:
        bias = "neutral"

    if not signals:
        signals.append("일목 신호는 중립입니다. 패턴 구조와 가격대 해석을 함께 보세요.")

    score = round(max(0.0, min(1.0, score)), 3)

    summary_parts = []
    if cloud_position == "cloud_top_test":
        summary_parts.append("구름 상단 지지 확인이 붙으면 다시 출발할 수 있는 자리입니다.")
    elif cloud_position == "cloud_bottom_test":
        summary_parts.append("구름 하단 이탈 시 구조가 빠르게 약해질 수 있습니다.")
    elif cloud_position == "inside_cloud":
        summary_parts.append("구름 안이라 결론을 서두르기보다 이탈 방향을 확인하는 편이 좋습니다.")
    elif cloud_position == "above_cloud":
        summary_parts.append("구름 위에서 쉬고 있어 눌림 지지 확인만 되면 재가속 해석이 가능합니다.")
    else:
        summary_parts.append("구름 아래라 바로 추격하기보다 저항 해소 여부가 먼저입니다.")

    if prior_high_structure == "recent_high_cleared_old_high_pending":
        summary_parts.append("직전 고점은 넘겼지만 더 큰 이전 고점은 아직 남아 있습니다.")
    elif prior_high_structure == "all_highs_cleared":
        summary_parts.append("직전 고점과 이전 고점 정리가 함께 된 구조입니다.")
    elif prior_high_structure == "recent_high_test":
        summary_parts.append("직전 고점 테스트 구간이라 종가 안착 여부가 중요합니다.")
    else:
        summary_parts.append("이전 고점 정리가 아직 충분하지 않습니다.")

    return {
        "score": score,
        "bias": bias,
        "cloud_position": cloud_position,
        "prior_high_structure": prior_high_structure,
        "summary": " ".join(summary_parts),
        "signals": signals[:5],
        "caution": caution,
    }


def _distance_to_neckline(pattern: PatternResult, current_close: float) -> float:
    if pattern.neckline is None or current_close <= 0:
        return 0.5
    return min(1.0, abs(current_close - pattern.neckline) / max(current_close * 0.12, 1.0))


def _outcome_from_future(pattern: PatternResult, window_df: pd.DataFrame, future_df: pd.DataFrame) -> tuple[str, str, str | None]:
    if future_df.empty:
        return "관찰 진행", "이후 데이터가 부족해 결과를 끝까지 확인하지 못했습니다.", None

    bullish = pattern.pattern_type in {
        "double_bottom",
        "inverse_head_and_shoulders",
        "ascending_triangle",
        "rectangle",
        "cup_and_handle",
        "rounding_bottom",
        "vcp",
    }
    entry = _safe_float(window_df["close"].iloc[-1], 0.0)
    target = pattern.target_level
    invalidation = pattern.invalidation_level
    best_move = 0.0

    for _, row in future_df.iterrows():
        high = _safe_float(row.get("high"), entry)
        low = _safe_float(row.get("low"), entry)
        ts = row.get("datetime") or row.get("date")
        resolved = ts.isoformat() if hasattr(ts, "isoformat") else str(ts)
        if bullish:
            best_move = max(best_move, (high - entry) / max(entry, 1.0))
            if target is not None and high >= target:
                return "성공", "목표가를 먼저 찍고 진행된 실제 과거 사례입니다.", resolved
            if invalidation is not None and low <= invalidation:
                return "실패", "무효화 가격을 먼저 이탈한 실제 과거 사례입니다.", resolved
        else:
            best_move = max(best_move, (entry - low) / max(entry, 1.0))
            if target is not None and low <= target:
                return "성공", "목표가를 먼저 달성한 실제 과거 사례입니다.", resolved
            if invalidation is not None and high >= invalidation:
                return "실패", "무효화 가격을 먼저 건드린 실제 과거 사례입니다.", resolved

    if best_move >= 0.035:
        return "부분 성공", "목표가까지는 못 갔지만 유의미한 유리한 움직임이 나온 사례입니다.", None
    return "관찰 진행", "뚜렷한 목표 달성도 무효화도 없이 정리된 사례입니다.", None


def _similarity_score(
    *,
    current_pattern: PatternResult,
    current_close: float,
    current_ichimoku: dict[str, Any],
    candidate_pattern: PatternResult,
    candidate_close: float,
    candidate_ichimoku: dict[str, Any],
) -> tuple[float, list[str]]:
    matched: list[str] = []
    score = 0.0

    if candidate_pattern.state == current_pattern.state:
        score += 0.20
        matched.append(f"같은 상태 ({candidate_pattern.state})")
    if candidate_ichimoku["cloud_position"] == current_ichimoku["cloud_position"]:
        score += 0.18
        matched.append("구름대 위치 유사")
    if candidate_ichimoku["prior_high_structure"] == current_ichimoku["prior_high_structure"]:
        score += 0.16
        matched.append("전고점 구조 유사")
    if candidate_ichimoku["bias"] == current_ichimoku["bias"]:
        score += 0.10
        matched.append("일목 방향성 유사")

    similarity_gap = abs(_safe_float(candidate_pattern.textbook_similarity) - _safe_float(current_pattern.textbook_similarity))
    score += max(0.0, 0.18 - similarity_gap * 0.24)

    current_neckline_gap = _distance_to_neckline(current_pattern, current_close)
    candidate_neckline_gap = _distance_to_neckline(candidate_pattern, candidate_close)
    score += max(0.0, 0.10 - abs(current_neckline_gap - candidate_neckline_gap) * 0.24)

    current_cloud_score = _safe_float(current_ichimoku["score"], 0.5)
    candidate_cloud_score = _safe_float(candidate_ichimoku["score"], 0.5)
    score += max(0.0, 0.08 - abs(current_cloud_score - candidate_cloud_score) * 0.12)

    return round(max(0.0, min(1.0, score)), 3), matched


def _scan_symbol_cases(
    *,
    code: str,
    name: str,
    timeframe: str,
    lookback_days: int,
    state: str,
    pattern_type: str,
    current_pattern: PatternResult,
    current_close: float,
    current_ichimoku: dict[str, Any],
) -> list[_ReferenceSnapshot]:
    fetcher = get_data_fetcher()
    # This helper is run inside asyncio, keep it sync-friendly by calling already-fetched data only.
    raise RuntimeError("Use the async wrapper instead.")


async def _collect_symbol_cases(
    *,
    code: str,
    name: str,
    timeframe: str,
    lookback_days: int,
    state: str,
    pattern_type: str,
    current_pattern: PatternResult,
    current_close: float,
    current_ichimoku: dict[str, Any],
) -> list[_ReferenceSnapshot]:
    fetcher = get_data_fetcher()
    try:
        df = await fetcher.get_stock_ohlcv_by_timeframe(code, timeframe, lookback_days=lookback_days)
    except Exception:
        return []
    if df.empty or len(df) < 120:
        return []

    df = df.reset_index(drop=True)
    engine = PatternEngine()
    cfg = get_backtest_config(timeframe)
    window = int(cfg["window"])
    step = max(2, int(cfg["step"]))
    max_forward = int(cfg["max_forward"])
    results: list[_ReferenceSnapshot] = []

    for start_idx in range(0, max(1, len(df) - window - max_forward), step):
        window_df = df.iloc[start_idx:start_idx + window].copy().reset_index(drop=True)
        future_df = df.iloc[start_idx + window:start_idx + window + max_forward].copy().reset_index(drop=True)
        patterns = engine.detect_all(window_df)
        if not patterns:
            continue

        window_ichimoku = _ichimoku_profile(window_df)
        current_window_close = _safe_float(window_df["close"].iloc[-1], 0.0)
        signal_ts = _timestamp_series(window_df).iloc[-1]
        signal_date = signal_ts.date().isoformat() if hasattr(signal_ts, "date") else str(signal_ts)[:10]

        for pattern in patterns:
            if pattern.pattern_type != pattern_type or pattern.state != state:
                continue

            similarity_score, matched = _similarity_score(
                current_pattern=current_pattern,
                current_close=current_close,
                current_ichimoku=current_ichimoku,
                candidate_pattern=pattern,
                candidate_close=current_window_close,
                candidate_ichimoku=window_ichimoku,
            )
            if similarity_score < 0.42:
                continue

            outcome_label, outcome_summary, resolution_date = _outcome_from_future(pattern, window_df, future_df)
            setup_summary = (
                f"{timeframe_label(timeframe)} 기준 {name}의 {pattern_type} {state} 사례입니다. "
                f"{window_ichimoku['summary']}"
            )

            results.append(
                _ReferenceSnapshot(
                    symbol_code=code,
                    symbol_name=name,
                    timeframe=timeframe,
                    pattern_type=pattern_type,
                    state=state,
                    signal_date=signal_date,
                    resolution_date=resolution_date,
                    similarity_score=similarity_score,
                    cloud_position=window_ichimoku["cloud_position"],
                    prior_high_structure=window_ichimoku["prior_high_structure"],
                    ichimoku_summary=window_ichimoku["summary"],
                    setup_summary=setup_summary,
                    outcome_label=outcome_label,
                    outcome_summary=outcome_summary,
                    matched_features=matched[:4],
                    sparkline=_sparkline_from_window(window_df),
                )
            )

    return results


async def build_reference_cases(
    *,
    symbol_code: str,
    timeframe: str,
    analysis: AnalysisResult,
    limit: int = 6,
) -> ReferenceCaseResponse:
    cache_key = f"reference_cases:v2:{symbol_code}:{timeframe}:{limit}"
    cached = await cache_get(cache_key)
    if cached:
        return ReferenceCaseResponse(**cached)

    best_pattern = analysis.patterns[0] if analysis.patterns else None
    if best_pattern is None:
        response = ReferenceCaseResponse(
            generated_at=datetime.utcnow().isoformat(),
            symbol_code=symbol_code,
            symbol_name=analysis.symbol.name,
            timeframe=timeframe,
            timeframe_label=analysis.timeframe_label,
            pattern_type="none",
            state="none",
            ichimoku=analysis.ichimoku,
            items=[],
        )
        await cache_set(cache_key, response.model_dump(), REFERENCE_CASES_TTL)
        return response

    fetcher = get_data_fetcher()
    current_df = await fetcher.get_stock_ohlcv_by_timeframe(symbol_code, timeframe)
    if current_df.empty:
        response = ReferenceCaseResponse(
            generated_at=datetime.utcnow().isoformat(),
            symbol_code=symbol_code,
            symbol_name=analysis.symbol.name,
            timeframe=timeframe,
            timeframe_label=analysis.timeframe_label,
            pattern_type=best_pattern.pattern_type,
            state=best_pattern.state,
            ichimoku=analysis.ichimoku,
            items=[],
        )
        await cache_set(cache_key, response.model_dump(), REFERENCE_CASES_TTL)
        return response

    universe_df = await fetcher.get_universe()
    universe_name_map = (
        universe_df.set_index("code")["name"].to_dict()
        if not universe_df.empty and {"code", "name"}.issubset(universe_df.columns)
        else {}
    )

    lookback_days = max(int(get_backtest_config(timeframe)["lookback_days"]), 730)
    current_close = _safe_float(current_df["close"].iloc[-1], 0.0)
    current_ichimoku = analysis.ichimoku.model_dump()

    universe = [code for code in get_backtest_universe() if code != symbol_code][:24]
    snapshots: list[_ReferenceSnapshot] = []
    for code in universe:
        snapshots.extend(
            await _collect_symbol_cases(
                code=code,
                name=str(universe_name_map.get(code) or code),
                timeframe=timeframe,
                lookback_days=lookback_days,
                state=best_pattern.state,
                pattern_type=best_pattern.pattern_type,
                current_pattern=best_pattern,
                current_close=current_close,
                current_ichimoku=current_ichimoku,
            )
        )

    unique_items: list[ReferenceCaseItem] = []
    seen_keys: set[str] = set()
    for index, item in enumerate(
        sorted(
            snapshots,
            key=lambda row: (row.similarity_score, row.outcome_label == "성공", row.outcome_label == "부분 성공"),
            reverse=True,
        )
    ):
        key = f"{item.symbol_code}:{item.signal_date}:{index}"
        if key in seen_keys:
            continue
        seen_keys.add(key)
        unique_items.append(
            ReferenceCaseItem(
                key=key,
                symbol_code=item.symbol_code,
                symbol_name=item.symbol_name,
                timeframe=item.timeframe,
                timeframe_label=timeframe_label(item.timeframe),
                pattern_type=item.pattern_type,
                state=item.state,
                signal_date=item.signal_date,
                resolution_date=item.resolution_date,
                similarity_score=item.similarity_score,
                cloud_position=item.cloud_position,
                prior_high_structure=item.prior_high_structure,
                ichimoku_summary=item.ichimoku_summary,
                setup_summary=item.setup_summary,
                outcome_label=item.outcome_label,
                outcome_summary=item.outcome_summary,
                matched_features=item.matched_features,
                sparkline=item.sparkline,
                chart_path=f"/chart/{item.symbol_code}",
            )
        )
        if len(unique_items) >= limit:
            break

    response = ReferenceCaseResponse(
        generated_at=datetime.utcnow().isoformat(),
        symbol_code=symbol_code,
        symbol_name=analysis.symbol.name,
        timeframe=timeframe,
        timeframe_label=analysis.timeframe_label,
        pattern_type=best_pattern.pattern_type,
        state=best_pattern.state,
        ichimoku=analysis.ichimoku,
        items=unique_items,
    )
    await cache_set(cache_key, response.model_dump(), REFERENCE_CASES_TTL)
    return response
