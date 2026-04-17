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
  neckline: number | null
  invalidation_level: number | null
  target_level: number | null
  key_points: Array<{ dt?: string; price: number; type: string }>
  is_provisional: boolean
  start_dt: string
  end_dt: string | null
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
  no_signal_flag: boolean
  no_signal_reason: string
  reason_summary: string
  sample_size: number
  patterns: PatternInfo[]
  is_provisional: boolean
  updated_at: string
  data_source: string
  data_quality: number
  source_note: string
  fetch_status: string
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
  p_up: number
  p_down: number
  textbook_similarity: number
  confidence: number
  entry_score: number
  no_signal_flag: boolean
  reason_summary: string
  completion_proximity: number
  recency_score: number
  data_source: string
  data_quality: number
  source_note: string
  fetch_status: string
  fetch_message: string
  liquidity_score: number
  avg_turnover_billion: number
  sample_size: number
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

export interface ScreenerRequest {
  pattern_types?: string[]
  states?: string[]
  markets?: string[]
  min_textbook_similarity?: number
  min_p_up?: number
  max_p_down?: number
  min_confidence?: number
  timeframes?: Timeframe[]
  min_market_cap?: number
  exclude_no_signal?: boolean
  sort_by?: 'entry_score' | 'p_up' | 'textbook_similarity' | 'confidence' | 'p_down'
  limit?: number
}
