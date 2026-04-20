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
    variant: str | None = None
    lifecycle_score: float = 0.0
    lifecycle_label: str = ""
    lifecycle_note: str = ""
    textbook_similarity: float
    geometry_fit: float
    leg_balance_fit: float = 0.5
    reversal_energy_fit: float = 0.5
    variant_fit: float = 0.5
    volume_context_fit: float = 0.0
    volatility_context_fit: float = 0.0
    breakout_quality_fit: float = 0.0
    retest_quality_fit: float = 0.0
    candlestick_confirmation_fit: float = 0.5
    candlestick_label: str | None = None
    candlestick_note: str | None = None
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


class ProjectionScenario(BaseModel):
    key: str
    label: str
    weight: float
    bias: str
    summary: str
    path: list[ProjectionPoint]


class ScoreFactor(BaseModel):
    label: str
    score: float
    weight: float
    note: str = ""


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
    avg_mfe_pct: float
    avg_mae_pct: float
    avg_bars_to_outcome: float
    historical_edge_score: float
    trend_alignment_score: float
    trend_direction: str
    trend_warning: str
    wyckoff_phase: str
    wyckoff_score: float
    wyckoff_note: str
    intraday_session_phase: str
    intraday_session_score: float
    intraday_session_note: str
    action_plan: str = "watch"
    action_plan_label: str = "관찰 후보"
    action_plan_summary: str = ""
    action_priority_score: float = 0.0
    risk_flags: list[str] = Field(default_factory=list)
    confirmation_checklist: list[str] = Field(default_factory=list)
    next_trigger: str = ""
    trade_readiness_score: float = 0.0
    trade_readiness_label: str = "보류"
    trade_readiness_summary: str = ""
    entry_window_score: float = 0.0
    entry_window_label: str = "재확인 필요"
    entry_window_summary: str = ""
    freshness_score: float = 0.0
    freshness_label: str = "재확인 필요"
    freshness_summary: str = ""
    reentry_score: float = 0.0
    reentry_label: str = "재확인 필요"
    reentry_summary: str = ""
    reentry_case: str = "none"
    reentry_case_label: str = "구조 없음"
    reentry_profile_key: str = "none"
    reentry_profile_label: str = "평가 보류"
    reentry_profile_summary: str = ""
    reentry_trigger: str = ""
    reentry_compression_score: float = 0.0
    reentry_volume_recovery_score: float = 0.0
    reentry_trigger_hold_score: float = 0.0
    reentry_wick_absorption_score: float = 0.0
    reentry_failure_burden_score: float = 0.0
    reentry_factors: list[ScoreFactor] = Field(default_factory=list)
    score_factors: list[ScoreFactor] = Field(default_factory=list)
    active_setup_score: float = 0.0
    active_setup_label: str = "활성 셋업 없음"
    active_setup_summary: str = ""
    active_pattern_count: int = 0
    completed_pattern_count: int = 0
    no_signal_flag: bool
    no_signal_reason: str
    reason_summary: str
    sample_size: int
    empirical_win_rate: float
    sample_reliability: float
    patterns: list[PatternInfo]
    projection_label: str
    projection_summary: str
    projection_caution: str = ""
    projected_path: list[ProjectionPoint]
    projection_scenarios: list[ProjectionScenario] = Field(default_factory=list)
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
    setup_stage: str = "neutral"
    p_up: float
    p_down: float
    textbook_similarity: float
    formation_quality: float = 0.0
    leg_balance_fit: float = 0.0
    reversal_energy_fit: float = 0.0
    breakout_quality_fit: float = 0.0
    retest_quality_fit: float = 0.0
    confidence: float
    entry_score: float
    reward_risk_ratio: float = 0.0
    headroom_score: float = 0.0
    target_distance_pct: float = 0.0
    stop_distance_pct: float = 0.0
    avg_mfe_pct: float = 0.0
    avg_mae_pct: float = 0.0
    avg_bars_to_outcome: float = 0.0
    historical_edge_score: float = 0.0
    trend_alignment_score: float = 0.0
    trend_direction: str = "sideways"
    trend_warning: str = ""
    wyckoff_phase: str = "neutral"
    wyckoff_score: float = 0.0
    wyckoff_note: str = ""
    intraday_session_phase: str = "neutral"
    intraday_session_score: float = 0.0
    intraday_session_note: str = ""
    action_plan: str = "watch"
    action_plan_label: str = "관찰 후보"
    action_plan_summary: str = ""
    action_priority_score: float = 0.0
    risk_flags: list[str] = Field(default_factory=list)
    confirmation_checklist: list[str] = Field(default_factory=list)
    next_trigger: str = ""
    trade_readiness_score: float = 0.0
    trade_readiness_label: str = "보류"
    trade_readiness_summary: str = ""
    entry_window_score: float = 0.0
    entry_window_label: str = "재확인 필요"
    entry_window_summary: str = ""
    freshness_score: float = 0.0
    freshness_label: str = "재확인 필요"
    freshness_summary: str = ""
    reentry_score: float = 0.0
    reentry_label: str = "재확인 필요"
    reentry_summary: str = ""
    reentry_case: str = "none"
    reentry_case_label: str = "구조 없음"
    reentry_profile_key: str = "none"
    reentry_profile_label: str = "평가 보류"
    reentry_profile_summary: str = ""
    reentry_trigger: str = ""
    reentry_compression_score: float = 0.0
    reentry_volume_recovery_score: float = 0.0
    reentry_trigger_hold_score: float = 0.0
    reentry_wick_absorption_score: float = 0.0
    reentry_failure_burden_score: float = 0.0
    reentry_factors: list[ScoreFactor] = Field(default_factory=list)
    score_factors: list[ScoreFactor] = Field(default_factory=list)
    active_setup_score: float = 0.0
    active_setup_label: str = "활성 셋업 없음"
    active_setup_summary: str = ""
    active_pattern_count: int = 0
    completed_pattern_count: int = 0
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
    live_intraday_candidate: bool = False
    live_intraday_priority_score: float = 0.0
    live_intraday_reason: str = ""
    non_live_intraday_reason: str = ""
    intraday_collection_mode: str = "budget"


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
    intraday_live_candidate_limit: int | None = None
    intraday_live_candidate_count: int | None = None
    intraday_live_phase: str | None = None
    cached_result_count: int = 0
    universe_size: int | None = None
    last_started_at: str | None = None
    last_finished_at: str | None = None
    last_error: str | None = None
    duration_ms: int | None = None
    trigger_accepted: bool | None = None


class KisRuntimeStatus(BaseModel):
    configured: bool
    environment: str
    token_cached: bool
    token_expires_at: str | None = None
    token_expires_in_seconds: int | None = None
    resolved_base_url: str | None = None
    token_cache_path: str
    max_concurrent_requests: int
    request_spacing_ms: int
    guidance: list[str] = Field(default_factory=list)


class CacheRuntimeStatus(BaseModel):
    backend: str
    redis_available: bool
    memory_fallback_entries: int


class IntradayStoreTimeframeStatus(BaseModel):
    timeframe: str
    rows: int
    symbols: int
    latest_fetched_at: str | None = None


class IntradayStoreStatus(BaseModel):
    path: str
    retention_days: int
    total_rows: int
    symbol_count: int
    latest_fetched_at: str | None = None
    timeframes: list[IntradayStoreTimeframeStatus] = Field(default_factory=list)


class ScheduledWarmupPlan(BaseModel):
    id: str
    label: str
    source_timeframe: str
    limit: int
    timeframes: list[str]
    allow_live: bool
    schedule: str


class RuntimeStatusResponse(BaseModel):
    generated_at: str
    app_name: str
    debug: bool
    kis: KisRuntimeStatus
    cache: CacheRuntimeStatus
    intraday_store: IntradayStoreStatus
    scheduler_enabled: bool
    scheduled_warmups: list[ScheduledWarmupPlan] = Field(default_factory=list)
    data_notes: list[str] = Field(default_factory=list)


class IntradayWarmupRequest(BaseModel):
    symbols: list[str]
    timeframes: list[str] = Field(default_factory=lambda: ["15m", "30m", "60m"])
    allow_live: bool = False
    lookback_days: int | None = None


class IntradayWarmupResult(BaseModel):
    symbol: str
    timeframe: str
    ok: bool
    bars: int = 0
    data_source: str = "unknown"
    fetch_status: str = "unknown"
    message: str = ""


class IntradayWarmupResponse(BaseModel):
    requested_at: str
    allow_live: bool
    symbols: list[str]
    timeframes: list[str]
    total_requests: int
    success_count: int
    failure_count: int
    results: list[IntradayWarmupResult]


class IntradayWarmupJobStatus(BaseModel):
    status: str = "idle"
    is_running: bool = False
    source: str | None = None
    allow_live: bool = False
    started_at: str | None = None
    finished_at: str | None = None
    total_requests: int = 0
    completed_count: int = 0
    success_count: int = 0
    failure_count: int = 0
    symbols: list[str] = Field(default_factory=list)
    timeframes: list[str] = Field(default_factory=list)
    last_error: str | None = None
    trigger_accepted: bool | None = None
    results: list[IntradayWarmupResult] = Field(default_factory=list)


class IntradayCandidateWarmupRequest(BaseModel):
    source_timeframe: str = "1d"
    limit: int = Field(default=20, ge=1, le=50)
    timeframes: list[str] = Field(default_factory=lambda: ["15m", "30m", "60m"])
    allow_live: bool = False
    include_watch: bool = True
    lookback_days: int | None = None


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


class PatternStatsEntry(BaseModel):
    pattern_type: str
    timeframe: str
    timeframe_label: str
    win_rate: float
    sample_size: int
    wins: int
    total: int
    avg_mfe_pct: float
    avg_mae_pct: float
    avg_bars_to_outcome: float
    historical_edge_score: float


class PatternStatsResponse(BaseModel):
    generated_at: str
    items: list[PatternStatsEntry]


class ScreenerRequest(BaseModel):
    pattern_types: list[str] | None = None
    states: list[str] | None = None
    markets: list[str] | None = None
    fetch_statuses: list[str] | None = None
    reentry_cases: list[str] | None = None
    min_textbook_similarity: float = 0.0
    min_p_up: float = 0.0
    max_p_down: float = 1.0
    min_confidence: float = 0.0
    min_sample_reliability: float = 0.0
    min_data_quality: float = 0.0
    min_trade_readiness_score: float = 0.0
    min_entry_window_score: float = 0.0
    min_freshness_score: float = 0.0
    min_reentry_score: float = 0.0
    min_reentry_compression_score: float = 0.0
    min_reentry_volume_recovery_score: float = 0.0
    min_reentry_trigger_hold_score: float = 0.0
    min_reentry_wick_absorption_score: float = 0.0
    min_reentry_failure_burden_score: float = 0.0
    min_active_setup_score: float = 0.0
    min_confluence_score: float = 0.0
    min_historical_edge_score: float = 0.0
    timeframes: list[str] | None = None
    min_market_cap: float | None = None
    exclude_no_signal: bool = True
    sort_by: str = "composite_score"
    limit: int = Field(default=50, ge=1, le=100)
