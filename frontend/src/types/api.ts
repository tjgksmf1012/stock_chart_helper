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
  textbook_similarity: number
  geometry_fit: number
  leg_balance_fit: number
  reversal_energy_fit: number
  volume_context_fit: number
  volatility_context_fit: number
  breakout_quality_fit: number
  retest_quality_fit: number
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
  no_signal_flag: boolean
  no_signal_reason: string
  reason_summary: string
  sample_size: number
  empirical_win_rate: number
  sample_reliability: number
  patterns: PatternInfo[]
  projection_label: string
  projection_summary: string
  projected_path: ProjectionPoint[]
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
}

export interface DashboardResponse {
  category: string
  timeframe: Timeframe
  timeframe_label: string
  items: DashboardItem[]
  generated_at: string
}

export interface ScanStatusResponse {
  timeframe: Timeframe
  timeframe_label: string
  status: string
  is_running: boolean
  source: string | null
  candidate_source: string | null
  candidate_count: number | null
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

export interface ScreenerRequest {
  pattern_types?: string[]
  states?: string[]
  markets?: string[]
  fetch_statuses?: string[]
  min_textbook_similarity?: number
  min_p_up?: number
  max_p_down?: number
  min_confidence?: number
  min_sample_reliability?: number
  min_data_quality?: number
  min_confluence_score?: number
  min_historical_edge_score?: number
  timeframes?: Timeframe[]
  min_market_cap?: number
  exclude_no_signal?: boolean
  sort_by?: 'composite_score' | 'entry_score' | 'p_up' | 'textbook_similarity' | 'confidence' | 'p_down' | 'sample_reliability' | 'confluence_score' | 'data_quality' | 'historical_edge_score'
  limit?: number
}
