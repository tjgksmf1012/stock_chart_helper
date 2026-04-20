import axios from 'axios'
import type {
  SymbolInfo, OHLCVBar, AnalysisResult, PriceInfo,
  DashboardOverviewResponse, DashboardResponse, PatternLibraryEntry, ScreenerRequest, DashboardItem, ScanStatusResponse, Timeframe,
  IntradayCandidateWarmupRequest, IntradayWarmupJobStatus, IntradayWarmupRequest, IntradayWarmupResponse, PatternStatsResponse, RuntimeStatusResponse,
  WatchlistItem, OutcomeRecord, OutcomesSummary, OutcomeStatus,
} from '@/types/api'

// In development the Vite proxy forwards /api → backend (see vite.config.ts).
// In production set VITE_API_BASE_URL to your backend's public URL
// (e.g. https://stock-chart-helper-api.onrender.com) and this will call it directly.
const _base = import.meta.env.VITE_API_BASE_URL
  ? `${String(import.meta.env.VITE_API_BASE_URL).replace(/\/$/, '')}/api/v1`
  : '/api/v1'

const api = axios.create({ baseURL: _base, timeout: 30_000 })

export const symbolsApi = {
  search: (q: string) => api.get<SymbolInfo[]>('/symbols/search', { params: { q } }).then(r => r.data),
  getBars: (symbol: string, timeframe: Timeframe, days: number) =>
    api.get<OHLCVBar[]>(`/symbols/${symbol}/bars`, { params: { timeframe, days } }).then(r => r.data),
  getAnalysis: (symbol: string, timeframe: Timeframe) =>
    api.get<AnalysisResult>(`/symbols/${symbol}/analysis`, { params: { timeframe } }).then(r => r.data),
  getPrice: (symbol: string) =>
    api.get<PriceInfo>(`/symbols/${symbol}/price`).then(r => r.data),
}

export const dashboardApi = {
  overview: (timeframe: Timeframe, limit = 10) => api.get<DashboardOverviewResponse>('/dashboard/overview', { params: { timeframe, limit } }).then(r => r.data),
  longHigh: (timeframe: Timeframe, limit = 10) => api.get<DashboardResponse>('/dashboard/long-high-probability', { params: { timeframe, limit } }).then(r => r.data),
  shortHigh: (timeframe: Timeframe, limit = 10) => api.get<DashboardResponse>('/dashboard/short-high-probability', { params: { timeframe, limit } }).then(r => r.data),
  highSimilarity: (timeframe: Timeframe, limit = 10) => api.get<DashboardResponse>('/dashboard/high-textbook-similarity', { params: { timeframe, limit } }).then(r => r.data),
  noSignal: (timeframe: Timeframe, limit = 10) => api.get<DashboardResponse>('/dashboard/watchlist-no-signal', { params: { timeframe, limit } }).then(r => r.data),
  armed: (timeframe: Timeframe, limit = 10) => api.get<DashboardResponse>('/dashboard/pattern-armed', { params: { timeframe, limit } }).then(r => r.data),
  forming: (timeframe: Timeframe, limit = 10) => api.get<DashboardResponse>('/dashboard/forming-candidates', { params: { timeframe, limit } }).then(r => r.data),
  liveIntraday: (timeframe: Timeframe, limit = 10) => api.get<DashboardResponse>('/dashboard/live-intraday-candidates', { params: { timeframe, limit } }).then(r => r.data),
  scanStatus: (timeframe: Timeframe) => api.get<ScanStatusResponse>('/dashboard/scan-status', { params: { timeframe } }).then(r => r.data),
  refreshScan: (timeframe: Timeframe) => api.post<ScanStatusResponse>('/dashboard/scan-refresh', null, { params: { timeframe } }).then(r => r.data),
}

export const patternsApi = {
  library: () => api.get<PatternLibraryEntry[]>('/patterns/library').then(r => r.data),
  get: (type: string) => api.get<PatternLibraryEntry>(`/patterns/library/${type}`).then(r => r.data),
  stats: () => api.get<PatternStatsResponse>('/patterns/stats').then(r => r.data),
  refreshStats: () => api.post<{ accepted: boolean; message: string; requested_at: string }>('/patterns/stats/refresh').then(r => r.data),
}

export const screenerApi = {
  run: (req: ScreenerRequest) => api.post<DashboardItem[]>('/screeners/run', req).then(r => r.data),
}

export const watchlistApi = {
  /** Return the server-side watchlist. */
  get: () => api.get<WatchlistItem[]>('/watchlist').then(r => r.data),
  /** Full replace — overwrite the server list with the current local list. */
  sync: (items: WatchlistItem[]) => api.post<WatchlistItem[]>('/watchlist', items).then(r => r.data),
  /** Add one symbol (idempotent). */
  add: (item: Omit<WatchlistItem, 'addedAt'>) =>
    api.post<WatchlistItem[]>('/watchlist/add', item).then(r => r.data),
  /** Remove one symbol by code. */
  remove: (code: string) => api.delete<WatchlistItem[]>(`/watchlist/${code}`).then(r => r.data),
}

export const outcomesApi = {
  /** Return all outcome records (newest first). */
  list: () => api.get<OutcomeRecord[]>('/outcomes').then(r => r.data),
  /** Record a new signal outcome (outcome='pending' by default). */
  record: (record: Omit<OutcomeRecord, 'id' | 'recorded_at' | 'updated_at'>) =>
    api.post<{ status: string; id: number; total_records: number }>('/outcomes', record).then(r => r.data),
  /** Update the outcome of a previously-recorded signal. */
  update: (
    id: number,
    update: { outcome: OutcomeStatus; exit_price?: number; exit_date?: string; notes?: string },
  ) => api.patch<{ status: string; id: number }>(`/outcomes/${id}`, update).then(r => r.data),
  /** Delete a record. */
  remove: (id: number) =>
    api.delete<{ status: string; deleted_id: number }>(`/outcomes/${id}`).then(r => r.data),
  /** Aggregate stats: overall win-rate + per-pattern breakdown. */
  summary: () => api.get<OutcomesSummary>('/outcomes/summary').then(r => r.data),
}

export const systemApi = {
  status: () => api.get<RuntimeStatusResponse>('/system/status').then(r => r.data),
  warmupStatus: () => api.get<IntradayWarmupJobStatus>('/system/intraday/warmup-status').then(r => r.data),
  warmupIntraday: (req: IntradayWarmupRequest) =>
    api.post<IntradayWarmupResponse>('/system/intraday/warmup', req).then(r => r.data),
  warmupCandidates: (req: IntradayCandidateWarmupRequest) =>
    api.post<IntradayWarmupResponse>('/system/intraday/warmup-candidates', req).then(r => r.data),
  warmupIntradayBackground: (req: IntradayWarmupRequest) =>
    api.post<IntradayWarmupJobStatus>('/system/intraday/warmup/background', req).then(r => r.data),
  warmupCandidatesBackground: (req: IntradayCandidateWarmupRequest) =>
    api.post<IntradayWarmupJobStatus>('/system/intraday/warmup-candidates/background', req).then(r => r.data),
}
