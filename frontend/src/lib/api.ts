import axios from 'axios'
import type {
  SymbolInfo, OHLCVBar, AnalysisResult, PriceInfo,
  DashboardResponse, PatternLibraryEntry, ScreenerRequest, DashboardItem, ScanStatusResponse
} from '@/types/api'

const api = axios.create({ baseURL: '/api/v1' })

export const symbolsApi = {
  search: (q: string) => api.get<SymbolInfo[]>('/symbols/search', { params: { q } }).then(r => r.data),
  getBars: (symbol: string, timeframe = '1d', days = 365) =>
    api.get<OHLCVBar[]>(`/symbols/${symbol}/bars`, { params: { timeframe, days } }).then(r => r.data),
  getAnalysis: (symbol: string, timeframe = '1d') =>
    api.get<AnalysisResult>(`/symbols/${symbol}/analysis`, { params: { timeframe } }).then(r => r.data),
  getPrice: (symbol: string) =>
    api.get<PriceInfo>(`/symbols/${symbol}/price`).then(r => r.data),
}

export const dashboardApi = {
  longHigh: (limit = 10) => api.get<DashboardResponse>('/dashboard/long-high-probability', { params: { limit } }).then(r => r.data),
  shortHigh: (limit = 10) => api.get<DashboardResponse>('/dashboard/short-high-probability', { params: { limit } }).then(r => r.data),
  highSimilarity: (limit = 10) => api.get<DashboardResponse>('/dashboard/high-textbook-similarity', { params: { limit } }).then(r => r.data),
  noSignal: (limit = 10) => api.get<DashboardResponse>('/dashboard/watchlist-no-signal', { params: { limit } }).then(r => r.data),
  armed: (limit = 10) => api.get<DashboardResponse>('/dashboard/pattern-armed', { params: { limit } }).then(r => r.data),
  scanStatus: () => api.get<ScanStatusResponse>('/dashboard/scan-status').then(r => r.data),
  refreshScan: () => api.post<ScanStatusResponse>('/dashboard/scan-refresh').then(r => r.data),
}

export const patternsApi = {
  library: () => api.get<PatternLibraryEntry[]>('/patterns/library').then(r => r.data),
  get: (type: string) => api.get<PatternLibraryEntry>(`/patterns/library/${type}`).then(r => r.data),
}

export const screenerApi = {
  run: (req: ScreenerRequest) => api.post<DashboardItem[]>('/screeners/run', req).then(r => r.data),
}
