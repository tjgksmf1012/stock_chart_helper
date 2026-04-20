from __future__ import annotations

import asyncio
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

from ..core.config import get_settings


class IntradayStore:
    """SQLite-backed cache for intraday bars."""

    def __init__(self) -> None:
        self._settings = get_settings()
        self._db_path = self._resolve_path(self._settings.intraday_storage_path)
        self._retention_days = max(7, int(self._settings.intraday_store_retention_days))
        self._init_lock = asyncio.Lock()
        self._write_lock = asyncio.Lock()
        self._ready = False

    def _resolve_path(self, configured_path: str) -> Path:
        path = Path(configured_path)
        if path.is_absolute():
            return path
        backend_root = Path(__file__).resolve().parents[2]
        return backend_root / path

    async def ensure_ready(self) -> None:
        if self._ready:
            return
        async with self._init_lock:
            if self._ready:
                return
            await asyncio.to_thread(self._initialize)
            self._ready = True

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA busy_timeout=30000")
        return conn

    def _initialize(self) -> None:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS intraday_bars (
                    symbol TEXT NOT NULL,
                    timeframe TEXT NOT NULL,
                    bar_time TEXT NOT NULL,
                    open REAL NOT NULL,
                    high REAL NOT NULL,
                    low REAL NOT NULL,
                    close REAL NOT NULL,
                    volume INTEGER NOT NULL,
                    amount REAL,
                    source TEXT,
                    fetched_at TEXT NOT NULL,
                    PRIMARY KEY (symbol, timeframe, bar_time)
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_intraday_bars_lookup
                ON intraday_bars (symbol, timeframe, bar_time DESC)
                """
            )

    async def upsert_bars(self, *, symbol: str, timeframe: str, df: pd.DataFrame, source: str) -> None:
        if df.empty:
            return
        await self.ensure_ready()
        async with self._write_lock:
            await asyncio.to_thread(self._upsert_bars_sync, symbol, timeframe, df, source)

    def _upsert_bars_sync(self, symbol: str, timeframe: str, df: pd.DataFrame, source: str) -> None:
        rows: list[tuple[object, ...]] = []
        fetched_at = datetime.utcnow().isoformat()
        for _, row in df.iterrows():
            stamp = pd.Timestamp(row["datetime"]).to_pydatetime().replace(tzinfo=None).isoformat()
            amount = row.get("amount")
            rows.append(
                (
                    symbol,
                    timeframe,
                    stamp,
                    float(row["open"]),
                    float(row["high"]),
                    float(row["low"]),
                    float(row["close"]),
                    int(row["volume"]),
                    float(amount) if amount is not None and str(amount) != "nan" else None,
                    source,
                    fetched_at,
                )
            )

        retention_cutoff = (datetime.utcnow() - timedelta(days=self._retention_days)).isoformat()
        with self._connect() as conn:
            conn.executemany(
                """
                INSERT INTO intraday_bars (
                    symbol, timeframe, bar_time, open, high, low, close, volume, amount, source, fetched_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(symbol, timeframe, bar_time) DO UPDATE SET
                    open = excluded.open,
                    high = excluded.high,
                    low = excluded.low,
                    close = excluded.close,
                    volume = excluded.volume,
                    amount = excluded.amount,
                    source = excluded.source,
                    fetched_at = excluded.fetched_at
                """,
                rows,
            )
            conn.execute("DELETE FROM intraday_bars WHERE fetched_at < ?", (retention_cutoff,))

    async def load_bars(self, *, symbol: str, timeframe: str, lookback_days: int) -> pd.DataFrame:
        await self.ensure_ready()
        return await asyncio.to_thread(self._load_bars_sync, symbol, timeframe, lookback_days)

    def _load_bars_sync(self, symbol: str, timeframe: str, lookback_days: int) -> pd.DataFrame:
        cutoff = (datetime.utcnow() - timedelta(days=max(1, lookback_days) + 2)).isoformat()
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT bar_time, open, high, low, close, volume, amount, source, fetched_at
                FROM intraday_bars
                WHERE symbol = ? AND timeframe = ? AND bar_time >= ?
                ORDER BY bar_time ASC
                """,
                (symbol, timeframe, cutoff),
            ).fetchall()

        if not rows:
            df = pd.DataFrame()
            df.attrs["data_source"] = "intraday_store"
            df.attrs["fetch_status"] = "stored_empty"
            df.attrs["fetch_message"] = "No previously stored intraday bars are available."
            return df

        frame = pd.DataFrame(rows, columns=["datetime", "open", "high", "low", "close", "volume", "amount", "source", "fetched_at"])
        frame["datetime"] = pd.to_datetime(frame["datetime"]).dt.tz_localize(None)
        latest_fetch = pd.to_datetime(frame["fetched_at"]).max()
        age_minutes = None
        if latest_fetch is not None and not pd.isna(latest_fetch):
            age_minutes = int(max(0, (datetime.utcnow() - latest_fetch.to_pydatetime()).total_seconds() // 60))

        source = str(frame["source"].dropna().iloc[-1]) if frame["source"].notna().any() else "intraday_store"
        result = frame[["datetime", "open", "high", "low", "close", "volume", "amount"]].copy()
        result.attrs["data_source"] = "intraday_store"
        result.attrs["stored_source"] = source
        result.attrs["fetch_status"] = "stored_available"
        result.attrs["fetch_message"] = "Stored intraday bars are available."
        result.attrs["storage_age_minutes"] = age_minutes
        return result

    async def get_status(self) -> dict[str, object]:
        await self.ensure_ready()
        return await asyncio.to_thread(self._get_status_sync)

    def _get_status_sync(self) -> dict[str, object]:
        with self._connect() as conn:
            total_rows = int(conn.execute("SELECT COUNT(*) FROM intraday_bars").fetchone()[0])
            symbol_count = int(conn.execute("SELECT COUNT(DISTINCT symbol) FROM intraday_bars").fetchone()[0])
            timeframe_rows = conn.execute(
                """
                SELECT timeframe, COUNT(*) AS rows, COUNT(DISTINCT symbol) AS symbols, MAX(fetched_at) AS latest_fetched_at
                FROM intraday_bars
                GROUP BY timeframe
                ORDER BY timeframe
                """
            ).fetchall()
            latest = conn.execute("SELECT MAX(fetched_at) FROM intraday_bars").fetchone()[0]

        return {
            "path": str(self._db_path),
            "retention_days": self._retention_days,
            "total_rows": total_rows,
            "symbol_count": symbol_count,
            "latest_fetched_at": latest,
            "timeframes": [
                {
                    "timeframe": row["timeframe"],
                    "rows": int(row["rows"]),
                    "symbols": int(row["symbols"]),
                    "latest_fetched_at": row["latest_fetched_at"],
                }
                for row in timeframe_rows
            ],
        }


_intraday_store: IntradayStore | None = None


def get_intraday_store() -> IntradayStore:
    global _intraday_store
    if _intraday_store is None:
        _intraday_store = IntradayStore()
    return _intraday_store
