"""관심종목 가격 알림 — 돌파선/손절/익절 도달 시 텔레그램 발송.

장중 10분 간격 스케줄 잡(run_watchlist_alert_check)이 관심종목의 현재가를
기준 가격들과 비교한다. 같은 레벨은 하루 1회만 발송(레디스 dedup).
텔레그램 미설정이면 전체가 no-op.
"""
from __future__ import annotations

import logging
from datetime import UTC, date, datetime, timedelta
from typing import Any

from ..core.config import get_settings
from ..core.redis import cache_get, cache_set
from .analysis_service import ANALYSIS_CACHE_PREFIX, analyze_symbol_dataframe, build_no_signal_snapshot
from .backtest_engine import _is_bullish
from .data_fetcher import get_data_fetcher
from .kis_client import get_kis_client
from .notification_service import send_telegram_message, telegram_configured
from .scanner import WATCHLIST_CACHE_KEY

logger = logging.getLogger(__name__)
settings = get_settings()

_ALERT_DEDUP_PREFIX = "alert:v1"
_MAX_WATCHLIST_CHECK = 20  # free tier 보호 — 관심종목 상위 20개까지만 점검

_KIND_LABELS = {
    "trigger": "돌파선 도달",
    "target": "익절 기준가 도달",
    "stop": "손절 기준가 이탈",
}


def _evaluate_levels(
    pattern_type: str | None,
    *,
    neckline: float | None,
    invalidation: float | None,
    target: float | None,
    price: float,
) -> list[dict[str, Any]]:
    """현재가가 기준 가격을 건드렸는지 판정 (순수 함수).

    상방 패턴: 목표 도달이 돌파선 도달을 대체(둘 다 해당되면 목표만),
    손절 이탈은 독립적으로 판정. 하방 패턴은 방향 반전.
    """
    if not pattern_type or price <= 0:
        return []

    alerts: list[dict[str, Any]] = []
    bullish = _is_bullish(pattern_type)
    if bullish:
        if target and price >= target:
            alerts.append({"kind": "target", "level": target})
        elif neckline and price >= neckline:
            alerts.append({"kind": "trigger", "level": neckline})
        if invalidation and price <= invalidation:
            alerts.append({"kind": "stop", "level": invalidation})
    else:
        if target and price <= target:
            alerts.append({"kind": "target", "level": target})
        elif neckline and price <= neckline:
            alerts.append({"kind": "trigger", "level": neckline})
        if invalidation and price >= invalidation:
            alerts.append({"kind": "stop", "level": invalidation})
    return alerts


async def _current_price(code: str) -> float | None:
    kis = get_kis_client()
    if kis.configured:
        try:
            data = await kis.fetch_current_price(code)
            if data and data.get("close"):
                return float(data["close"])
        except Exception:
            pass
    try:
        fetcher = get_data_fetcher()
        end = date.today()
        df = await fetcher.get_stock_ohlcv(code, end - timedelta(days=7), end)
        if df is not None and not df.empty:
            return float(df["close"].iloc[-1])
    except Exception:
        pass
    return None


async def _get_pattern_levels(code: str) -> dict[str, Any] | None:
    """일봉 분석에서 기준 가격(돌파/손절/익절) 추출 — 캐시 우선, 없으면 계산."""
    cached = await cache_get(f"{ANALYSIS_CACHE_PREFIX}:{code}:1d")
    analysis_dict: dict[str, Any] | None = cached if isinstance(cached, dict) else None

    if analysis_dict is None:
        try:
            from ..api.schemas import SymbolInfo

            fetcher = get_data_fetcher()
            df = await fetcher.get_stock_ohlcv_by_timeframe(code, "1d")
            name = await fetcher.get_stock_name(code)
            symbol_info = SymbolInfo(code=code, name=name, market="KRX", sector=None, market_cap=None, is_in_universe=True)
            result = (
                await analyze_symbol_dataframe(symbol_info, "1d", df)
                if df is not None and not df.empty
                else build_no_signal_snapshot(symbol_info, "1d", df)
            )
            analysis_dict = result.model_dump()
            await cache_set(f"{ANALYSIS_CACHE_PREFIX}:{code}:1d", analysis_dict, settings.pattern_cache_ttl)
        except Exception as exc:
            logger.warning("alert level analysis failed for %s: %s", code, exc)
            return None

    patterns = analysis_dict.get("patterns") or []
    if not patterns or analysis_dict.get("no_signal_flag"):
        return None
    pattern = patterns[0]
    return {
        "pattern_type": pattern.get("pattern_type"),
        "neckline": pattern.get("neckline"),
        "invalidation": pattern.get("invalidation_level"),
        "target": pattern.get("target_level"),
    }


async def run_watchlist_alert_check() -> dict[str, int]:
    """관심종목 전체 점검 — 스케줄 잡에서 호출."""
    if not telegram_configured():
        return {"checked": 0, "sent": 0}

    stored = await cache_get(WATCHLIST_CACHE_KEY)
    rows = stored if isinstance(stored, list) else []
    today = datetime.now(UTC).strftime("%Y-%m-%d")
    checked = sent = 0

    for item in rows[:_MAX_WATCHLIST_CHECK]:
        if not isinstance(item, dict):
            continue
        code = str(item.get("code") or "").strip()
        name = str(item.get("name") or code)
        if not code:
            continue

        levels = await _get_pattern_levels(code)
        if not levels:
            continue
        price = await _current_price(code)
        if price is None:
            continue
        checked += 1

        for alert in _evaluate_levels(
            levels["pattern_type"],
            neckline=levels["neckline"],
            invalidation=levels["invalidation"],
            target=levels["target"],
            price=price,
        ):
            dedup_key = f"{_ALERT_DEDUP_PREFIX}:{code}:{alert['kind']}:{today}"
            if await cache_get(dedup_key):
                continue
            label = _KIND_LABELS[alert["kind"]]
            text = (
                f"🔔 {name}({code}) {label}\n"
                f"기준 {alert['level']:,.0f}원 · 현재가 {price:,.0f}원\n"
                f"https://stockcharthelper.vercel.app/chart/{code}"
            )
            if await send_telegram_message(text):
                await cache_set(dedup_key, {"at": datetime.now(UTC).isoformat()}, ttl=86400)
                sent += 1

    if checked:
        logger.info("watchlist alert check: %d checked, %d sent", checked, sent)
    return {"checked": checked, "sent": sent}
