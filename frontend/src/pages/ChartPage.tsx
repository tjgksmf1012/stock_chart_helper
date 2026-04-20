import { useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { useQueries, useQuery } from '@tanstack/react-query'
import { ArrowLeft, Database, Layers3, Loader2, Search, Star, TrendingDown, TrendingUp } from 'lucide-react'

import { AnalysisPanel } from '@/components/chart/AnalysisPanel'
import { CandleChart } from '@/components/chart/CandleChart'
import { Badge } from '@/components/ui/Badge'
import { Card } from '@/components/ui/Card'
import { QueryError } from '@/components/ui/QueryError'
import { symbolsApi } from '@/lib/api'
import { DEFAULT_TIMEFRAME, getChartLookbackDays, getContextTimeframes, TIMEFRAME_OPTIONS, timeframeLabel } from '@/lib/timeframes'
import { cn, fmtDateTime, fmtNumber, fmtPct, fmtPrice } from '@/lib/utils'
import { useAppStore } from '@/store/app'
import type { AnalysisResult } from '@/types/api'

export default function ChartPage() {
  const { symbol } = useParams<{ symbol: string }>()
  const nav = useNavigate()
  const { selectedTimeframe, setTimeframe, addToWatchlist, removeFromWatchlist, isWatched } = useAppStore()
  const timeframe = selectedTimeframe ?? DEFAULT_TIMEFRAME
  const [searchQuery, setSearchQuery] = useState('')
  const [searchResults, setSearchResults] = useState<Array<{ code: string; name: string; market: string }>>([])
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

  const handleSearch = async (query: string) => {
    setSearchQuery(query)
    if (query.trim().length < 1) {
      setSearchResults([])
      return
    }

    const results = await symbolsApi.search(query)
    setSearchResults(results)
  }

  const analysis = analysisQ.data
  const hasBars = (barsQ.data?.length ?? 0) > 0
  const isPrimaryLoading = Boolean(symbol) && !analysis && analysisQ.isLoading
  const isChartLoading = Boolean(symbol) && !hasBars && barsQ.isLoading
  const isChartError = Boolean(symbol) && !hasBars && barsQ.isError
  const contextAnalyses = contextQueries.flatMap(query => (query.data ? [query.data] : []))
  const contextSummary = summarizeContext(analysis, contextAnalyses)
  const qualityTone = (analysis?.data_quality ?? 0) >= 0.8 ? 'bullish' : (analysis?.data_quality ?? 0) >= 0.6 ? 'neutral' : 'warning'

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
            onChange={event => handleSearch(event.target.value)}
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
        <div className="rounded-xl border border-border bg-card p-4">
          <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
            <div className="space-y-2">
              <div className="flex flex-wrap items-center gap-2">
                <h1 className="text-lg font-bold">{analysis.symbol.name}</h1>
                <span className="font-mono text-sm text-muted-foreground">{symbol}</span>
                <span className="text-xs text-muted-foreground">{analysis.symbol.market}</span>
                <Badge variant={qualityTone}>{analysis.timeframe_label}</Badge>
                <Badge variant={actionPlanVariant(analysis.action_plan)}>{analysis.action_plan_label}</Badge>
                <Badge variant={scoreVariant(analysis.trade_readiness_score ?? 0)}>준비 {Math.round((analysis.trade_readiness_score ?? 0) * 100)}%</Badge>
                <Badge variant={scoreVariant(analysis.entry_window_score ?? 0)}>진입 {Math.round((analysis.entry_window_score ?? 0) * 100)}%</Badge>
                <Badge variant={scoreVariant(analysis.freshness_score ?? 0)}>신선 {Math.round((analysis.freshness_score ?? 0) * 100)}%</Badge>
                <Badge variant={scoreVariant(analysis.reentry_score ?? 0)}>재진입 {Math.round((analysis.reentry_score ?? 0) * 100)}%</Badge>
                <Badge variant={scoreVariant(analysis.active_setup_score ?? 0)}>활성 {Math.round((analysis.active_setup_score ?? 0) * 100)}%</Badge>
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
                  {watched ? '관심종목' : '추가'}
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
                <p className="text-xs text-muted-foreground/80">분봉은 데이터 상태에 따라 조금 더 오래 걸릴 수 있습니다.</p>
              </div>
            ) : isChartError ? (
              <div className="flex h-[520px] items-center justify-center p-4">
                <QueryError
                  message="차트 데이터를 불러오지 못했습니다. 분석 결과는 먼저 확인할 수 있습니다."
                  onRetry={() => barsQ.refetch()}
                />
              </div>
            ) : (
              <div className="flex h-[520px] flex-col items-center justify-center gap-2 text-sm text-muted-foreground">
                <p>표시할 차트 데이터가 아직 없습니다.</p>
                <p className="text-xs text-muted-foreground/80">분봉 데이터가 부족하거나 백그라운드 예열이 아직 끝나지 않았을 수 있습니다.</p>
              </div>
            )}
          </Card>
          {analysis ? (
            <AnalysisPanel analysis={analysis} />
          ) : (
            <Card className="flex items-center justify-center text-sm text-muted-foreground">
              분석 결과가 준비되면 이 영역에 상세 해석이 표시됩니다.
            </Card>
          )}
        </div>
      )}
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
        <div className="text-xs text-muted-foreground">불러오는 중...</div>
      </Card>
    )
  }

  if (!analysis) {
    return (
      <Card>
        <div className="text-xs text-muted-foreground">컨텍스트 데이터 없음</div>
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
          <span>상태</span>
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
  if (contexts.length === 0) return `${primary.timeframe_label} 기준 분석입니다.`

  const strongest = [...contexts].sort(
    (left, right) => (right.trade_readiness_score ?? 0) + right.p_up - ((left.trade_readiness_score ?? 0) + left.p_up),
  )[0]

  return `${primary.timeframe_label} 기준 현재 판단은 ${primary.action_plan_label}입니다. 보조 타임프레임 중에서는 ${strongest.timeframe_label}가 가장 강하며, 준비도 ${fmtPct(strongest.trade_readiness_score ?? 0, 0)} / 신선도 ${fmtPct(strongest.freshness_score ?? 0, 0)} / 재진입 ${fmtPct(strongest.reentry_score ?? 0, 0)} (${strongest.reentry_case_label || strongest.reentry_label}) 수준입니다.`
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
