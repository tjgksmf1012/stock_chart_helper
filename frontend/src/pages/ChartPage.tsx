import { useEffect, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { useQueries, useQuery } from '@tanstack/react-query'
import {
  AlertTriangle,
  ArrowLeft,
  Database,
  Layers3,
  Loader2,
  Search,
  ShieldAlert,
  Star,
  TrendingDown,
  TrendingUp,
} from 'lucide-react'

import { AnalysisPanel } from '@/components/chart/AnalysisPanel'
import { CandleChart } from '@/components/chart/CandleChart'
import { Badge } from '@/components/ui/Badge'
import { Card } from '@/components/ui/Card'
import { QueryError } from '@/components/ui/QueryError'
import { symbolsApi } from '@/lib/api'
import {
  DEFAULT_TIMEFRAME,
  getChartLookbackDays,
  getContextTimeframes,
  TIMEFRAME_OPTIONS,
  timeframeLabel,
} from '@/lib/timeframes'
import { cn, fmtDateTime, fmtNumber, fmtPct, fmtPrice } from '@/lib/utils'
import { useAppStore } from '@/store/app'
import type { AnalysisResult, Timeframe } from '@/types/api'

export default function ChartPage() {
  const { symbol } = useParams<{ symbol: string }>()
  const nav = useNavigate()
  const { selectedTimeframe, setTimeframe, addToWatchlist, removeFromWatchlist, isWatched } = useAppStore()
  const timeframe = selectedTimeframe ?? DEFAULT_TIMEFRAME
  const [searchQuery, setSearchQuery] = useState('')
  const [searchResults, setSearchResults] = useState<Array<{ code: string; name: string; market: string }>>([])
  const searchRequestRef = useRef(0)
  const watched = symbol ? isWatched(symbol) : false

  const barsQ = useQuery({
    queryKey: ['bars', symbol, timeframe],
    queryFn: () => symbolsApi.getBars(symbol!, timeframe, getChartLookbackDays(timeframe)),
    enabled: !!symbol,
    staleTime: 60_000,
    retry: ['1m', '15m', '30m', '60m'].includes(timeframe) ? 0 : 1,
  })

  const analysisQ = useQuery({
    queryKey: ['analysis', symbol, timeframe],
    queryFn: () => symbolsApi.getAnalysis(symbol!, timeframe),
    enabled: !!symbol,
    staleTime: 180_000,
    retry: 1,
  })

  const contextTimeframes = getContextTimeframes(timeframe)
  const contextQueries = useQueries({
    queries: contextTimeframes.map(contextTimeframe => ({
      queryKey: ['analysis', symbol, contextTimeframe],
      queryFn: () => symbolsApi.getAnalysis(symbol!, contextTimeframe),
      enabled: !!symbol,
      staleTime: 180_000,
    })),
  })

  const priceQ = useQuery({
    queryKey: ['price', symbol],
    queryFn: () => symbolsApi.getPrice(symbol!),
    enabled: !!symbol,
    staleTime: 60_000,
    refetchInterval: 120_000,
  })

  useEffect(() => {
    const query = searchQuery.trim()
    const requestId = ++searchRequestRef.current

    if (query.length < 1) {
      setSearchResults([])
      return
    }

    const timer = window.setTimeout(async () => {
      try {
        const results = await symbolsApi.search(query)
        if (searchRequestRef.current === requestId) {
          setSearchResults(results)
        }
      } catch {
        if (searchRequestRef.current === requestId) {
          setSearchResults([])
        }
      }
    }, 180)

    return () => window.clearTimeout(timer)
  }, [searchQuery])

  useEffect(() => {
    setSearchQuery('')
    setSearchResults([])
  }, [symbol])

  const analysis = analysisQ.data
  const hasBars = (barsQ.data?.length ?? 0) > 0
  const isPrimaryLoading = Boolean(symbol) && !analysis && analysisQ.isLoading
  const isChartLoading = Boolean(symbol) && !hasBars && barsQ.isLoading
  const isChartError = Boolean(symbol) && !hasBars && barsQ.isError
  const contextAnalyses = contextQueries.flatMap(query => (query.data ? [query.data] : []))
  const contextSummary = summarizeContext(analysis, contextAnalyses)
  const qualityTone =
    (analysis?.data_quality ?? 0) >= 0.8 ? 'bullish' : (analysis?.data_quality ?? 0) >= 0.6 ? 'neutral' : 'warning'

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <button onClick={() => nav('/')} className="text-muted-foreground transition-colors hover:text-foreground">
          <ArrowLeft size={18} />
        </button>

        <div className="relative max-w-sm flex-1">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
          <input
            className="w-full rounded-lg border border-border bg-card py-2 pl-8 pr-3 text-sm focus:border-primary/60 focus:outline-none"
            placeholder="종목 코드 또는 이름 검색"
            value={searchQuery}
            onChange={event => setSearchQuery(event.target.value)}
            onKeyDown={event => {
              if (event.key === 'Escape') {
                setSearchResults([])
                return
              }
              if (event.key === 'Enter' && searchResults.length > 0) {
                nav(`/chart/${searchResults[0].code}`)
                setSearchQuery('')
                setSearchResults([])
              }
            }}
          />
          {searchResults.length > 0 && (
            <div className="absolute left-0 right-0 top-full z-50 mt-1 max-h-48 overflow-y-auto rounded-lg border border-border bg-card shadow-xl">
              {searchResults.map(result => (
                <button
                  key={result.code}
                  className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm transition-colors hover:bg-muted/50"
                  onClick={() => {
                    nav(`/chart/${result.code}`)
                    setSearchQuery('')
                    setSearchResults([])
                  }}
                >
                  <span className="font-mono text-xs text-muted-foreground">{result.code}</span>
                  <span>{result.name}</span>
                  <span className="ml-auto text-xs text-muted-foreground">{result.market}</span>
                </button>
              ))}
            </div>
          )}
        </div>

        <div className="flex flex-wrap gap-1">
          {TIMEFRAME_OPTIONS.map(option => (
            <button
              key={option.value}
              onClick={() => setTimeframe(option.value)}
              className={cn(
                'rounded-md px-2.5 py-1.5 text-xs transition-colors',
                timeframe === option.value
                  ? 'bg-primary text-primary-foreground'
                  : 'border border-border bg-card text-muted-foreground hover:text-foreground',
              )}
            >
              {option.label}
            </button>
          ))}
        </div>
      </div>

      {!symbol && (
        <Card>
          <p className="text-sm text-muted-foreground">차트를 보려면 종목을 검색하거나 대시보드에서 종목을 선택해 주세요.</p>
        </Card>
      )}

      {analysis && (
        <div className="space-y-4">
          <div className="rounded-xl border border-border bg-card p-4">
            <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
              <div className="space-y-2">
                <div className="flex flex-wrap items-center gap-2">
                  <h1 className="text-lg font-bold">{analysis.symbol.name}</h1>
                  <span className="font-mono text-sm text-muted-foreground">{symbol}</span>
                  <span className="text-xs text-muted-foreground">{analysis.symbol.market}</span>
                  <Badge variant={qualityTone}>{analysis.timeframe_label}</Badge>
                  <Badge variant={actionPlanVariant(analysis.action_plan)}>{analysis.action_plan_label}</Badge>
                  <Badge variant={scoreVariant(analysis.trade_readiness_score ?? 0)}>
                    준비 {Math.round((analysis.trade_readiness_score ?? 0) * 100)}%
                  </Badge>
                  <Badge variant={scoreVariant(analysis.entry_window_score ?? 0)}>
                    진입 {Math.round((analysis.entry_window_score ?? 0) * 100)}%
                  </Badge>
                  <Badge variant={scoreVariant(analysis.freshness_score ?? 0)}>
                    신선 {Math.round((analysis.freshness_score ?? 0) * 100)}%
                  </Badge>
                  <Badge variant={scoreVariant(analysis.reentry_score ?? 0)}>
                    재진입 {Math.round((analysis.reentry_score ?? 0) * 100)}%
                  </Badge>
                  <Badge variant={scoreVariant(analysis.active_setup_score ?? 0)}>
                    활성 {Math.round((analysis.active_setup_score ?? 0) * 100)}%
                  </Badge>
                  {analysis.is_provisional && <Badge variant="warning">잠정</Badge>}
                  <button
                    onClick={() => {
                      if (!symbol) return
                      if (watched) removeFromWatchlist(symbol)
                      else addToWatchlist({ code: symbol, name: analysis.symbol.name, market: analysis.symbol.market })
                    }}
                    className={cn(
                      'flex items-center gap-1 rounded-md px-2 py-1 text-xs transition-colors',
                      watched
                        ? 'bg-yellow-400/15 text-yellow-400 hover:bg-yellow-400/25'
                        : 'text-muted-foreground hover:bg-yellow-400/10 hover:text-yellow-400',
                    )}
                  >
                    <Star size={12} className={watched ? 'fill-yellow-400' : ''} />
                    {watched ? '관심종목 해제' : '추가'}
                  </button>
                </div>

                {priceQ.data && priceQ.data.close > 0 && (
                  <div className="flex flex-wrap items-center gap-3">
                    <span className="font-mono text-xl font-bold">{fmtPrice(priceQ.data.close)}</span>
                    <span
                      className={cn(
                        'flex items-center gap-0.5 text-sm font-medium',
                        priceQ.data.change >= 0 ? 'text-emerald-400' : 'text-red-400',
                      )}
                    >
                      {priceQ.data.change >= 0 ? <TrendingUp size={13} /> : <TrendingDown size={13} />}
                      {priceQ.data.change >= 0 ? '+' : ''}
                      {fmtPrice(priceQ.data.change)}
                      <span className="text-xs">
                        ({priceQ.data.change >= 0 ? '+' : ''}
                        {fmtPct(priceQ.data.change_pct)})
                      </span>
                    </span>
                    <span className="text-xs text-muted-foreground">{priceQ.data.source === 'kis' ? '실시간' : '종가 기준'}</span>
                  </div>
                )}

                <div className="flex flex-wrap items-center gap-3 text-xs text-muted-foreground">
                  <span>분석 업데이트 {fmtDateTime(analysis.updated_at)}</span>
                  <span className="inline-flex items-center gap-1">
                    <Database size={12} />
                    {analysis.data_source}
                  </span>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3 text-right sm:grid-cols-4 xl:grid-cols-9">
                <MetricCell label="상승 확률" value={`${(analysis.p_up * 100).toFixed(0)}%`} tone="text-green-400" />
                <MetricCell label="하락 확률" value={`${(analysis.p_down * 100).toFixed(0)}%`} tone="text-red-400" />
                <MetricCell label="신뢰도" value={`${(analysis.confidence * 100).toFixed(0)}%`} />
                <MetricCell label="거래 준비도" value={`${Math.round((analysis.trade_readiness_score ?? 0) * 100)}%`} />
                <MetricCell label="진입 구간" value={`${Math.round((analysis.entry_window_score ?? 0) * 100)}%`} />
                <MetricCell label="패턴 신선도" value={`${Math.round((analysis.freshness_score ?? 0) * 100)}%`} />
                <MetricCell label="재진입 구조" value={`${Math.round((analysis.reentry_score ?? 0) * 100)}%`} />
                <MetricCell label="활성 셋업" value={`${Math.round((analysis.active_setup_score ?? 0) * 100)}%`} />
                <MetricCell label="시가총액" value={analysis.symbol.market_cap ? fmtNumber(analysis.symbol.market_cap) : '-'} />
              </div>
            </div>

            {analysis.fetch_message && (
              <div className="mt-3 rounded-lg border border-border bg-background/60 px-3 py-2 text-xs text-muted-foreground">
                {analysis.fetch_message}
              </div>
            )}
            {analysis.action_plan_summary && (
              <div className="mt-3 rounded-lg border border-primary/20 bg-primary/5 px-3 py-2 text-xs leading-relaxed text-muted-foreground">
                <span className="font-semibold text-primary">실전 판단:</span> {analysis.action_plan_summary}
              </div>
            )}
            {analysis.entry_window_summary && (
              <div className="mt-3 rounded-lg border border-sky-400/20 bg-sky-400/5 px-3 py-2 text-xs leading-relaxed text-muted-foreground">
                <span className="font-semibold text-sky-200">진입 구간:</span> {analysis.entry_window_summary}
              </div>
            )}
            {analysis.freshness_summary && (
              <div className="mt-3 rounded-lg border border-violet-400/20 bg-violet-400/5 px-3 py-2 text-xs leading-relaxed text-muted-foreground">
                <span className="font-semibold text-violet-200">패턴 신선도:</span> {analysis.freshness_summary}
              </div>
            )}
            {analysis.reentry_summary && (
              <div className="mt-3 rounded-lg border border-amber-400/20 bg-amber-400/5 px-3 py-2 text-xs leading-relaxed text-muted-foreground">
                <span className="font-semibold text-amber-200">재진입 구조:</span> {analysis.reentry_summary}
                {analysis.reentry_case_label && analysis.reentry_case !== 'none' && (
                  <div className="mt-1 text-amber-100">유형: {analysis.reentry_case_label}</div>
                )}
                {analysis.reentry_trigger && <div className="mt-1 text-amber-100/90">확인 포인트: {analysis.reentry_trigger}</div>}
              </div>
            )}
          </div>

          <ExecutiveSummaryCard analysis={analysis} />
          <DataReadinessCard analysis={analysis} timeframe={timeframe} />
        </div>
      )}

      {analysis && (
        <Card className="space-y-3">
          <div className="flex items-center gap-2 text-sm font-semibold">
            <Layers3 size={15} className="text-primary" />
            멀티 타임프레임 컨텍스트
          </div>
          <p className="text-xs leading-relaxed text-muted-foreground">{contextSummary}</p>
          <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
            <ContextCard analysis={analysis} isPrimary />
            {contextQueries.map((query, index) => (
              <ContextCard
                key={contextTimeframes[index]}
                analysis={query.data ?? null}
                isLoading={query.isLoading}
                labelOverride={timeframeLabel(contextTimeframes[index])}
              />
            ))}
          </div>
        </Card>
      )}

      {isPrimaryLoading && (
        <Card className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 size={16} className="animate-spin" />
          분석을 불러오는 중입니다.
        </Card>
      )}

      {analysisQ.isError && !analysisQ.isLoading && !analysis && (
        <Card>
          <QueryError
            message="분석 데이터를 불러오지 못했습니다."
            onRetry={() => {
              analysisQ.refetch()
              barsQ.refetch()
            }}
          />
        </Card>
      )}

      {symbol && (analysis || hasBars || isChartLoading || isChartError) && (
        <div className="grid grid-cols-1 gap-4 xl:grid-cols-[minmax(0,1fr)_360px]">
          <Card>
            {hasBars && barsQ.data ? (
              <CandleChart bars={barsQ.data} analysis={analysis} height={520} />
            ) : isChartLoading ? (
              <div className="flex h-[520px] flex-col items-center justify-center gap-2 text-sm text-muted-foreground">
                <Loader2 size={18} className="animate-spin" />
                <p>차트를 불러오는 중입니다.</p>
                <p className="text-xs text-center text-muted-foreground/80">
                  분봉은 데이터 상태와 예열 상황에 따라 조금 더 오래 걸릴 수 있습니다.
                </p>
              </div>
            ) : isChartError ? (
              <div className="flex h-[520px] items-center justify-center p-4">
                <QueryError
                  message="차트 데이터를 불러오지 못했습니다. 분석 결과는 먼저 확인할 수 있습니다."
                  onRetry={() => barsQ.refetch()}
                />
              </div>
            ) : (
              <EmptyChartState
                analysis={analysis ?? null}
                timeframe={timeframe}
                onRetry={() => barsQ.refetch()}
                onFallbackDaily={() => setTimeframe('1d')}
              />
            )}
          </Card>
          {analysis ? (
            <AnalysisPanel analysis={analysis} />
          ) : (
            <Card className="flex items-center justify-center text-sm text-muted-foreground">
              분석 결과가 준비되면 오른쪽에 상세 해석이 표시됩니다.
            </Card>
          )}
        </div>
      )}
    </div>
  )
}

function EmptyChartState({
  analysis,
  timeframe,
  onRetry,
  onFallbackDaily,
}: {
  analysis: AnalysisResult | null
  timeframe: Timeframe
  onRetry: () => void
  onFallbackDaily: () => void
}) {
  const isIntraday = ['1m', '15m', '30m', '60m'].includes(timeframe)
  const title =
    analysis?.fetch_status_label ||
    (isIntraday ? '분봉 데이터를 아직 준비하지 못했습니다.' : '차트 데이터를 아직 준비하지 못했습니다.')
  const body =
    analysis?.fetch_message ||
    (isIntraday
      ? '장중 분봉 데이터가 부족하거나 백그라운드 예열이 아직 끝나지 않았습니다.'
      : '데이터 공급 상태에 따라 일시적으로 차트가 비어 있을 수 있습니다.')

  return (
    <div className="flex h-[520px] flex-col items-center justify-center gap-2 px-6 text-sm text-muted-foreground">
      <p className="font-medium text-foreground">{title}</p>
      <p className="max-w-md text-center text-xs text-muted-foreground/80">{body}</p>
      <div className="flex flex-wrap justify-center gap-2 pt-1">
        <button
          onClick={onRetry}
          className="rounded-md border border-border bg-card px-2.5 py-1.5 text-xs text-muted-foreground transition-colors hover:text-foreground"
        >
          다시 시도
        </button>
        {isIntraday && (
          <button
            onClick={onFallbackDaily}
            className="rounded-md border border-sky-500/30 bg-sky-500/10 px-2.5 py-1.5 text-xs text-sky-100 transition-colors hover:bg-sky-500/15"
          >
            일봉 먼저 보기
          </button>
        )}
      </div>
    </div>
  )
}

function ExecutiveSummaryCard({ analysis }: { analysis: AnalysisResult }) {
  const topRisk = analysis.risk_flags?.[0]
  const topChecklist = analysis.confirmation_checklist?.[0]

  return (
    <Card className="space-y-4 border-primary/20 bg-primary/5">
      <div className="flex items-center gap-2 text-sm font-semibold">
        <ShieldAlert size={15} className="text-primary" />
        한눈에 보는 매매 판단
      </div>
      <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
        <QuickPoint
          title="지금 판단"
          tone="primary"
          value={`${analysis.action_plan_label} · 준비 ${Math.round((analysis.trade_readiness_score ?? 0) * 100)}%`}
          description={analysis.action_plan_summary || analysis.trade_readiness_summary}
        />
        <QuickPoint
          title="다음 확인"
          tone="sky"
          value={analysis.next_trigger || analysis.entry_window_label}
          description={topChecklist || analysis.entry_window_summary}
        />
        <QuickPoint
          title="가장 큰 리스크"
          tone="amber"
          value={topRisk || (analysis.no_signal_flag ? '관망 우선' : analysis.freshness_label)}
          description={analysis.no_signal_flag ? analysis.no_signal_reason : analysis.fetch_message || analysis.freshness_summary}
        />
      </div>
      {analysis.is_provisional && (
        <div className="rounded-lg border border-amber-500/20 bg-amber-500/5 px-3 py-2 text-xs text-amber-100">
          이 결과는 잠정 상태입니다. 분봉이나 실시간 데이터가 더 들어오면 점수와 패턴 해석이 바뀔 수 있습니다.
        </div>
      )}
    </Card>
  )
}

function DataReadinessCard({ analysis, timeframe }: { analysis: AnalysisResult; timeframe: Timeframe }) {
  const blockers = buildDataBlockers(analysis, timeframe)

  return (
    <Card className="space-y-4">
      <div className="flex items-center gap-2 text-sm font-semibold">
        <AlertTriangle size={15} className="text-amber-300" />
        데이터 준비도와 해석 제한
      </div>
      <div className="grid grid-cols-2 gap-3 xl:grid-cols-5">
        <MetricCell label="수집 상태" value={analysis.fetch_status_label || '-'} />
        <MetricCell label="사용 바 수" value={`${analysis.available_bars ?? 0}개`} />
        <MetricCell label="데이터 품질" value={fmtPct(analysis.data_quality ?? 0, 0)} />
        <MetricCell label="표본 수" value={`${analysis.sample_size ?? 0}건`} />
        <MetricCell label="통계 기준" value={analysis.stats_timeframe || '-'} />
      </div>
      <div className="rounded-lg border border-border bg-background/60 p-3 text-xs leading-relaxed text-muted-foreground">
        <span className="font-medium text-foreground">해석 메모:</span> {buildDataReadinessSummary(analysis, blockers)}
      </div>
      <div className="grid grid-cols-1 gap-2 md:grid-cols-2">
        {blockers.map(blocker => (
          <div key={blocker} className="rounded-lg border border-amber-500/20 bg-amber-500/5 px-3 py-2 text-xs text-amber-100">
            {blocker}
          </div>
        ))}
      </div>
    </Card>
  )
}

function buildDataBlockers(analysis: AnalysisResult, timeframe: Timeframe): string[] {
  const blockers: string[] = []

  if (analysis.is_provisional) {
    blockers.push('아직 잠정 결과라서 이후 데이터가 더 들어오면 점수와 패턴 해석이 달라질 수 있습니다.')
  }
  if (analysis.no_signal_flag && analysis.no_signal_reason) {
    blockers.push(`현재는 관망 우선 구간입니다. 이유: ${analysis.no_signal_reason}`)
  }
  if ((analysis.available_bars ?? 0) < minimumBarsForTimeframe(timeframe)) {
    blockers.push(`${timeframeLabel(timeframe)} 기준으로 해석하기에 바 수가 아직 부족해 구조 점수의 신뢰도가 낮습니다.`)
  }
  if ((analysis.data_quality ?? 0) < 0.6) {
    blockers.push('데이터 품질 점수가 낮아 분봉 해석과 통계 기반 수치를 보수적으로 읽는 편이 안전합니다.')
  }
  if ((analysis.sample_reliability ?? 0) < 0.45) {
    blockers.push('유사 패턴 표본 신뢰도가 낮아 승률보다 구조와 리스크 관리 비중을 더 높게 두는 편이 좋습니다.')
  }
  if (analysis.fetch_message && blockers.length < 4) {
    blockers.push(analysis.fetch_message)
  }

  return blockers.slice(0, 4)
}

function buildDataReadinessSummary(analysis: AnalysisResult, blockers: string[]): string {
  if (blockers.length === 0) {
    return '현재 타임프레임 기준으로는 데이터 상태가 비교적 안정적입니다. 점수와 패턴 해석을 기본 판단 재료로 써도 무리가 크지 않습니다.'
  }
  if ((analysis.trade_readiness_score ?? 0) >= 0.65 && (analysis.data_quality ?? 0) >= 0.7 && !analysis.is_provisional) {
    return '진입 점수는 괜찮지만 몇 가지 제한 요소가 남아 있습니다. 바로 추격하기보다 다음 트리거와 리스크 기준을 같이 보는 편이 좋습니다.'
  }
  return '지금 화면의 숫자는 참고용으로는 쓸 수 있지만, 확정 신호처럼 받아들이기에는 이른 상태입니다. 구조 확인과 데이터 안정성을 먼저 체크해 주세요.'
}

function minimumBarsForTimeframe(timeframe: Timeframe): number {
  switch (timeframe) {
    case '1m':
      return 180
    case '15m':
      return 120
    case '30m':
      return 100
    case '60m':
      return 80
    case '1d':
      return 160
    case '1wk':
      return 90
    case '1mo':
      return 36
    default:
      return 80
  }
}

function QuickPoint({
  title,
  value,
  description,
  tone,
}: {
  title: string
  value: string
  description: string
  tone: 'primary' | 'sky' | 'amber'
}) {
  const toneClass = {
    primary: 'border-primary/20 bg-background/60 text-primary',
    sky: 'border-sky-400/20 bg-background/60 text-sky-200',
    amber: 'border-amber-400/20 bg-background/60 text-amber-200',
  }[tone]

  return (
    <div className={`rounded-lg border p-3 ${toneClass}`}>
      <div className="text-xs font-medium">{title}</div>
      <div className="mt-1 text-sm font-semibold text-foreground">{value}</div>
      <p className="mt-1 text-xs leading-relaxed text-muted-foreground">{description}</p>
    </div>
  )
}

function ContextCard({
  analysis,
  isPrimary = false,
  isLoading = false,
  labelOverride,
}: {
  analysis: AnalysisResult | null
  isPrimary?: boolean
  isLoading?: boolean
  labelOverride?: string
}) {
  if (isLoading) {
    return (
      <Card>
        <div className="text-xs text-muted-foreground">불러오는 중입니다...</div>
      </Card>
    )
  }

  if (!analysis) {
    return (
      <Card>
        <div className="text-xs text-muted-foreground">컨텍스트 데이터가 아직 없습니다.</div>
      </Card>
    )
  }

  return (
    <Card className={isPrimary ? 'border-primary/40' : undefined}>
      <div className="flex items-center justify-between gap-2">
        <div className="text-sm font-semibold">{labelOverride ?? analysis.timeframe_label}</div>
        {isPrimary && <Badge variant="default">현재</Badge>}
      </div>
      <div className="mt-3 space-y-2 text-xs text-muted-foreground">
        <div className="flex items-center justify-between">
          <span>상승 확률</span>
          <span className="text-green-400">{fmtPct(analysis.p_up, 0)}</span>
        </div>
        <div className="flex items-center justify-between">
          <span>거래 준비도</span>
          <span>{fmtPct(analysis.trade_readiness_score ?? 0, 0)}</span>
        </div>
        <div className="flex items-center justify-between">
          <span>패턴 신선도</span>
          <span>{fmtPct(analysis.freshness_score ?? 0, 0)}</span>
        </div>
        <div className="flex items-center justify-between">
          <span>재진입 구조</span>
          <span>{fmtPct(analysis.reentry_score ?? 0, 0)}</span>
        </div>
        {analysis.reentry_case_label && analysis.reentry_case !== 'none' && (
          <div className="flex items-center justify-between">
            <span>재진입 유형</span>
            <span>{analysis.reentry_case_label}</span>
          </div>
        )}
        <div className="flex items-center justify-between">
          <span>행동 가이드</span>
          <span>{analysis.action_plan_label}</span>
        </div>
      </div>
    </Card>
  )
}

function MetricCell({ label, value, tone }: { label: string; value: string; tone?: string }) {
  return (
    <div>
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className={cn('mt-1 text-sm font-semibold', tone)}>{value}</div>
    </div>
  )
}

function summarizeContext(primary: AnalysisResult | undefined, contexts: AnalysisResult[]): string {
  if (!primary) return '현재 분석 결과가 아직 없습니다.'
  if (contexts.length === 0) return `${primary.timeframe_label} 기준 단일 해석만 준비된 상태입니다.`

  const strongest = [...contexts].sort(
    (left, right) => (right.trade_readiness_score ?? 0) + right.p_up - ((left.trade_readiness_score ?? 0) + left.p_up),
  )[0]

  return `${primary.timeframe_label} 기준 현재 판단은 ${primary.action_plan_label}입니다. 보조 타임프레임 중에서는 ${strongest.timeframe_label} 쪽이 가장 강하고, 준비도 ${fmtPct(strongest.trade_readiness_score ?? 0, 0)}, 신선도 ${fmtPct(strongest.freshness_score ?? 0, 0)}, 재진입 구조 ${fmtPct(strongest.reentry_score ?? 0, 0)}(${strongest.reentry_case_label || strongest.reentry_label})로 읽힙니다.`
}

function actionPlanVariant(plan: string): 'bullish' | 'warning' | 'muted' | 'neutral' {
  if (plan === 'ready_now') return 'bullish'
  if (plan === 'watch') return 'neutral'
  if (plan === 'recheck') return 'warning'
  return 'muted'
}

function scoreVariant(score: number): 'bullish' | 'warning' | 'muted' | 'neutral' {
  if (score >= 0.72) return 'bullish'
  if (score >= 0.56) return 'neutral'
  if (score >= 0.4) return 'warning'
  return 'muted'
}
