"""Pydantic response schemas."""

from __future__ import annotations

from pydantic import BaseModel, Field


class PriceInfo(BaseModel):
    code: str
    close: float
    prev_close: float
    change: float
    change_pct: float
    volume: int
    source: str
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
    volume_context_fit: float = 0.0
    volatility_context_fit: float = 0.0
    breakout_quality_fit: float = 0.0
    retest_quality_fit: float = 0.0
    neckline: float | None
    invalidation_level: float | None
    target_level: float | None
    key_points: list[dict]
    is_provisional: bool
    start_dt: str
    end_dt: str | None
    target_hit_at: str | None = None
    invalidated_at: str | None = None


class ProjectionPoint(BaseModel):
    dt: str
    price: float
    kind: str


class AnalysisResult(BaseModel):
    symbol: SymbolInfo
    timeframe: str
    timeframe_label: str
    p_up: float
    p_down: float
    textbook_similarity: float
    pattern_confirmation_score: float
    confidence: float
    entry_score: float
    completion_proximity: float
    recency_score: float
    reward_risk_ratio: float
    headroom_score: float
    target_distance_pct: float
    stop_distance_pct: float
    trend_alignment_score: float
    trend_direction: str
    trend_warning: str
    no_signal_flag: bool
    no_signal_reason: str
    reason_summary: str
    sample_size: int
    empirical_win_rate: float
    sample_reliability: float
    patterns: list[PatternInfo]
    projection_label: str
    projection_summary: str
    projected_path: list[ProjectionPoint]
    is_provisional: bool
    updated_at: str
    data_source: str
    data_quality: float
    source_note: str
    fetch_status: str
    fetch_status_label: str
    fetch_message: str
    liquidity_score: float
    avg_turnover_billion: float
    bars_since_signal: int | None
    stats_timeframe: str
    available_bars: int


class DashboardItem(BaseModel):
    rank: int
    symbol: SymbolInfo
    timeframe: str
    timeframe_label: str
    pattern_type: str | None
    state: str | None
    p_up: float
    p_down: float
    textbook_similarity: float
    confidence: float
    entry_score: float
    reward_risk_ratio: float = 0.0
    headroom_score: float = 0.0
    target_distance_pct: float = 0.0
    stop_distance_pct: float = 0.0
    trend_alignment_score: float = 0.0
    trend_direction: str = "sideways"
    trend_warning: str = ""
    no_signal_flag: bool
    reason_summary: str
    completion_proximity: float = 0.0
    recency_score: float = 0.0
    data_source: str = "unknown"
    data_quality: float = 0.0
    source_note: str = ""
    fetch_status: str = "unknown"
    fetch_message: str = ""
    liquidity_score: float = 0.0
    avg_turnover_billion: float = 0.0
    sample_size: int = 0
    empirical_win_rate: float = 0.5
    sample_reliability: float = 0.0
    stats_timeframe: str = "1d"
    available_bars: int = 0
    fetch_status_label: str = "상태 정보 없음"
    confluence_score: float = 0.0
    confluence_summary: str = ""
    scenario_text: str = ""


class DashboardResponse(BaseModel):
    category: str
    timeframe: str
    timeframe_label: str
    items: list[DashboardItem]
    generated_at: str


class ScanStatusResponse(BaseModel):
    timeframe: str
    timeframe_label: str
    status: str
    is_running: bool
    source: str | None = None
    candidate_source: str | None = None
    candidate_count: int | None = None
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
    direction: str
    description: str
    structure_conditions: list[str]
    volume_conditions: list[str]
    confirmation_conditions: list[str]
    invalidation_conditions: list[str]
    cautions: list[str]
    svg_path: str | None


class ScreenerRequest(BaseModel):
    pattern_types: list[str] | None = None
    states: list[str] | None = None
    markets: list[str] | None = None
    fetch_statuses: list[str] | None = None
    min_textbook_similarity: float = 0.0
    min_p_up: float = 0.0
    max_p_down: float = 1.0
    min_confidence: float = 0.0
    min_sample_reliability: float = 0.0
    min_data_quality: float = 0.0
    min_confluence_score: float = 0.0
    timeframes: list[str] | None = None
    min_market_cap: float | None = None
    exclude_no_signal: bool = True
    sort_by: str = "composite_score"
    limit: int = Field(default=50, ge=1, le=100)
