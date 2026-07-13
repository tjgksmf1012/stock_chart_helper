"""marcap 데이터셋 기반 시점 고정 유니버스 — KRX 로그인 없는 pit 경로.

FinanceData/marcap (GitHub 공개 배포, 연도별 parquet)은 상장폐지 종목을
포함한 전 종목의 일별 시가총액을 담고 있어, 증권사 API(토스/KIS —
현재 거래 가능 종목만 제공)로는 불가능한 생존 편향 제거가 가능하다.

파일은 backend/data/marcap/marcap-YYYY.parquet 에 있어야 한다:
  curl -sL -o data/marcap/marcap-2022.parquet \
      https://github.com/FinanceData/marcap/raw/master/data/marcap-2022.parquet

주의: 유니버스 선정은 편향이 없어지지만, 뽑힌 상폐 종목의 시세를 현재
데이터 소스가 못 주면 커버리지가 떨어진다 — 호출부는 커버리지를 리포트에
기록하고, 낮으면(<90%) pass를 watch로 강등해야 한다 (상폐 종목 트레이드가
빠지는 방향의 잔여 편향). marcap 자체에 OHLCV가 있으므로, 차기 단계에서
상폐 종목 bars 폴백 소스로 쓸 수 있다.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from .universe import select_top_by_market_cap

logger = logging.getLogger(__name__)

_DEFAULT_DIR = Path(__file__).resolve().parents[2] / "data" / "marcap"


def load_marcap_caps(asof: date, data_dir: Path | None = None, max_back_days: int = 10) -> pd.Series:
    """asof(휴장이면 직전 영업일)의 종목코드→시가총액 Series. 파일 없으면 빈 Series."""
    directory = data_dir or _DEFAULT_DIR
    path = directory / f"marcap-{asof.year}.parquet"
    frames: list[pd.DataFrame] = []
    for candidate in (path, directory / f"marcap-{asof.year - 1}.parquet"):
        if candidate.exists():
            try:
                frames.append(pd.read_parquet(candidate, columns=["Date", "Code", "Marcap"]))
            except Exception as exc:
                logger.warning("marcap parquet read failed (%s): %s", candidate, exc)
    if not frames:
        logger.warning("marcap 데이터 없음: %s — README의 다운로드 안내를 참고하세요", path)
        return pd.Series(dtype=float)

    merged = pd.concat(frames, ignore_index=True)
    merged["Date"] = pd.to_datetime(merged["Date"]).dt.date
    floor = asof - timedelta(days=max_back_days)
    window = merged[(merged["Date"] <= asof) & (merged["Date"] >= floor)]
    if window.empty:
        return pd.Series(dtype=float)
    latest = window["Date"].max()
    snapshot = window[window["Date"] == latest]
    return pd.Series(
        pd.to_numeric(snapshot["Marcap"], errors="coerce").values,
        index=snapshot["Code"].astype(str).str.zfill(6),
    )


def point_in_time_universe_from_marcap(
    asof: date, top_n: int, data_dir: Path | None = None
) -> list[str]:
    return select_top_by_market_cap(load_marcap_caps(asof, data_dir), top_n)
