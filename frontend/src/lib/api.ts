import axios, { type InternalAxiosRequestConfig } from 'axios'
import type {
  SymbolInfo, OHLCVBar, AnalysisResult, PriceInfo,
  AiRecommendationItem, AiRecommendationResponse, DashboardOverviewResponse, DashboardResponse, PatternLibraryEntry, ScreenerRequest, DashboardItem, ScanStatusResponse, Timeframe,
  IntradayCandidateWarmupRequest, IntradayWarmupJobStatus, IntradayWarmupRequest, IntradayWarmupResponse, PatternStatsResponse, RuntimeStatusResponse,
  WatchlistItem, OutcomeRecord, OutcomesSummary, OutcomeStatus,
} from '@/types/api'

// In development the Vite proxy forwards /api → backend (see vite.config.ts).
// In production set VITE_API_BASE_URL to your backend's public URL
// (e.g. https://stock-chart-helper-api.onrender.com) and this will call it directly.
function resolveApiBase() {
  if (typeof window !== 'undefined' && window.location.hostname.endsWith('vercel.app')) {
    return '/api/v1'
  }

  if (import.meta.env.VITE_API_BASE_URL) {
    return `${String(import.meta.env.VITE_API_BASE_URL).replace(/\/$/, '')}/api/v1`
  }

  return '/api/v1'
}

const _base = resolveApiBase()
const _directBase = import.meta.env.VITE_API_BASE_URL
  ? `${String(import.meta.env.VITE_API_BASE_URL).replace(/\/$/, '')}/api/v1`
  : 'https://stock-chart-helper-api.onrender.com/api/v1'
const REQUEST_TIMEOUT_MS = 20_000
const MAX_DIRECT_RETRIES = 1

interface RetryableAxiosConfig extends InternalAxiosRequestConfig {
  __retryCount?: number
  __directFallbackTried?: boolean
}

const api = axios.create({ baseURL: _base, timeout: REQUEST_TIMEOUT_MS })

api.interceptors.response.use(undefined, async error => {
  const config = error.config as RetryableAxiosConfig | undefined
  const method = config?.method?.toLowerCase() ?? 'get'
  const status = error.response?.status
  const isTransient =
    !error.response ||
    status === 408 ||
    status === 429 ||
    status === 500 ||
    status === 502 ||
    status === 503 ||
    status === 504

  if (!config || method !== 'get' || !isTransient) {
    return Promise.reject(error)
  }

  if ((config.baseURL ?? _base) === '/api/v1' && !config.__directFallbackTried) {
    config.__directFallbackTried = true
    config.__retryCount = 0
    config.baseURL = _directBase
    await new Promise(resolve => window.setTimeout(resolve, 700))
    return api.request(config)
  }

  if ((config.__retryCount ?? 0) >= MAX_DIRECT_RETRIES) {
    return Promise.reject(error)
  }

  const retryCount = (config.__retryCount ?? 0) + 1
  config.__retryCount = retryCount
  await new Promise(resolve => window.setTimeout(resolve, 1_200 * retryCount))
  return api.request(config)
})

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

export const aiApi = {
  recommendations: async (timeframe: Timeframe, limit = 8) => {
    try {
      return await api.get<AiRecommendationResponse>('/ai/recommendations', { params: { timeframe, limit } }).then(r => r.data)
    } catch (error) {
      if (axios.isAxiosError(error) && error.response?.status === 404) {
        return fallbackAiRecommendations(timeframe, limit)
      }
      throw error
    }
  },
}

async function fallbackAiRecommendations(timeframe: Timeframe, limit: number): Promise<AiRecommendationResponse> {
  const overview = await api
    .get<DashboardOverviewResponse>('/dashboard/overview', { params: { timeframe, limit: Math.max(limit, 10) } })
    .then(response => response.data)
  const rows = new Map<string, DashboardItem>()
  const timeframeLabel = overview.timeframe_label || timeframe
  const sections: DashboardResponse[] = [
    overview.long_high_probability,
    overview.pattern_armed,
    overview.forming_candidates,
    overview.high_textbook_similarity,
    overview.watchlist_no_signal,
  ]

  for (const section of sections) {
    for (const item of section.items) {
      const previous = rows.get(item.symbol.code)
      if (!previous || fallbackScore(item) > fallbackScore(previous)) {
        rows.set(item.symbol.code, item)
      }
    }
  }

  const ranked = Array.from(rows.values())
    .map(item => makeFallbackRecommendation(item))
    .sort((a, b) => b.score - a.score)
  const items = rerankAiItems(ranked.slice(0, limit))
  const priorityItems = rerankAiItems(ranked.filter(item => item.stance === 'priority_watch').slice(0, limit))
  const watchItems = rerankAiItems(ranked.filter(item => item.stance === 'wait_for_trigger' || item.stance === 'avoid_chase').slice(0, limit))
  const riskItems = rerankAiItems(ranked.filter(item => item.stance === 'risk_review').slice(0, limit))

  return {
    generated_at: new Date().toISOString(),
    timeframe,
    timeframe_label: timeframeLabel,
    market_brief: `${timeframeLabel} 후보를 기존 스캔 API로 재계산했습니다. 우선 검토 ${priorityItems.length}개, 트리거 대기 ${watchItems.length}개, 리스크 점검 ${riskItems.length}개입니다.`,
    portfolio_guidance: priorityItems[0]
      ? `${priorityItems[0].symbol.name}처럼 준비도와 데이터 품질이 같이 맞는 후보를 먼저 보고, 같은 방향 후보가 과하게 겹치지 않게 관리하세요.`
      : watchItems[0]
        ? `${watchItems[0].symbol.name} 같은 트리거 대기 후보가 중심입니다. 확인 신호 전에는 관찰 비중을 유지하는 쪽이 좋습니다.`
        : '강한 후보가 적습니다. 공격보다 관망과 리스크 점검이 우선입니다.',
    items,
    priority_items: priorityItems,
    watch_items: watchItems,
    risk_items: riskItems,
    disclaimer: '투자 권유가 아닌 기술적 분석 보조 의견입니다. 실제 매매 전 재무, 뉴스, 수급, 손절 기준을 직접 확인하세요.',
  }
}

function makeFallbackRecommendation(item: DashboardItem): AiRecommendationItem {
  const score = fallbackScore(item)
  const stance = fallbackStance(item, score)
  return {
    rank: 0,
    symbol: item.symbol,
    timeframe: item.timeframe,
    timeframe_label: item.timeframe_label,
    stance,
    stance_label: stance === 'priority_watch' ? '우선 검토' : stance === 'wait_for_trigger' ? '트리거 대기' : stance === 'avoid_chase' ? '추격 금지' : '리스크 점검',
    score,
    confidence: clamp01(0.35 * item.confidence + 0.25 * item.sample_reliability + 0.25 * item.data_quality + 0.15 * item.liquidity_score),
    source_category: item.live_intraday_candidate ? 'live_intraday' : item.no_signal_flag ? 'risk_watch' : item.state === 'forming' ? 'forming_pattern' : 'active_pattern',
    summary:
      stance === 'priority_watch'
        ? `${item.symbol.name}은 패턴 구조와 거래 준비도가 함께 들어와 우선 관찰 후보입니다.`
        : stance === 'avoid_chase'
          ? `${item.symbol.name}은 방향성은 보이나 진입 구간 점수가 낮아 추격보다 눌림 확인이 우선입니다.`
          : stance === 'wait_for_trigger'
            ? `${item.symbol.name}은 구조는 살아 있지만 확인 트리거를 기다리는 편이 좋습니다.`
            : `${item.symbol.name}은 현재 리스크와 데이터 품질을 먼저 점검해야 합니다.`,
    reasons: [
      `상승확률 ${(item.p_up * 100).toFixed(1)}%, 하락확률 ${(item.p_down * 100).toFixed(1)}%`,
      `거래준비도 ${(item.trade_readiness_score * 100).toFixed(0)}%, 진입구간 ${(item.entry_window_score * 100).toFixed(0)}%`,
      `데이터 품질 ${(item.data_quality * 100).toFixed(0)}%, 신뢰도 ${(item.confidence * 100).toFixed(0)}%`,
      item.reason_summary || item.confluence_summary,
    ].filter(Boolean),
    risk_flags: item.risk_flags?.length ? item.risk_flags : item.trend_warning ? [item.trend_warning] : [],
    next_actions: [
      item.next_trigger,
      ...(item.confirmation_checklist ?? []).slice(0, 3),
      stance === 'priority_watch' ? '확인 신호와 손절 기준을 동시에 고정' : '트리거 충족 전에는 관심종목에만 보관',
    ].filter(Boolean),
    position_hint:
      stance === 'priority_watch'
        ? '우선 관찰 후보입니다. 진입은 확인 트리거 이후가 적합합니다.'
        : stance === 'risk_review'
          ? '현재는 방어적 판단이 우선입니다.'
          : '관심종목에 두고 트리거가 맞을 때만 다시 평가하세요.',
    pattern_type: item.pattern_type,
    state: item.state,
    p_up: item.p_up,
    p_down: item.p_down,
    trade_readiness_score: item.trade_readiness_score,
    entry_window_score: item.entry_window_score,
    freshness_score: item.freshness_score,
    reward_risk_ratio: item.reward_risk_ratio,
    data_quality: item.data_quality,
    confluence_score: item.confluence_score,
    next_trigger: item.next_trigger,
    chart_path: `/chart/${item.symbol.code}`,
  }
}

function fallbackScore(item: DashboardItem) {
  const edge = clamp01((item.p_up - item.p_down + 0.2) / 0.55)
  const raw =
    0.2 * item.trade_readiness_score +
    0.16 * item.entry_window_score +
    0.12 * item.freshness_score +
    0.1 * item.reentry_score +
    0.1 * item.active_setup_score +
    0.1 * item.historical_edge_score +
    0.08 * item.confluence_score +
    0.06 * item.data_quality +
    0.04 * item.liquidity_score +
    0.04 * edge -
    (item.no_signal_flag ? 0.22 : 0) -
    Math.min((item.risk_flags?.length ?? 0) * 0.035, 0.14)
  return Math.round(clamp01(raw) * 1000) / 10
}

function fallbackStance(item: DashboardItem, score: number): AiRecommendationItem['stance'] {
  if (item.no_signal_flag || item.data_quality < 0.38 || item.action_plan === 'cooling') return 'risk_review'
  if (item.entry_window_score < 0.34 && item.p_up >= 0.58) return 'avoid_chase'
  if (score >= 68 && item.p_up >= 0.55 && item.trade_readiness_score >= 0.5) return 'priority_watch'
  if (score >= 52) return 'wait_for_trigger'
  return 'risk_review'
}

function rerankAiItems(items: AiRecommendationItem[]) {
  return items.map((item, index) => ({ ...item, rank: index + 1 }))
}

function clamp01(value: number) {
  return Math.max(0, Math.min(1, value))
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
