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
  source: 'kis' | 'toss' | 'pykrx' | 'none'
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

export interface IchimokuSummary {
  score: number
  bias: 'bullish' | 'bearish' | 'neutral' | string
  cloud_position: string
  cloud_thickness_level: string
  cloud_thickness_pct: number
  cloud_distance_pct: number
  prior_high_structure: string
  summary: string
  signals: string[]
  caution: string
}

export interface ReferenceCaseItem {
  key: string
  symbol_code: string
  symbol_name: string
  timeframe: Timeframe
  timeframe_label: string
  pattern_type: string
  state: string
  signal_date: string
  resolution_date: string | null
  similarity_score: number
  match_grade: string
  cloud_position: string
  cloud_thickness_level: string
  prior_high_structure: string
  ichimoku_summary: string
  setup_summary: string
  outcome_label: string
  outcome_summary: string
  outcome_return_pct: number
  max_favorable_pct: number
  max_adverse_pct: number
  bars_to_resolution: number | null
  matched_features: string[]
  sparkline: number[]
  chart_path: string
}

export interface ReferenceCaseResponse {
  generated_at: string
  symbol_code: string
  symbol_name: string
  timeframe: Timeframe
  timeframe_label: string
  pattern_type: string
  state: string
  ichimoku: IchimokuSummary
  sample_count: number
  success_rate: number
  partial_success_rate: number
  avg_similarity_score: number
  avg_outcome_return_pct: number
  items: ReferenceCaseItem[]
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
  ichimoku: IchimokuSummary
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
  money_flow?: MoneyFlowData | null
}

// ─── Market Intelligence ──────────────────────────────────────────────────────

export interface MoneyFlowDailyEntry {
  date: string
  foreign: number   // 억원 (양수=순매수)
  institution: number
}

export interface MoneyFlowData {
  foreign_net_3d: number
  foreign_net_10d: number
  institution_net_3d: number
  institution_net_10d: number
  alignment: 'aligned' | 'diverged' | 'mixed' | 'neutral'
  alignment_label: string
  alignment_note: string
  daily: MoneyFlowDailyEntry[]
}

export interface IndexRegime {
  regime: 'bull' | 'correction' | 'bear' | 'sideways' | 'unknown'
  current: number
  change_pct: number
  ma20: number | null
  ma60: number | null
  ma120: number | null
  distance_from_ma120_pct: number
}

export interface MarketRegimeResponse {
  kospi: IndexRegime
  kosdaq: IndexRegime
  overall_regime: 'bull' | 'correction' | 'bear' | 'sideways' | 'unknown'
  generated_at: string
}

export interface SectorEntry {
  sector_name: string
  bullish_count: number
  bearish_count: number
  net_score: number
  top_symbols: string[]
}

export interface SectorHeatmapResponse {
  sectors: SectorEntry[]
  code_to_sector: Record<string, string>
  generated_at: string
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
  watchlist_priority?: boolean
  summary: string
  action_line: string
  do_now?: string
  avoid_if?: string
  review_price?: string
  skip_reason?: string
  overlap_risk?: string
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
  personal_fit_score?: number
  personal_fit_label?: string
  personal_fit_reasons?: string[]
}

export interface PersonalStyleProfile {
  style_key: string
  style_label: string
  summary: string
  confidence: number
  sample_count: number
  primary_intent: string
  primary_intent_label: string
  secondary_intent?: string | null
  secondary_intent_label?: string | null
  best_pattern?: string | null
  best_pattern_win_rate?: number
  best_timeframe?: string | null
  best_timeframe_label?: string | null
  best_timeframe_win_rate?: number
  focus_points: string[]
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
  watchlist_focus_items?: AiRecommendationItem[]
  personalized_items?: AiRecommendationItem[]
  priority_total?: number
  watch_total?: number
  risk_total?: number
  personal_style?: PersonalStyleProfile
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
  cancel_requested?: boolean
  source: string | null
  candidate_source: string | null
  candidate_count: number | null
  intraday_live_candidate_limit: number | null
  intraday_live_candidate_count: number | null
  intraday_live_phase: string | null
  cached_result_count: number
  universe_size: number | null
  scanned_count?: number | null
  last_started_at: string | null
  last_finished_at: string | null
  last_error: string | null
  duration_ms: number | null
  trigger_accepted?: boolean | null
  data_source_degraded?: boolean
  data_source_note?: string | null
}

export interface DeepAnalysisProgress {
  running: boolean
  done: number
  total: number
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
  timeouts?: number
  resolution_rate?: number | null
  is_synthetic?: boolean
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

export interface TossRuntimeStatus {
  configured: boolean
  token_cached: boolean
  base_url: string
  live_intraday_provider_order: string
  guidance: string[]
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

export interface ScheduledDailyScanPlan {
  id: string
  label: string
  timeframe: Timeframe | string
  schedule: string
  purpose: string
}

export interface StorageRoleStatus {
  name: string
  backend: string
  role: string
  persistence: string
  examples: string[]
}

export interface RuntimeStatusResponse {
  generated_at: string
  app_name: string
  debug: boolean
  kis: KisRuntimeStatus
  toss: TossRuntimeStatus
  cache: CacheRuntimeStatus
  intraday_store: IntradayStoreStatus
  scheduler_enabled: boolean
  scheduled_daily_scans: ScheduledDailyScanPlan[]
  scheduled_warmups: ScheduledWarmupPlan[]
  storage_roles: StorageRoleStatus[]
  data_notes: string[]
}

export interface ScanHistoryRunSummary {
  id: number
  timeframe: Timeframe | string
  timeframe_label: string
  source: string | null
  status: string
  candidate_source: string | null
  reference_date: string | null
  reference_reason: string | null
  universe_size: number | null
  candidate_count: number | null
  result_count: number
  duration_ms: number | null
  started_at: string | null
  finished_at: string | null
  last_error: string | null
}

export interface ScanQualitySummary {
  avg_close_return_pct: number
  avg_max_runup_pct: number
  avg_max_drawdown_pct: number
  positive_close_rate: number
  hit_3pct_rate: number
  hit_5pct_rate: number
  target_touch_rate: number
  stop_touch_rate: number
}

export interface ScanQualityBucket extends ScanQualitySummary {
  bucket: string
  sample_count: number
}

export interface ScanQualityActionPlan extends ScanQualitySummary {
  action_plan: string
  sample_count: number
}

export interface ScanQualityGroup extends ScanQualitySummary {
  group: string
  sample_count: number
}

export interface ScanQualityFalsePositive {
  symbol_code: string
  symbol_name: string
  signal_date: string
  pattern_type: string | null
  state: string | null
  timeframe: Timeframe | string
  composite_score: number
  p_up: number
  close_return_pct: number
  max_runup_pct: number
  max_drawdown_pct: number
  reason: string
}

export interface ScanQualityReportResponse {
  generated_at: string
  timeframe: Timeframe | string
  lookback_days: number
  forward_bars: number
  run_count: number
  evaluated_count: number
  latest_reference_date: string | null
  summary: ScanQualitySummary
  score_buckets: ScanQualityBucket[]
  action_plans: ScanQualityActionPlan[]
  pattern_groups: ScanQualityGroup[]
  state_groups: ScanQualityGroup[]
  timeframe_groups: ScanQualityGroup[]
  false_positive_signals: ScanQualityFalsePositive[]
  notes: string[]
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
export type OutcomeIntent = 'observe' | 'breakout_wait' | 'pullback_candidate' | 'invalidation_watch'

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
  intent?: OutcomeIntent | null
  outcome: OutcomeStatus
  exit_price?: number | null
  exit_date?: string | null
  notes?: string | null
  p_up_at_signal?: number | null
  composite_score_at_signal?: number | null
  textbook_similarity_at_signal?: number | null
  trade_readiness_at_signal?: number | null
  evaluation_basis?: string | null
  observed_high?: number | null
  observed_low?: number | null
  recorded_at?: string
  updated_at?: string
}

export interface OutcomesSummary {
  total_records: number
  completed: number
  wins: number
  win_rate: number
  avg_hold_days?: number
  pending: number
  cancelled: number
  by_pattern: Record<string, { wins: number; total: number; win_rate: number }>
  by_intent?: Record<string, { wins: number; total: number; win_rate: number }>
  by_timeframe?: Record<string, { wins: number; total: number; win_rate: number }>
  style_profile?: PersonalStyleProfile
}

export interface CalibrationBin {
  lower: number
  upper: number
  count: number
  predicted: number
  observed: number
  gap: number
  low_confidence?: boolean
}

export interface CalibrationReport {
  timeframe: string | null
  evaluated_total: number
  scored_total: number
  sample_size: number
  resolved_wins: number
  base_rate: number
  mean_predicted: number
  brier_score: number
  ece: number
  mean_gap: number
  reliability: string
  bins: CalibrationBin[]
}

export interface OfflineCalibrationResponse extends Partial<CalibrationReport> {
  timeframe: string
  status: 'ready' | 'building'
  generated_at?: string
  simulated?: { symbols: number; windows: number; signals: number; unresolved: number }
}

export interface OutcomeEvaluationItem {
  id: number
  symbol_code: string
  symbol_name: string
  outcome: OutcomeStatus
  close: number
  high?: number | null
  low?: number | null
  evaluation_basis?: string
  target_price?: number | null
  stop_price?: number | null
  reason: string
}

export interface OutcomeEvaluationResponse {
  status: string
  checked: number
  updated: number
  skipped: number
  items: OutcomeEvaluationItem[]
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

// 정밀분석 (온디맨드 심층 분석)
export interface DeepPatternCase {
  pattern_type: string
  signal_date: string
  outcome: 'success' | 'fail' | 'timeout'
  bars_to_outcome: number | null
  /** 부호 있는 가격 변화 (숏 패턴 성공이면 음수) — 표시용으로는 pnl_pct를 쓸 것 */
  move_pct: number
  /** 패턴 방향 반영 손익 (숏 성공 = +). 구버전 캐시 응답엔 없을 수 있음 */
  pnl_pct?: number
  direction?: 'long' | 'short'
  mfe_pct: number
  mae_pct: number
}

export interface DeepPatternStat {
  pattern_type: string
  total: number
  wins: number
  losses: number
  timeouts: number
  win_rate: number | null
  avg_bars_to_outcome: number | null
  avg_win_move_pct: number | null
  avg_loss_move_pct: number | null
}

export interface DeepLongContext {
  week52_high?: number
  week52_low?: number
  week52_position?: number
  volatility_recent_pct?: number
  volatility_year_pct?: number
  volatility_regime?: string
}

export interface DeepAnalysisResponse {
  symbol_code: string
  generated_at: string
  available_bars: number
  case_count?: number
  cases: DeepPatternCase[]
  stats: DeepPatternStat[]
  long_context: DeepLongContext
  note: string
}

// 실험실 (전략 검증 리포트 — scripts/run_lab.py 산출물)
export interface LabReport {
  strategy: string
  label: string
  period: { start: string; end: string }
  config: { top_n: number; train_years: number; test_months: number; round_trip_cost_pct: number }
  universe_mode: 'marcap' | 'pit' | 'current'
  universe_note: string | null
  data_coverage: number
  n_trades: number
  ev_pct: number
  ci_95: [number, number]
  win_rate: number
  payoff_ratio: number
  sequential_mdd_pct?: number
  portfolio_mdd_pct?: number
  portfolio_total_return_pct?: number
  /** 고정 리스크(트레이드당 1%) 규율 운용 시 자본곡선 — 실제 운용 규율에 가장 가까운 MDD */
  risk_1pct?: { n_used: number; total_return_pct: number; mdd_pct: number; avg_r: number; risk_pct: number }
  random_benchmark_ev_pct: number | null
  verdict: 'pass' | 'watch' | 'fail'
  generated_at: string
}

export interface LabReportsResponse {
  reports: LabReport[]
}

export interface LabSignal {
  strategy_id: string
  strategy_label: string
  code: string
  signal_date: string
  /** 신호일 종가 — 다음날 시가 진입의 근사치, 포지션 사이징 기준가 */
  reference_price?: number | null
  stop_price: number
  target_price: number | null
  max_holding_days: number
  verdict: 'pass' | 'watch' | 'fail' | null
}

export interface LabEligibleStrategy {
  strategy_id: string
  label: string
  verdict: 'pass' | 'watch' | 'fail' | null
}

export interface LabSignalsResponse {
  status?: 'ready' | 'computing'
  generated_at: string | null
  eligible_strategies: LabEligibleStrategy[]
  universe_size?: number
  signals: LabSignal[]
  recorded_paper_trades?: number
  note: string | null
}

export interface LabPaperTradeSummaryItem {
  strategy_id: string
  label: string
  realized_n: number
  realized_ev_pct: number | null
  realized_win_rate: number | null
  open_count: number
  backtest_ci_low: number | null
  drift: 'ok' | 'drifting' | 'insufficient' | 'unknown'
}

export interface LabPaperTradesSummaryResponse {
  strategies: LabPaperTradeSummaryItem[]
}

// 확률적 전망 — 점 예측이 아니라 구간 + 실측 적중률
export interface OutlookHorizon {
  horizon_days: number
  label: string
  q10: number
  q25: number
  q50: number
  q75: number
  q90: number
  coverage: { coverage: number; hits: number; n: number; nominal: number } | null
}

export interface OutlookConditionalSignal {
  strategy_id: string
  strategy_label: string
  signal_date: string
  holding_days: number
  ev_pct: number
  ci_95: [number, number]
  verdict: 'pass' | 'watch' | 'fail'
}

export interface SymbolOutlookResponse {
  symbol_code: string
  generated_at: string
  horizons: OutlookHorizon[]
  conditional_signal: OutlookConditionalSignal | null
  note: string
}
