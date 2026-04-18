import axios from 'axios'
import type {
  SymbolInfo, OHLCVBar, AnalysisResult, PriceInfo,
  DashboardResponse, PatternLibraryEntry, ScreenerRequest, DashboardItem, ScanStatusResponse, Timeframe,
  PatternStatsResponse,
} from '@/types/api'

const api = axios.create({ baseURL: '/api/v1' })

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
  longHigh: (timeframe: Timeframe, limit = 10) => api.get<DashboardResponse>('/dashboard/long-high-probability', { params: { timeframe, limit } }).then(r => r.data),
  shortHigh: (timeframe: Timeframe, limit = 10) => api.get<DashboardResponse>('/dashboard/short-high-probability', { params: { timeframe, limit } }).then(r => r.data),
  highSimilarity: (timeframe: Timeframe, limit = 10) => api.get<DashboardResponse>('/dashboard/high-textbook-similarity', { params: { timeframe, limit } }).then(r => r.data),
  noSignal: (timeframe: Timeframe, limit = 10) => api.get<DashboardResponse>('/dashboard/watchlist-no-signal', { params: { timeframe, limit } }).then(r => r.data),
  armed: (timeframe: Timeframe, limit = 10) => api.get<DashboardResponse>('/dashboard/pattern-armed', { params: { timeframe, limit } }).then(r => r.data),
  forming: (timeframe: Timeframe, limit = 10) => api.get<DashboardResponse>('/dashboard/forming-candidates', { params: { timeframe, limit } }).then(r => r.data),
  scanStatus: (timeframe: Timeframe) => api.get<ScanStatusResponse>('/dashboard/scan-status', { params: { timeframe } }).then(r => r.data),
  refreshScan: (timeframe: Timeframe) => api.post<ScanStatusResponse>('/dashboard/scan-refresh', null, { params: { timeframe } }).then(r => r.data),
}

export const patternsApi = {
  library: () => api.get<PatternLibraryEntry[]>('/patterns/library').then(r => r.data),
  get: (type: string) => api.get<PatternLibraryEntry>(`/patterns/library/${type}`).then(r => r.data),
  stats: () => api.get<PatternStatsResponse>('/patterns/stats').then(r => r.data),
}

export const screenerApi = {
  run: (req: ScreenerRequest) => api.post<DashboardItem[]>('/screeners/run', req).then(r => r.data),
}
