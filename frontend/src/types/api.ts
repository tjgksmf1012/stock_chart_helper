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
  timeframe: string
  p_up: number
  p_down: number
  textbook_similarity: number
  pattern_confirmation_score: number
  confidence: number
  entry_score: number
  no_signal_flag: boolean
  no_signal_reason: string
  reason_summary: string
  sample_size: number
  patterns: PatternInfo[]
  is_provisional: boolean
  updated_at: string
}

export interface DashboardItem {
  rank: number
  symbol: SymbolInfo
  pattern_type: string | null
  state: string | null
  p_up: number
  p_down: number
  textbook_similarity: number
  confidence: number
  entry_score: number
  no_signal_flag: boolean
  reason_summary: string
}

export interface DashboardResponse {
  category: string
  items: DashboardItem[]
  generated_at: string
}

export interface ScanStatusResponse {
  status: string
  is_running: boolean
  source: string | null
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
  timeframes?: string[]
  exclude_no_signal?: boolean
  sort_by?: 'entry_score' | 'p_up' | 'textbook_similarity' | 'confidence' | 'p_down'
  limit?: number
}
