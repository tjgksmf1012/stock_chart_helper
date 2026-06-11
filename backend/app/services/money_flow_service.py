"""
Foreign investor / institution net buying data via pykrx.
Data is T+1 (previous trading day). Cached for 4 hours.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, timedelta

import pandas as pd

from ..core.redis import cache_get, cache_set

logger = logging.getLogger(__name__)

_CACHE_PREFIX = "moneyflow:v2"
_CACHE_TTL = 14400  # 4시간

_BULLISH_PATTERNS = {
    "double_bottom", "inverse_head_and_shoulders", "ascending_triangle",
    "rectangle", "cup_and_handle", "rounding_bottom", "vcp",
}
_BEARISH_PATTERNS = {
    "double_top", "head_and_shoulders", "descending_triangle",
}

# 수급 방향성 유의미 임계치 (50억원)
_THRESHOLD_BILLION = 50.0


def _to_billion(krw: float) -> float:
    return round(krw / 1e8, 1)


def _parse_flow_columns(df: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    """외국인합계, 기관합계 시리즈를 추출. 컬럼명이 버전마다 다를 수 있음."""
    foreign_col = next(
        (c for c in df.columns if "외국인" in c and "합계" in c), None
    ) or next(
        (c for c in df.columns if "외국인" in c), None
    )
    institution_col = next(
        (c for c in df.columns if "기관" in c and "합계" in c), None
    ) or next(
        (c for c in df.columns if "기관" in c), None
    )

    foreign_s = pd.to_numeric(df[foreign_col], errors="coerce").fillna(0) if foreign_col else pd.Series(0.0, index=df.index)
    inst_s = pd.to_numeric(df[institution_col], errors="coerce").fillna(0) if institution_col else pd.Series(0.0, index=df.index)
    return foreign_s, inst_s


def _compute_alignment(
    foreign_3d: float,
    institution_3d: float,
    pattern_type: str | None,
) -> tuple[str, str, str]:
    """Returns (alignment, alignment_label, alignment_note)."""
    if pattern_type in _BULLISH_PATTERNS:
        pattern_bias = "bullish"
    elif pattern_type in _BEARISH_PATTERNS:
        pattern_bias = "bearish"
    else:
        return "neutral", "수급 중립", "패턴 없음"

    combined = foreign_3d * 0.6 + institution_3d * 0.4

    if abs(combined) < _THRESHOLD_BILLION:
        return "neutral", "수급 뚜렷하지 않음", "외인+기관 합산 순매수 규모 미미"

    flow_is_bullish = combined > 0
    pattern_is_bullish = pattern_bias == "bullish"
    foreign_is_bullish = foreign_3d > _THRESHOLD_BILLION
    institution_is_bullish = institution_3d > _THRESHOLD_BILLION

    # 외인/기관 방향 엇갈리면 mixed
    if (abs(foreign_3d) > _THRESHOLD_BILLION
            and abs(institution_3d) > _THRESHOLD_BILLION
            and foreign_is_bullish != institution_is_bullish):
        label = f"외국인 {'순매수' if foreign_is_bullish else '순매도'} / 기관 {'순매수' if institution_is_bullish else '순매도'}"
        return "mixed", label, "외국인·기관 방향 엇갈림 — 신중한 접근 필요"

    if flow_is_bullish == pattern_is_bullish:
        return "aligned", "패턴과 수급 방향 일치", "외인+기관 자금이 패턴 방향을 지지"
    else:
        return "diverged", "패턴과 수급 방향 반대", "외인+기관 자금이 패턴 방향과 반대 — 주의 필요"


def _build_result(
    daily_rows: list[dict],
    pattern_type: str | None,
) -> dict:
    """daily_rows: [{date, foreign, institution}] (억원, 시간순) → 응답 dict."""
    foreign_values = [row["foreign"] for row in daily_rows]
    institution_values = [row["institution"] for row in daily_rows]

    foreign_3d = round(sum(foreign_values[-3:]), 1) if len(foreign_values) >= 3 else 0.0
    foreign_10d = round(sum(foreign_values[-10:]), 1) if len(foreign_values) >= 10 else 0.0
    institution_3d = round(sum(institution_values[-3:]), 1) if len(institution_values) >= 3 else 0.0
    institution_10d = round(sum(institution_values[-10:]), 1) if len(institution_values) >= 10 else 0.0

    alignment, alignment_label, alignment_note = _compute_alignment(
        foreign_3d, institution_3d, pattern_type
    )
    return {
        "foreign_net_3d": foreign_3d,
        "foreign_net_10d": foreign_10d,
        "institution_net_3d": institution_3d,
        "institution_net_10d": institution_10d,
        "alignment": alignment,
        "alignment_label": alignment_label,
        "alignment_note": alignment_note,
        "daily": daily_rows[-20:],
    }


async def _fetch_daily_rows_kis(code: str) -> list[dict] | None:
    """KIS 투자자별 매매동향 → [{date, foreign, institution}] (억원)."""
    from .kis_client import get_kis_client

    kis = get_kis_client()
    if not kis.configured:
        return None

    trends = await asyncio.wait_for(kis.fetch_investor_trends(code), timeout=15.0)
    if not trends:
        return None

    # KIS 거래대금은 백만원 단위 → 억원 = /100
    return [
        {
            "date": row["date"],
            "foreign": round(row["foreign_value_million"] / 100.0, 1),
            "institution": round(row["institution_value_million"] / 100.0, 1),
        }
        for row in trends
    ]


async def _fetch_daily_rows_pykrx(code: str) -> list[dict] | None:
    """pykrx 폴백. KRX 로그인 필수화 이후 빈 응답일 수 있음 (KRX_ID/KRX_PW 필요)."""
    from pykrx import stock as krx

    end = date.today()
    start = end - timedelta(days=40)  # 거래일 기준 약 28일 확보

    df = await asyncio.wait_for(
        asyncio.to_thread(
            krx.get_market_trading_value_by_date,
            start.strftime("%Y%m%d"),
            end.strftime("%Y%m%d"),
            code,
        ),
        timeout=15.0,
    )
    if df is None or df.empty:
        return None

    foreign_s, inst_s = _parse_flow_columns(df)
    rows = []
    for idx in df.index:
        date_str = idx.strftime("%Y-%m-%d") if hasattr(idx, "strftime") else str(idx)
        rows.append({
            "date": date_str,
            "foreign": _to_billion(float(foreign_s.get(idx, 0) or 0)),
            "institution": _to_billion(float(inst_s.get(idx, 0) or 0)),
        })
    return rows


async def get_money_flow(code: str, pattern_type: str | None = None) -> dict | None:
    """
    Returns money flow dict for given stock code, or None on failure.
    {
        foreign_net_3d, foreign_net_10d,
        institution_net_3d, institution_net_10d,
        alignment, alignment_label, alignment_note,
        daily: [{ date, foreign, institution }]
    }

    KIS 투자자별 매매동향을 주 소스로 사용 (pykrx 투자자 API는 KRX 로그인
    필수화로 무인증 환경에서 빈 데이터를 반환).
    """
    cache_key = f"{_CACHE_PREFIX}:{code}"
    cached = await cache_get(cache_key)
    if cached:
        # alignment는 패턴에 따라 달라지므로 재계산
        alignment, alignment_label, alignment_note = _compute_alignment(
            cached.get("foreign_net_3d", 0),
            cached.get("institution_net_3d", 0),
            pattern_type,
        )
        cached.update({
            "alignment": alignment,
            "alignment_label": alignment_label,
            "alignment_note": alignment_note,
        })
        return cached

    daily_rows: list[dict] | None = None
    try:
        daily_rows = await _fetch_daily_rows_kis(code)
    except Exception as exc:
        logger.warning("KIS money flow fetch failed for %s: %s", code, exc)

    if not daily_rows:
        try:
            daily_rows = await _fetch_daily_rows_pykrx(code)
        except Exception as exc:
            logger.warning("pykrx money flow fetch failed for %s: %s", code, exc)

    if not daily_rows:
        return None

    result = _build_result(daily_rows, pattern_type)
    # 캐시 저장 (alignment 제외 버전 — alignment는 패턴에 따라 재계산)
    cacheable = {k: v for k, v in result.items() if k not in ("alignment", "alignment_label", "alignment_note")}
    await cache_set(cache_key, cacheable, ttl=_CACHE_TTL)
    return result
