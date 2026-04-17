"""Pydantic response schemas."""
from pydantic import BaseModel
from datetime import datetime, date
from typing import Any


class PriceInfo(BaseModel):
    code: str
    close: float
    prev_close: float
    change: float
    change_pct: float
    volume: int
    source: str           # "kis" | "pykrx" | "none"
    timestamp: str | None = None


class SymbolInfo(BaseModel):
    code: str
    name: str
    market: str
    sector: str | None
    market_cap: float | None
    is_in_universe: bool


class OHLCVBar(BaseModel):
    date: str
    open: float
    high: float
    low: float
    close: float
    volume: int
    amount: float | None = None


class PatternInfo(BaseModel):
    pattern_type: str
    state: str
    grade: str
    textbook_similarity: float
    geometry_fit: float
    neckline: float | None
    invalidation_level: float | None
    target_level: float | None
    key_points: list[dict]
    is_provisional: bool
    start_dt: str
    end_dt: str | None


class AnalysisResult(BaseModel):
    symbol: SymbolInfo
    timeframe: str
    p_up: float
    p_down: float
    textbook_similarity: float
    pattern_confirmation_score: float
    confidence: float
    entry_score: float
    no_signal_flag: bool
    no_signal_reason: str
    reason_summary: str
    sample_size: int
    patterns: list[PatternInfo]
    is_provisional: bool
    updated_at: str


class DashboardItem(BaseModel):
    rank: int
    symbol: SymbolInfo
    pattern_type: str | None
    state: str | None
    p_up: float
    p_down: float
    textbook_similarity: float
    confidence: float
    entry_score: float
    no_signal_flag: bool
    reason_summary: str


class DashboardResponse(BaseModel):
    category: str
    items: list[DashboardItem]
    generated_at: str


class ScanStatusResponse(BaseModel):
    status: str
    is_running: bool
    source: str | None = None
    cached_result_count: int = 0
    universe_size: int | None = None
    last_started_at: str | None = None
    last_finished_at: str | None = None
    last_error: str | None = None
    duration_ms: int | None = None
    trigger_accepted: bool | None = None


class PatternLibraryEntry(BaseModel):
    pattern_type: str
    name_kr: str
    grade: str
    direction: str         # bullish | bearish | neutral
    description: str
    structure_conditions: list[str]
    volume_conditions: list[str]
    confirmation_conditions: list[str]
    invalidation_conditions: list[str]
    cautions: list[str]
    svg_path: str | None   # relative path to reference SVG


class ScreenerRequest(BaseModel):
    pattern_types: list[str] | None = None
    states: list[str] | None = None
    markets: list[str] | None = None
    min_textbook_similarity: float = 0.0
    min_p_up: float = 0.0
    max_p_down: float = 1.0
    min_confidence: float = 0.0
    timeframes: list[str] | None = None
    min_market_cap: float | None = None
    exclude_no_signal: bool = True
    sort_by: str = "entry_score"
    limit: int = 50
