"""marcap parquet을 상폐 종목 시세(bars) 폴백으로 쓰기 위한 로더.

marcap 가격은 무보정 원시가라 액면분할/병합일에 가짜 점프가 생긴다.
상장주식수(Stocks) 변동으로 분할을 감지해 back-adjust 한다.
한계: 배당락은 보정하지 않는다 (모멘텀에 소폭 불리한 왜곡 — 스펙에 명시).
유상증자도 주식수 점프로 잡히지만, 증자 시 권리락 가격 조정이 실제로
발생하므로 근사로는 분할과 같은 취급이 무보정보다 낫다.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

_DEFAULT_DIR = Path(__file__).resolve().parents[2] / "data" / "marcap"
_RAW_COLS = ["Date", "Code", "Open", "High", "Low", "Close", "Volume", "Stocks"]
_SPLIT_THRESHOLD = 0.05  # 주식수가 하루 새 5% 넘게 변하면 분할/병합으로 판정
_PRICE_COLS = ("open", "high", "low", "close")


def adjust_for_splits(df: pd.DataFrame) -> pd.DataFrame:
    """date 오름차순 bars의 분할 back-adjust. stocks 컬럼 없으면 그대로 반환."""
    if df.empty or "stocks" not in df.columns:
        return df
    out = df.copy()
    stocks = out["stocks"].astype(float).tolist()
    factor = 1.0
    factors = [1.0] * len(out)
    # 뒤에서 앞으로: t일→t+1일 주식수 점프가 있으면 t 이하 전체에 비율 누적
    for i in range(len(out) - 2, -1, -1):
        prev_s, next_s = stocks[i], stocks[i + 1]
        if prev_s > 0 and next_s > 0 and abs(next_s / prev_s - 1) > _SPLIT_THRESHOLD:
            factor *= prev_s / next_s
        factors[i] = factor
    for col in _PRICE_COLS:
        out[col] = out[col].astype(float) * factors
    out["volume"] = out["volume"].astype(float) / factors
    return out


def load_marcap_bars(code: str, data_dir: Path | None = None) -> pd.DataFrame | None:
    """연도별 marcap parquet에서 한 종목의 일봉을 모아 분할 보정 후 반환. 없으면 None."""
    directory = data_dir or _DEFAULT_DIR
    frames: list[pd.DataFrame] = []
    for path in sorted(directory.glob("marcap-*.parquet")):
        try:
            df = pd.read_parquet(path, columns=_RAW_COLS)
        except Exception:
            continue
        part = df[df["Code"].astype(str).str.zfill(6) == code]
        if not part.empty:
            frames.append(part)
    if not frames:
        return None
    merged = pd.concat(frames, ignore_index=True)
    merged.columns = [c.lower() for c in merged.columns]
    merged["date"] = pd.to_datetime(merged["date"]).dt.date
    for col in ("open", "high", "low", "close", "volume", "stocks"):
        merged[col] = pd.to_numeric(merged[col], errors="coerce")
    merged = merged[(merged["close"] > 0) & (merged["open"] > 0)]
    if merged.empty:
        return None
    merged = merged.sort_values("date").drop_duplicates("date").reset_index(drop=True)
    adjusted = adjust_for_splits(merged)
    return adjusted[["date", "open", "high", "low", "close", "volume"]].reset_index(drop=True)


def merge_bars_with_fallback(
    fetched: dict[str, pd.DataFrame],
    codes: list[str],
    fallback_loader,
    min_bars: int = 150,
) -> tuple[dict[str, pd.DataFrame], int]:
    """fetcher가 못 채운 코드만 폴백으로 보완. (병합 결과, 폴백 사용 종목 수)."""
    merged = dict(fetched)
    n_fallback = 0
    for code in codes:
        if code in merged:
            continue
        try:
            bars = fallback_loader(code)
        except Exception:
            continue
        if bars is not None and len(bars) >= min_bars:
            merged[code] = bars.reset_index(drop=True)
            n_fallback += 1
    return merged, n_fallback
