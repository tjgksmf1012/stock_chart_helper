export type Timeframe = '1mo' | '1wk' | '1d' | '60m' | '30m' | '15m' | '1m'

export interface SymbolInfo {
  code: string
  name: string
  market: string
  sector: string | null
  market_cap: number | null
  is_in_universe: boolean
}

export interface PriceInfo {
  code: string
  close: number
  prev_close: number
  change: number
  change_pct: number
  volume: number
  source: 'kis' | 'pykrx' | 'none'
  timestamp: string | null
}

export interface OHLCVBar {
  date: string
  open: number
  high: number
  low: number
  close: number
  volume: number
  amount: number | null
}

export interface PatternInfo {
  pattern_type: string
  state: 'forming' | 'armed' | 'confirmed' | 'invalidated' | 'played_out'
  grade: 'A' | 'B' | 'C'
  variant?: string | null
  lifecycle_score: number
  lifecycle_label: string
  lifecycle_note: string
  textbook_similarity: number
  geometry_fit: number
  leg_balance_fit: number
  reversal_energy_fit: number
  variant_fit: number
  volume_context_fit: number
  volatility_context_fit: number
  breakout_quality_fit: number
  retest_quality_fit: number
  candlestick_confirmation_fit: number
  candlestick_label?: string | null
  candlestick_note?: string | null
  neckline: number | null
  invalidation_level: number | null
  target_level: number | null
  key_points: Array<{ dt?: string; price: number; type: string }>
  is_provisional: boolean
  start_dt: string
  end_dt: string | null
  target_hit_at?: string | null
  invalidated_at?: string | null
}

export interface ProjectionPoint {
  dt: string
  price: number
  kind: string
}

export interface ProjectionScenario {
  key: string
  label: string
  weight: number
  bias: 'bullish' | 'bearish' | 'neutral'
  summary: string
  path: ProjectionPoint[]
}

export interface ScoreFactor {
  label: string
  score: number
  weight: number
  note: string
}

export interface AnalysisResult {
  symbol: SymbolInfo
  timeframe: Timeframe
  timeframe_label: string
  p_up: number
  p_down: number
  textbook_similarity: number
  pattern_confirmation_score: number
  confidence: number
  entry_score: number
  completion_proximity: number
  recency_score: number
  reward_risk_ratio: number
  headroom_score: number
  target_distance_pct: number
  stop_distance_pct: number
  avg_mfe_pct: number
  avg_mae_pct: number
  avg_bars_to_outcome: number
  historical_edge_score: number
  trend_alignment_score: number
  trend_direction: string
  trend_warning: string
  wyckoff_phase: string
  wyckoff_score: number
  wyckoff_note: string
  intraday_session_phase: string
  intraday_session_score: number
  intraday_session_note: string
  action_plan: string
  action_plan_label: string
  action_plan_summary: string
  action_priority_score: number
  risk_flags: string[]
  confirmation_checklist: string[]
  next_trigger: string
  trade_readiness_score: number
  trade_readiness_label: string
  trade_readiness_summary: string
  entry_window_score: number
  entry_window_label: string
  entry_window_summary: string
  freshness_score: number
  freshness_label: string
  freshness_summary: string
  reentry_score: number
  reentry_label: string
  reentry_summary: string
  reentry_case: string
  reentry_case_label: string
  reentry_profile_key: string
  reentry_profile_label: string
  reentry_profile_summary: string
  reentry_trigger: string
  reentry_compression_score: number
  reentry_volume_recovery_score: number
  reentry_trigger_hold_score: number
  reentry_wick_absorption_score: number
  reentry_failure_burden_score: number
  reentry_factors: ScoreFactor[]
  score_factors: ScoreFactor[]
  active_setup_score: number
  active_setup_label: string
  active_setup_summary: string
  active_pattern_count: number
  completed_pattern_count: number
  no_signal_flag: boolean
  no_signal_reason: string
  reason_summary: string
  sample_size: number
  empirical_win_rate: number
  sample_reliability: number
  patterns: PatternInfo[]
  projection_label: string
  projection_summary: string
  projection_caution: string
  projected_path: ProjectionPoint[]
  projection_scenarios: ProjectionScenario[]
  is_provisional: boolean
  updated_at: string
  data_source: string
  data_quality: number
  source_note: string
  fetch_status: string
  fetch_status_label: string
  fetch_message: string
  liquidity_score: number
  avg_turnover_billion: number
  bars_since_signal: number | null
  stats_timeframe: string
  available_bars: number
}

export interface DashboardItem {
  rank: number
  symbol: SymbolInfo
  timeframe: Timeframe
  timeframe_label: string
  pattern_type: string | null
  state: string | null
  setup_stage: string
  p_up: number
  p_down: number
  textbook_similarity: number
  formation_quality: number
  leg_balance_fit: number
  reversal_energy_fit: number
  breakout_quality_fit: number
  retest_quality_fit: number
  confidence: number
  entry_score: number
  reward_risk_ratio: number
  headroom_score: number
  target_distance_pct: number
  stop_distance_pct: number
  avg_mfe_pct: number
  avg_mae_pct: number
  avg_bars_to_outcome: number
  historical_edge_score: number
  trend_alignment_score: number
  trend_direction: string
  trend_warning: string
  wyckoff_phase: string
  wyckoff_score: number
  wyckoff_note: string
  intraday_session_phase: string
  intraday_session_score: number
  intraday_session_note: string
  action_plan: string
  action_plan_label: string
  action_plan_summary: string
  action_priority_score: number
  risk_flags: string[]
  confirmation_checklist: string[]
  next_trigger: string
  trade_readiness_score: number
  trade_readiness_label: string
  trade_readiness_summary: string
  entry_window_score: number
  entry_window_label: string
  entry_window_summary: string
  freshness_score: number
  freshness_label: string
  freshness_summary: string
  reentry_score: number
  reentry_label: string
  reentry_summary: string
  reentry_case: string
  reentry_case_label: string
  reentry_profile_key: string
  reentry_profile_label: string
  reentry_profile_summary: string
  reentry_trigger: string
  reentry_compression_score: number
  reentry_volume_recovery_score: number
  reentry_trigger_hold_score: number
  reentry_wick_absorption_score: number
  reentry_failure_burden_score: number
  reentry_factors: ScoreFactor[]
  score_factors: ScoreFactor[]
  active_setup_score: number
  active_setup_label: string
  active_setup_summary: string
  active_pattern_count: number
  completed_pattern_count: number
  no_signal_flag: boolean
  reason_summary: string
  completion_proximity: number
  recency_score: number
  data_source: string
  data_quality: number
  source_note: string
  fetch_status: string
  fetch_status_label: string
  fetch_message: string
  liquidity_score: number
  avg_turnover_billion: number
  sample_size: number
  empirical_win_rate: number
  sample_reliability: number
  stats_timeframe: string
  available_bars: number
  confluence_score: number
  confluence_summary: string
  scenario_text: string
  live_intraday_candidate: boolean
  live_intraday_priority_score: number
  live_intraday_reason: string
  non_live_intraday_reason: string
  intraday_collection_mode: string
}

export interface DashboardResponse {
  category: string
  timeframe: Timeframe
  timeframe_label: string
  items: DashboardItem[]
  generated_at: string
}

export interface DashboardOverviewResponse {
  timeframe: Timeframe
  timeframe_label: string
  generated_at: string
  long_high_probability: DashboardResponse
  pattern_armed: DashboardResponse
  live_intraday_candidates: DashboardResponse
  forming_candidates: DashboardResponse
  high_textbook_similarity: DashboardResponse
  short_high_probability: DashboardResponse
  watchlist_no_signal: DashboardResponse
}

export interface AiRecommendationItem {
  rank: number
  symbol: SymbolInfo
  timeframe: Timeframe
  timeframe_label: string
  stance: 'priority_watch' | 'wait_for_trigger' | 'avoid_chase' | 'risk_review'
  stance_label: string
  score: number
  confidence: number
  source_category: string
  summary: string
  action_line: string
  reasons: string[]
  risk_flags: string[]
  next_actions: string[]
  position_hint: string
  pattern_type: string | null
  state: string | null
  p_up: number
  p_down: number
  trade_readiness_score: number
  entry_window_score: number
  freshness_score: number
  reward_risk_ratio: number
  data_quality: number
  confluence_score: number
  next_trigger: string
  chart_path: string
}

export interface AiRecommendationResponse {
  generated_at: string
  timeframe: Timeframe
  timeframe_label: string
  market_brief: string
  portfolio_guidance: string
  items: AiRecommendationItem[]
  priority_items: AiRecommendationItem[]
  watch_items: AiRecommendationItem[]
  risk_items: AiRecommendationItem[]
  disclaimer: string
  llm_enabled?: boolean
  llm_model?: string | null
  llm_error?: string | null
  llm_status?: string
  llm_cached_at?: string | null
  llm_refreshing?: boolean
  llm_source?: string
}

export interface ScanStatusResponse {
  timeframe: Timeframe
  timeframe_label: string
  status: string
  is_running: boolean
  source: string | null
  candidate_source: string | null
  candidate_count: number | null
  intraday_live_candidate_limit: number | null
  intraday_live_candidate_count: number | null
  intraday_live_phase: string | null
  cached_result_count: number
  universe_size: number | null
  last_started_at: string | null
  last_finished_at: string | null
  last_error: string | null
  duration_ms: number | null
  trigger_accepted?: boolean | null
}

export interface PatternLibraryEntry {
  pattern_type: string
  name_kr: string
  grade: string
  direction: 'bullish' | 'bearish' | 'neutral'
  description: string
  structure_conditions: string[]
  volume_conditions: string[]
  confirmation_conditions: string[]
  invalidation_conditions: string[]
  cautions: string[]
  svg_path: string | null
}

export interface PatternStatsEntry {
  pattern_type: string
  timeframe: '1mo' | '1wk' | '1d'
  timeframe_label: string
  win_rate: number
  sample_size: number
  wins: number
  total: number
  avg_mfe_pct: number
  avg_mae_pct: number
  avg_bars_to_outcome: number
  historical_edge_score: number
}

export interface PatternStatsResponse {
  generated_at: string
  items: PatternStatsEntry[]
}

export interface KisRuntimeStatus {
  configured: boolean
  environment: string
  token_cached: boolean
  token_expires_at: string | null
  token_expires_in_seconds: number | null
  resolved_base_url: string | null
  token_cache_path: string
  max_concurrent_requests: number
  request_spacing_ms: number
  guidance: string[]
  last_prime?: KisPrimeStatus | null
}

export interface CacheRuntimeStatus {
  backend: string
  redis_available: boolean
  memory_fallback_entries: number
}

export interface IntradayStoreTimeframeStatus {
  timeframe: string
  rows: number
  symbols: number
  latest_fetched_at: string | null
}

export interface IntradayStoreStatus {
  path: string
  retention_days: number
  total_rows: number
  symbol_count: number
  latest_fetched_at: string | null
  timeframes: IntradayStoreTimeframeStatus[]
}

export interface ScheduledWarmupPlan {
  id: string
  label: string
  source_timeframe: Timeframe | string
  limit: number
  timeframes: string[]
  allow_live: boolean
  schedule: string
}

export interface RuntimeStatusResponse {
  generated_at: string
  app_name: string
  debug: boolean
  kis: KisRuntimeStatus
  cache: CacheRuntimeStatus
  intraday_store: IntradayStoreStatus
  scheduler_enabled: boolean
  scheduled_warmups: ScheduledWarmupPlan[]
  data_notes: string[]
}

export interface KisPrimeStatus {
  status: string
  is_running: boolean
  requested_at: string | null
  finished_at: string | null
  triggered_by: string | null
  symbol: string | null
  timeframe: string | null
  ok: boolean | null
  token_cached_before: boolean
  token_cached_after: boolean
  token_expires_at: string | null
  token_expires_in_seconds: number | null
  resolved_base_url: string | null
  store_rows_before: number
  store_rows_after: number
  store_rows_added: number
  bars_returned: number
  data_source: string | null
  fetch_status: string | null
  message: string | null
  last_error: string | null
}

export interface IntradayWarmupRequest {
  symbols: string[]
  timeframes: string[]
  allow_live: boolean
  lookback_days?: number | null
}

export interface IntradayCandidateWarmupRequest {
  source_timeframe: Timeframe
  limit: number
  timeframes: string[]
  allow_live: boolean
  include_watch?: boolean
  lookback_days?: number | null
}

export interface IntradayWarmupResult {
  symbol: string
  timeframe: string
  ok: boolean
  bars: number
  data_source: string
  fetch_status: string
  message: string
}

export interface IntradayWarmupResponse {
  requested_at: string
  allow_live: boolean
  symbols: string[]
  timeframes: string[]
  total_requests: number
  success_count: number
  failure_count: number
  results: IntradayWarmupResult[]
}

export interface IntradayWarmupJobStatus {
  status: string
  is_running: boolean
  source: string | null
  allow_live: boolean
  started_at: string | null
  finished_at: string | null
  total_requests: number
  completed_count: number
  success_count: number
  failure_count: number
  symbols: string[]
  timeframes: string[]
  last_error: string | null
  trigger_accepted?: boolean | null
  results: IntradayWarmupResult[]
}

// ─── Watchlist ────────────────────────────────────────────────────────────────

export interface WatchlistItem {
  code: string
  name: string
  market: string
  addedAt?: string | null
}

// ─── Outcome tracking ─────────────────────────────────────────────────────────

export type OutcomeStatus = 'win' | 'loss' | 'stopped_out' | 'pending' | 'cancelled'

export interface OutcomeRecord {
  id?: number
  symbol_code: string
  symbol_name: string
  pattern_type: string
  timeframe: string
  signal_date: string
  entry_price: number
  target_price?: number | null
  stop_price?: number | null
  outcome: OutcomeStatus
  exit_price?: number | null
  exit_date?: string | null
  notes?: string | null
  p_up_at_signal?: number | null
  composite_score_at_signal?: number | null
  textbook_similarity_at_signal?: number | null
  trade_readiness_at_signal?: number | null
  recorded_at?: string
  updated_at?: string
}

export interface OutcomesSummary {
  total_records: number
  completed: number
  wins: number
  win_rate: number
  pending: number
  cancelled: number
  by_pattern: Record<string, { wins: number; total: number; win_rate: number }>
}

// ─── Screener ─────────────────────────────────────────────────────────────────

export interface ScreenerRequest {
  pattern_types?: string[]
  states?: string[]
  markets?: string[]
  fetch_statuses?: string[]
  reentry_cases?: string[]
  min_textbook_similarity?: number
  min_p_up?: number
  max_p_down?: number
  min_confidence?: number
  min_sample_reliability?: number
  min_data_quality?: number
  min_trade_readiness_score?: number
  min_entry_window_score?: number
  min_freshness_score?: number
  min_reentry_score?: number
  min_reentry_compression_score?: number
  min_reentry_volume_recovery_score?: number
  min_reentry_trigger_hold_score?: number
  min_reentry_wick_absorption_score?: number
  min_reentry_failure_burden_score?: number
  min_active_setup_score?: number
  min_confluence_score?: number
  min_historical_edge_score?: number
  timeframes?: Timeframe[]
  min_market_cap?: number
  exclude_no_signal?: boolean
  sort_by?:
    | 'composite_score'
    | 'entry_score'
    | 'p_up'
    | 'textbook_similarity'
    | 'confidence'
    | 'p_down'
    | 'sample_reliability'
  | 'trade_readiness_score'
  | 'entry_window_score'
  | 'freshness_score'
  | 'reentry_score'
  | 'reentry_compression_score'
  | 'reentry_volume_recovery_score'
  | 'reentry_trigger_hold_score'
  | 'reentry_wick_absorption_score'
  | 'reentry_failure_burden_score'
  | 'active_setup_score'
    | 'confluence_score'
    | 'data_quality'
    | 'historical_edge_score'
  limit?: number
}
