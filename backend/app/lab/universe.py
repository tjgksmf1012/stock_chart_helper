"""시점 고정(point-in-time) 유니버스 — 생존 편향 제거의 핵심 (스펙 §2).

현재 시총 상위를 과거로 돌려보면 "지금까지 살아남아 커진 종목"만 보게 된다.
리밸런스 시점마다 그 날짜 기준의 시총 상위를 pykrx로 다시 뽑는다.
순수 선택 로직과 pykrx IO를 분리해 선택 로직만 단위 테스트한다.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import date, timedelta

import pandas as pd

logger = logging.getLogger(__name__)


def select_top_by_market_cap(cap_by_code: pd.Series, top_n: int) -> list[str]:
    """시가총액 Series(index=종목코드)에서 유효값만 정렬해 상위 top_n 코드 반환."""
    if cap_by_code.empty:
        return []
    valid = cap_by_code.dropna()
    valid = valid[valid > 0]
    return valid.sort_values(ascending=False).head(top_n).index.tolist()


async def fetch_point_in_time_universe(asof: date, top_n: int, max_back_days: int = 10) -> list[str]:
    """asof 시점의 KOSPI+KOSDAQ 시총 상위 top_n. 휴장일이면 며칠 거슬러 재시도.

    pykrx 실패 시 빈 목록 반환 — 호출부(CLI)가 커버리지에 기록하고 해당
    윈도우를 건너뛴다 (조용히 현재 유니버스로 대체하지 않는다).
    """
    from pykrx import stock as krx

    for back in range(max_back_days + 1):
        day = asof - timedelta(days=back)
        stamp = day.strftime("%Y%m%d")
        try:
            frames = await asyncio.gather(
                asyncio.to_thread(krx.get_market_cap_by_ticker, stamp, "KOSPI"),
                asyncio.to_thread(krx.get_market_cap_by_ticker, stamp, "KOSDAQ"),
            )
            merged = pd.concat(frames)
            if merged.empty or "시가총액" not in merged.columns:
                continue
            return select_top_by_market_cap(merged["시가총액"].astype(float), top_n)
        except Exception as exc:
            logger.warning("point-in-time universe fetch failed for %s: %s", stamp, exc)
    return []


async def fetch_current_universe_biased(top_n: int) -> list[str]:
    """현재 상장 목록 기준 시총 상위 — 시점 고정이 아니라 **생존 편향이 있다**.

    KRX 로그인(KRX_ID/KRX_PW) 없이 pykrx 시점 조회가 막힌 환경을 위한 명시적
    대체 모드. 과거에 상폐·편출된 종목이 빠져 있어 성적이 실제보다 좋게 나오는
    방향의 편향이므로, 이 모드로 낸 결과는 리포트에 편향을 기록해야 하고
    'pass' 판정의 근거로 쓸 수 없다 (호출부가 watch로 강등).
    """
    from ..services.data_fetcher import get_data_fetcher

    universe = await get_data_fetcher().get_universe()
    if universe.empty or "market_cap" not in universe.columns:
        return []
    caps = pd.Series(
        pd.to_numeric(universe["market_cap"], errors="coerce").values,
        index=universe["code"].astype(str),
    )
    return select_top_by_market_cap(caps, top_n)
