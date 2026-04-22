import axios, { type InternalAxiosRequestConfig } from 'axios'
import type {
  SymbolInfo, OHLCVBar, AnalysisResult, PriceInfo,
  AiRecommendationItem, AiRecommendationResponse, DashboardOverviewResponse, DashboardResponse, PatternLibraryEntry, ScreenerRequest, DashboardItem, ReferenceCaseResponse, ScanStatusResponse, Timeframe,
  IntradayCandidateWarmupRequest, IntradayWarmupJobStatus, IntradayWarmupRequest, IntradayWarmupResponse, KisPrimeStatus, PatternStatsResponse, RuntimeStatusResponse,
  WatchlistItem, OutcomeEvaluationResponse, OutcomeRecord, OutcomesSummary, OutcomeStatus,
} from '@/types/api'

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
  getReferenceCases: (symbol: string, timeframe: Timeframe, limit = 6) =>
    api.get<ReferenceCaseResponse>(`/symbols/${symbol}/reference-cases`, { params: { timeframe, limit } }).then(r => r.data),
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
    market_brief: `${timeframeLabel} 기준으로 우선 검토 ${priorityItems.length}개, 대기 ${watchItems.length}개, 리스크 점검 ${riskItems.length}개입니다.`,
    portfolio_guidance: priorityItems[0]
      ? `${priorityItems[0].symbol.name}처럼 준비도와 데이터 품질이 함께 맞는 후보부터 보는 편이 낫습니다.`
      : watchItems[0]
        ? `${watchItems[0].symbol.name}처럼 트리거 확인이 필요한 후보가 많습니다. 서두르지 않는 편이 낫습니다.`
        : '강한 우선 후보가 적어 관망과 리스크 점검 비중이 높습니다.',
    items,
    priority_items: priorityItems,
    watch_items: watchItems,
    risk_items: riskItems,
    watchlist_focus_items: [],
    disclaimer: '투자 권유가 아닌 기술적 분석 보조 정보입니다. 실제 매매 여부와 손절 기준은 직접 확인하세요.',
  }
}

function makeFallbackRecommendation(item: DashboardItem): AiRecommendationItem {
  const score = fallbackScore(item)
  const stance = fallbackStance(item, score)
  const doNow = buildFallbackDoNow(item, stance)
  const avoidIf = buildFallbackAvoidIf(item)
  const reviewPrice = buildFallbackReviewPrice(item)
  const skipReason = buildFallbackSkipReason(item, stance)

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
    watchlist_priority: false,
    summary:
      stance === 'priority_watch'
        ? `${item.symbol.name}은 준비도와 구조가 살아 있어 오늘 우선 검토 후보입니다.`
        : stance === 'avoid_chase'
          ? `${item.symbol.name}은 방향성은 좋지만 추격보다 눌림 확인이 더 중요합니다.`
          : stance === 'wait_for_trigger'
            ? `${item.symbol.name}은 구조는 유지되지만 트리거 확인이 먼저입니다.`
            : `${item.symbol.name}은 리스크와 데이터 상태를 먼저 점검해야 합니다.`,
    action_line: `지금 할 일: ${doNow}`,
    do_now: doNow,
    avoid_if: avoidIf,
    review_price: reviewPrice,
    skip_reason: skipReason,
    overlap_risk: '',
    reasons: [
      `상승 확률 ${(item.p_up * 100).toFixed(1)}%, 하락 확률 ${(item.p_down * 100).toFixed(1)}%`,
      `거래 준비도 ${(item.trade_readiness_score * 100).toFixed(0)}%, 진입 구간 ${(item.entry_window_score * 100).toFixed(0)}%`,
      `데이터 품질 ${(item.data_quality * 100).toFixed(0)}%, 신뢰도 ${(item.confidence * 100).toFixed(0)}%`,
      item.reason_summary || item.confluence_summary,
    ].filter(Boolean),
    risk_flags: item.risk_flags?.length ? item.risk_flags : item.trend_warning ? [item.trend_warning] : [],
    next_actions: [
      `지금 할 일: ${doNow}`,
      `진입 금지 조건: ${avoidIf}`,
      `다시 볼 가격: ${reviewPrice}`,
      `오늘 안 봐도 되는 이유: ${skipReason}`,
      ...(item.confirmation_checklist ?? []).slice(0, 2),
    ].filter(Boolean),
    position_hint:
      stance === 'priority_watch'
        ? '우선 검토 후보입니다. 확인 신호가 나오면 대응하고 무효화 기준은 미리 정해두는 편이 낫습니다.'
        : stance === 'risk_review'
          ? '지금은 방어적 판단이 우선입니다.'
          : '트리거가 맞을 때만 다시 평가하는 편이 낫습니다.',
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

function buildFallbackDoNow(item: DashboardItem, stance: AiRecommendationItem['stance']) {
  if (item.next_trigger) return `${item.next_trigger} 확인 후 재평가`
  if (stance === 'priority_watch') return '핵심 가격대와 거래량 반응 확인'
  if (stance === 'avoid_chase') return '눌림 또는 지지 확인 전까지 대기'
  if (stance === 'risk_review') return '신규 진입보다 리스크 정리 우선'
  return '트리거 형성 전까지 관찰 유지'
}

function buildFallbackAvoidIf(item: DashboardItem) {
  if (item.risk_flags?.length) return item.risk_flags[0]
  if (item.no_signal_flag && item.reason_summary) return item.reason_summary
  if (item.reward_risk_ratio < 1.2) return '손익비가 낮아 비중 확대를 피해야 함'
  return '핵심 가격대 지지 확인 전 추격 금지'
}

function buildFallbackReviewPrice(item: DashboardItem) {
  return item.next_trigger || item.entry_window_summary || item.reentry_trigger || '핵심 가격대가 다시 정렬될 때 재검토'
}

function buildFallbackSkipReason(item: DashboardItem, stance: AiRecommendationItem['stance']) {
  if (stance === 'priority_watch') return '이미 상위 우선 후보라 오늘 안 볼 이유가 크지 않음'
  if (item.no_signal_flag && item.reason_summary) return item.reason_summary
  if (item.data_quality < 0.45) return '데이터 품질이 낮아 오늘은 강하게 해석하지 않는 편이 나음'
  if (stance === 'avoid_chase') return '가격이 먼저 달려 눌림 없이 접근하면 기대값이 떨어짐'
  return '트리거가 아직 완성되지 않아 서둘러 볼 이유가 약함'
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
  get: () => api.get<WatchlistItem[]>('/watchlist').then(r => r.data),
  sync: (items: WatchlistItem[]) => api.post<WatchlistItem[]>('/watchlist', items).then(r => r.data),
  add: (item: Omit<WatchlistItem, 'addedAt'>) =>
    api.post<WatchlistItem[]>('/watchlist/add', item).then(r => r.data),
  remove: (code: string) => api.delete<WatchlistItem[]>(`/watchlist/${code}`).then(r => r.data),
}

export const outcomesApi = {
  list: () => api.get<OutcomeRecord[]>('/outcomes').then(r => r.data),
  record: (record: Omit<OutcomeRecord, 'id' | 'recorded_at' | 'updated_at'>) =>
    api.post<{ status: string; id: number; total_records: number }>('/outcomes', record).then(r => r.data),
  update: (
    id: number,
    update: { outcome: OutcomeStatus; exit_price?: number; exit_date?: string; notes?: string },
  ) => api.patch<{ status: string; id: number }>(`/outcomes/${id}`, update).then(r => r.data),
  remove: (id: number) =>
    api.delete<{ status: string; deleted_id: number }>(`/outcomes/${id}`).then(r => r.data),
  summary: () => api.get<OutcomesSummary>('/outcomes/summary').then(r => r.data),
  evaluatePending: () => api.post<OutcomeEvaluationResponse>('/outcomes/evaluate-pending').then(r => r.data),
}

export const systemApi = {
  status: () => api.get<RuntimeStatusResponse>('/system/status').then(r => r.data),
  kisPrimeStatus: () => api.get<KisPrimeStatus>('/system/kis/prime-status').then(r => r.data),
  primeKis: (params?: { symbol?: string; timeframe?: string }) =>
    api.post<KisPrimeStatus>('/system/kis/prime', null, { params }).then(r => r.data),
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
