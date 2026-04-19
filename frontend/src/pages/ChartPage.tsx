import { useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { useQueries, useQuery } from '@tanstack/react-query'
import { ArrowLeft, Database, Layers3, Loader2, Search, Star, TrendingDown, TrendingUp } from 'lucide-react'

import { AnalysisPanel } from '@/components/chart/AnalysisPanel'
import { CandleChart } from '@/components/chart/CandleChart'
import { Badge } from '@/components/ui/Badge'
import { Card } from '@/components/ui/Card'
import { symbolsApi } from '@/lib/api'
import {
  DEFAULT_TIMEFRAME,
  getChartLookbackDays,
  getContextTimeframes,
  TIMEFRAME_OPTIONS,
  timeframeLabel,
} from '@/lib/timeframes'
import { cn, fmtDateTime, fmtNumber, fmtPct, fmtPrice, PATTERN_NAMES, STATE_COLORS, STATE_LABELS } from '@/lib/utils'
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
  })

  const analysisQ = useQuery({
    queryKey: ['analysis', symbol, timeframe],
    queryFn: () => symbolsApi.getAnalysis(symbol!, timeframe),
    enabled: !!symbol,
    staleTime: 180_000,
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
  const qualityTone =
    (analysis?.data_quality ?? 0) >= 0.8 ? 'bullish' : (analysis?.data_quality ?? 0) >= 0.6 ? 'muted' : 'warning'
  const contextAnalyses = contextQueries.flatMap(query => (query.data ? [query.data] : []))
  const contextSummary = summarizeContext(analysis, contextAnalyses)

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
              className={`rounded-md px-2.5 py-1.5 text-xs transition-colors ${
                timeframe === option.value
                  ? 'bg-primary text-primary-foreground'
                  : 'border border-border bg-card text-muted-foreground hover:text-foreground'
              }`}
            >
              {option.label}
            </button>
          ))}
        </div>
      </div>

      {analysis && (
        <div className="rounded-xl border border-border bg-card p-4">
          <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
            <div className="space-y-1">
              <div className="flex flex-wrap items-center gap-2">
                <h1 className="text-lg font-bold">{analysis.symbol.name}</h1>
                <span className="font-mono text-sm text-muted-foreground">{symbol}</span>
                <span className="text-xs text-muted-foreground">{analysis.symbol.market}</span>
                <Badge variant={qualityTone}>{analysis.timeframe_label}</Badge>
                <Badge variant={actionPlanVariant(analysis.action_plan)}>{analysis.action_plan_label}</Badge>
                <Badge variant={readinessVariant(analysis.trade_readiness_score ?? 0)}>
                  준비도 {Math.round((analysis.trade_readiness_score ?? 0) * 100)}%
                </Badge>
                <Badge variant={(analysis.active_setup_score ?? 0) >= 0.56 ? 'neutral' : 'muted'}>
                  활성 {Math.round((analysis.active_setup_score ?? 0) * 100)}%
                </Badge>
                <Badge variant={qualityTone}>품질 {Math.round(analysis.data_quality * 100)}%</Badge>
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
                  {watched ? '관심 종목' : '추가'}
                </button>
              </div>

              {priceQ.data && priceQ.data.close > 0 && (
                <div className="flex items-center gap-3">
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
                  <span className="text-xs text-muted-foreground">
                    {priceQ.data.source === 'kis' ? '실시간' : '종가 기준'}
                  </span>
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

            <div className="grid grid-cols-2 gap-3 text-right sm:grid-cols-6">
              <MetricCell label="상승 확률" value={`${(analysis.p_up * 100).toFixed(0)}%`} tone="text-green-400" />
              <MetricCell label="하락 확률" value={`${(analysis.p_down * 100).toFixed(0)}%`} tone="text-red-400" />
              <MetricCell label="신뢰도" value={`${(analysis.confidence * 100).toFixed(0)}%`} />
              <MetricCell label="준비도" value={`${Math.round((analysis.trade_readiness_score ?? 0) * 100)}%`} />
              <MetricCell label="활성 셋업" value={`${Math.round((analysis.active_setup_score ?? 0) * 100)}%`} />
              <MetricCell label="시총" value={analysis.symbol.market_cap ? `${fmtNumber(analysis.symbol.market_cap)}억` : '-'} />
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

      {!symbol ? (
        <div className="flex h-80 flex-col items-center justify-center gap-3 text-muted-foreground">
          <Search size={40} className="opacity-20" />
          <p className="text-sm">검색창에서 종목을 선택하면 차트 분석을 시작합니다.</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4 xl:grid-cols-[1fr_340px]">
          <div>
            {barsQ.isLoading ? (
              <div className="flex h-96 items-center justify-center rounded-lg bg-card">
                <Loader2 size={24} className="animate-spin text-muted-foreground" />
              </div>
            ) : barsQ.data && barsQ.data.length > 0 ? (
              <CandleChart bars={barsQ.data} analysis={analysis ?? null} height={480} />
            ) : (
              <div className="flex h-96 items-center justify-center rounded-lg bg-card px-6 text-center text-sm text-muted-foreground">
                {analysis?.fetch_message || '차트 데이터를 불러오지 못했습니다. 잠시 후 다시 시도하거나 다른 타임프레임을 확인해 주세요.'}
              </div>
            )}
          </div>

          <div>
            {analysisQ.isLoading ? (
              <div className="flex h-40 items-center justify-center">
                <Loader2 size={20} className="animate-spin text-muted-foreground" />
              </div>
            ) : analysis ? (
              <AnalysisPanel analysis={analysis} />
            ) : (
              <div className="rounded-lg border border-border bg-card p-4 text-sm text-muted-foreground">
                분석 결과를 불러오지 못했습니다.
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

function MetricCell({ label, value, tone }: { label: string; value: string; tone?: string }) {
  return (
    <div className="rounded-lg border border-border bg-background/60 p-3">
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className={`mt-1 text-sm font-semibold ${tone ?? 'text-foreground'}`}>{value}</div>
    </div>
  )
}

function actionPlanVariant(plan: string): 'bullish' | 'warning' | 'muted' | 'neutral' {
  if (plan === 'ready_now') return 'bullish'
  if (plan === 'watch') return 'neutral'
  if (plan === 'recheck') return 'warning'
  return 'muted'
}

function readinessVariant(score: number): 'bullish' | 'warning' | 'muted' | 'neutral' {
  if (score >= 0.72) return 'bullish'
  if (score >= 0.58) return 'neutral'
  if (score >= 0.44) return 'warning'
  return 'muted'
}

function ContextCard({
  analysis,
  isLoading,
  isPrimary = false,
  labelOverride,
}: {
  analysis: AnalysisResult | null
  isLoading?: boolean
  isPrimary?: boolean
  labelOverride?: string
}) {
  if (isLoading) {
    return (
      <div className="rounded-lg border border-border bg-background/60 p-3">
        <div className="flex items-center justify-center py-6 text-muted-foreground">
          <Loader2 size={16} className="animate-spin" />
        </div>
      </div>
    )
  }

  if (!analysis) {
    return (
      <div className="rounded-lg border border-border bg-background/60 p-3">
        <div className="text-xs text-muted-foreground">{labelOverride ?? '-'}</div>
        <div className="mt-2 text-xs text-muted-foreground">분석 결과 없음</div>
      </div>
    )
  }

  const best = analysis.patterns[0]
  const qualityVariant = analysis.data_quality >= 0.8 ? 'bullish' : analysis.data_quality >= 0.6 ? 'muted' : 'warning'

  return (
    <div className={`rounded-lg border bg-background/60 p-3 ${isPrimary ? 'border-primary/40' : 'border-border'}`}>
      <div className="flex items-center justify-between gap-2">
        <div className="text-xs font-semibold">{labelOverride ?? analysis.timeframe_label}</div>
        <Badge variant={qualityVariant}>품질 {Math.round(analysis.data_quality * 100)}%</Badge>
      </div>

      <div className="mt-2 flex items-center justify-between">
        <div className="text-sm font-semibold">{Math.round(analysis.p_up * 100)}%</div>
        <div className="text-xs text-muted-foreground">상승 확률</div>
      </div>

      {best ? (
        <div className="mt-2 space-y-1">
          <div className="text-xs text-muted-foreground">{PATTERN_NAMES[best.pattern_type] ?? best.pattern_type}</div>
          <div className="flex items-center gap-2">
            <span className={cn('rounded px-1.5 py-0.5 text-xs', STATE_COLORS[best.state])}>
              {STATE_LABELS[best.state]}
            </span>
            <span className="text-xs text-muted-foreground">유사도 {fmtPct(best.textbook_similarity)}</span>
          </div>
        </div>
      ) : (
        <div className="mt-2 text-xs text-muted-foreground">유의미한 패턴 없음</div>
      )}

      <div className="mt-3 grid grid-cols-2 gap-2 text-xs text-muted-foreground">
        <span>신뢰도 {fmtPct(analysis.confidence)}</span>
        <span className="text-right">신선도 {fmtPct(analysis.recency_score)}</span>
      </div>
    </div>
  )
}

function summarizeContext(primary: AnalysisResult | undefined, contexts: AnalysisResult[]): string {
  if (!primary) return '현재 타임프레임 기준 분석을 불러오는 중입니다.'

  const primaryBias = primary.p_up - primary.p_down
  const aligned = contexts.filter(context => (context.p_up - context.p_down) * primaryBias > 0.02).length
  const opposite = contexts.filter(context => (context.p_up - context.p_down) * primaryBias < -0.02).length

  if (contexts.length === 0) {
    return `${primary.timeframe_label} 단독 신호 기준으로 해석하고 있습니다.`
  }

  if (aligned === contexts.length) {
    return `${primary.timeframe_label} 신호가 주변 타임프레임과 같은 방향으로 정렬돼 있어 추세 추종 관점으로 보기 좋습니다.`
  }

  if (opposite > 0) {
    return `${primary.timeframe_label} 신호는 있지만 상위 또는 하위 축이 엇갈립니다. 무조건 추격하기보다 지지와 무효화 기준을 함께 보는 편이 좋습니다.`
  }

  return `${primary.timeframe_label} 신호는 유효하지만 주변 타임프레임은 일부만 동조하고 있습니다. 보수적으로 확인하는 편이 좋습니다.`
}
