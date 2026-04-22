import { useEffect, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { useMutation, useQueries, useQuery } from '@tanstack/react-query'
import {
  ArrowLeft,
  ExternalLink,
  Bookmark,
  BookOpen,
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
import { outcomesApi, symbolsApi } from '@/lib/api'
import {
  getChartLookbackDays,
  getContextTimeframes,
  TIMEFRAME_OPTIONS,
  normalizeDisplayTimeframe,
  timeframeLabel,
} from '@/lib/timeframes'
import { cn, fmtDateTime, fmtNumber, fmtPct, fmtPrice } from '@/lib/utils'
import { useAppStore } from '@/store/app'
import type { AnalysisResult, Timeframe } from '@/types/api'

export default function ChartPage() {
  const { symbol } = useParams<{ symbol: string }>()
  const nav = useNavigate()
  const { selectedTimeframe, setTimeframe, addToWatchlist, removeFromWatchlist, isWatched } = useAppStore()
  const timeframe = normalizeDisplayTimeframe(selectedTimeframe)
  const watched = symbol ? isWatched(symbol) : false
  const [searchQuery, setSearchQuery] = useState('')
  const [searchResults, setSearchResults] = useState<Array<{ code: string; name: string; market: string }>>([])
  const [savedId, setSavedId] = useState<number | null>(null)
  const searchRequestRef = useRef(0)

  const barsQ = useQuery({
    queryKey: ['bars', symbol, timeframe],
    queryFn: () => symbolsApi.getBars(symbol!, timeframe, getChartLookbackDays(timeframe)),
    enabled: !!symbol,
    staleTime: 60_000,
    retry: 1,
  })

  const analysisQ = useQuery({
    queryKey: ['analysis', symbol, timeframe],
    queryFn: () => symbolsApi.getAnalysis(symbol!, timeframe),
    enabled: !!symbol,
    staleTime: 180_000,
    retry: 1,
  })

  const priceQ = useQuery({
    queryKey: ['price', symbol],
    queryFn: () => symbolsApi.getPrice(symbol!),
    enabled: !!symbol,
    staleTime: 60_000,
    refetchInterval: 120_000,
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
  const referenceCases = buildReferenceCases(analysis, symbol, timeframe)
  const contextAnalyses = contextQueries.flatMap(query => (query.data ? [query.data] : []))
  const contextSummary = summarizeContext(analysis, contextAnalyses)
  const hasBars = (barsQ.data?.length ?? 0) > 0
  const isPrimaryLoading = Boolean(symbol) && !analysis && analysisQ.isLoading
  const isChartLoading = Boolean(symbol) && !hasBars && barsQ.isLoading
  const isChartError = Boolean(symbol) && !hasBars && barsQ.isError

  const saveMutation = useMutation({
    mutationFn: () => {
      if (!analysis) return Promise.reject(new Error('no analysis'))
      const bestPattern = analysis.patterns[0]
      return outcomesApi.record({
        symbol_code: symbol!,
        symbol_name: analysis.symbol.name,
        pattern_type: bestPattern?.pattern_type ?? 'no_pattern',
        timeframe,
        signal_date: new Date().toISOString().slice(0, 10),
        entry_price: priceQ.data?.close ?? 0,
        target_price: bestPattern?.target_level ?? null,
        stop_price: bestPattern?.invalidation_level ?? null,
        outcome: 'pending',
        p_up_at_signal: analysis.p_up,
        composite_score_at_signal: analysis.trade_readiness_score ?? 0,
        textbook_similarity_at_signal: analysis.textbook_similarity,
        trade_readiness_at_signal: analysis.trade_readiness_score ?? 0,
      })
    },
    onSuccess: result => setSavedId(result.id),
  })

  const openReferenceWindow = (focusCase?: string) => {
    const params = new URLSearchParams()
    if (symbol) params.set('symbol', symbol)
    params.set('timeframe', timeframe)
    if (analysis?.patterns[0]?.pattern_type) params.set('pattern', analysis.patterns[0].pattern_type)
    if (focusCase) params.set('case', focusCase)

    window.open(`/reference-charts?${params.toString()}`, '_blank', 'noopener,noreferrer')
  }

  return (
    <div className="space-y-5">
      <div className="flex flex-col gap-3 xl:flex-row xl:items-center xl:justify-between">
        <div className="flex items-center gap-3">
          <button onClick={() => nav('/')} className="rounded-lg border border-border bg-background/50 p-2 text-muted-foreground transition-colors hover:text-foreground">
            <ArrowLeft size={18} />
          </button>

          <div className="relative w-full max-w-md">
            <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
            <input
              className="w-full rounded-lg border border-border bg-card/80 py-2.5 pl-9 pr-3 text-sm focus:border-primary/60 focus:outline-none"
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
              <div className="absolute left-0 right-0 top-full z-50 mt-1 max-h-56 overflow-y-auto rounded-lg border border-border bg-card shadow-xl">
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
        </div>

        <div className="flex flex-wrap gap-1.5">
          {TIMEFRAME_OPTIONS.map(option => (
            <button
              key={option.value}
              onClick={() => setTimeframe(option.value)}
              className={cn(
                'rounded-lg border px-3 py-2 text-xs font-medium transition-colors',
                timeframe === option.value
                  ? 'border-primary/30 bg-primary text-primary-foreground'
                  : 'border-border bg-card/70 text-muted-foreground hover:text-foreground',
              )}
            >
              {option.label}
            </button>
          ))}
        </div>
      </div>

      {!symbol && (
        <Card className="p-6">
          <p className="text-sm text-muted-foreground">차트 분석을 시작하려면 종목을 검색하거나 대시보드에서 종목을 선택해 주세요.</p>
        </Card>
      )}

      {analysis && (
        <section className="grid gap-4 xl:grid-cols-[minmax(0,1.35fr)_360px]">
          <Card className="space-y-4 border-primary/15 bg-[linear-gradient(180deg,rgba(37,99,235,0.1),rgba(15,23,42,0.14))]">
            <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
              <div className="space-y-3">
                <div className="flex flex-wrap items-center gap-2">
                  <h1 className="text-2xl font-bold">{analysis.symbol.name}</h1>
                  <span className="font-mono text-sm text-muted-foreground">{symbol}</span>
                  <span className="text-xs text-muted-foreground">{analysis.symbol.market}</span>
                  <Badge variant="muted">{analysis.timeframe_label}</Badge>
                  <Badge variant={actionPlanVariant(analysis.action_plan)}>{analysis.action_plan_label}</Badge>
                  {analysis.is_provisional && <Badge variant="warning">임시 판단</Badge>}
                </div>

                {priceQ.data && priceQ.data.close > 0 && (
                  <div className="flex flex-wrap items-center gap-3">
                    <span className="font-mono text-2xl font-bold">{fmtPrice(priceQ.data.close)}</span>
                    <span
                      className={cn(
                        'inline-flex items-center gap-1 text-sm font-medium',
                        priceQ.data.change >= 0 ? 'text-emerald-300' : 'text-red-300',
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
                    <span className="text-xs text-muted-foreground">{priceQ.data.source === 'kis' ? '실시간 기준' : '종가 기준'}</span>
                  </div>
                )}

                <p className="max-w-3xl text-sm leading-relaxed text-muted-foreground">{analysis.action_plan_summary}</p>

                <div className="flex flex-wrap items-center gap-3 text-xs text-muted-foreground">
                  <span>분석 업데이트 {fmtDateTime(analysis.updated_at)}</span>
                  <span className="inline-flex items-center gap-1">
                    <Database size={12} />
                    {analysis.data_source}
                  </span>
                </div>
              </div>

              <div className="flex flex-wrap gap-2">
                <button
                  onClick={() => {
                    if (!symbol) return
                    if (watched) removeFromWatchlist(symbol)
                    else addToWatchlist({ code: symbol, name: analysis.symbol.name, market: analysis.symbol.market })
                  }}
                  className={cn(
                    'inline-flex items-center gap-2 rounded-lg border px-3 py-2 text-xs font-medium transition-colors',
                    watched
                      ? 'border-yellow-400/30 bg-yellow-400/15 text-yellow-400'
                      : 'border-border bg-background/60 text-muted-foreground hover:text-foreground',
                  )}
                >
                  <Star size={13} className={watched ? 'fill-yellow-400' : ''} />
                  {watched ? '관심종목 해제' : '관심종목 추가'}
                </button>
                <button
                  onClick={() => {
                    if (!analysis || savedId != null) return
                    saveMutation.mutate()
                  }}
                  disabled={savedId != null || saveMutation.isPending || !analysis}
                  className={cn(
                    'inline-flex items-center gap-2 rounded-lg border px-3 py-2 text-xs font-medium transition-colors',
                    savedId != null
                      ? 'border-primary/30 bg-primary/15 text-primary'
                      : 'border-border bg-background/60 text-muted-foreground hover:text-foreground disabled:opacity-40',
                  )}
                >
                  <Bookmark size={13} className={savedId != null ? 'fill-current' : ''} />
                  {savedId != null ? '신호 저장됨' : saveMutation.isPending ? '저장 중...' : '신호 저장'}
                </button>
              </div>
            </div>

            <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
              <HeroMetric label="상승 확률" value={fmtPct(analysis.p_up, 0)} tone="text-emerald-300" />
              <HeroMetric label="신뢰도" value={fmtPct(analysis.confidence, 0)} />
              <HeroMetric label="거래 준비도" value={fmtPct(analysis.trade_readiness_score ?? 0, 0)} />
              <HeroMetric label="진입 구간" value={fmtPct(analysis.entry_window_score ?? 0, 0)} />
            </div>

            {analysis.fetch_message && (
              <div className="rounded-lg border border-border bg-background/55 px-3 py-2 text-xs text-muted-foreground">
                {analysis.fetch_message}
              </div>
            )}
          </Card>

          <Card className="space-y-4">
            <div className="flex items-center gap-2 text-sm font-semibold">
              <ShieldAlert size={15} className="text-primary" />
              첫 화면 판단
            </div>
            <SummaryCallout
              title="지금 판단"
              body={`${analysis.action_plan_label} · ${analysis.trade_readiness_label}`}
              tone="primary"
            />
            <SummaryCallout
              title="다음 확인"
              body={analysis.next_trigger || analysis.entry_window_summary}
              tone="sky"
            />
            <SummaryCallout
              title="주의할 점"
              body={analysis.risk_flags?.[0] || analysis.no_signal_reason || analysis.freshness_summary}
              tone="amber"
            />
            <div className="rounded-lg border border-border bg-background/55 p-3 text-xs leading-relaxed text-muted-foreground">
              {contextSummary}
            </div>
          </Card>
        </section>
      )}

      {analysis && (
        <section className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_320px]">
          <Card className="space-y-3">
            <div className="flex items-center gap-2 text-sm font-semibold">
              <Layers3 size={15} className="text-primary" />
              멀티 타임프레임 컨텍스트
            </div>
            <div className="grid gap-3 md:grid-cols-3">
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

          <Card className="space-y-3">
            <div className="text-sm font-semibold">데이터 준비도</div>
            <div className="grid grid-cols-2 gap-3">
              <HeroMetric label="데이터 품질" value={fmtPct(analysis.data_quality, 0)} />
              <HeroMetric label="표본 신뢰도" value={fmtPct(analysis.sample_reliability, 0)} />
              <HeroMetric label="사용 바 수" value={`${analysis.available_bars.toLocaleString('ko-KR')}개`} />
              <HeroMetric label="시가총액" value={analysis.symbol.market_cap ? fmtNumber(analysis.symbol.market_cap) : '-'} />
            </div>
            <div className="rounded-lg border border-border bg-background/55 p-3 text-xs leading-relaxed text-muted-foreground">
              {buildDataReadinessSummary(analysis, timeframe)}
            </div>
          </Card>
        </section>
      )}

      {analysis && (
        <section className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_320px]">
          <Card className="space-y-4">
            <div className="flex items-center gap-2 text-sm font-semibold">
              <BookOpen size={15} className="text-primary" />
              과거 레퍼런스 비교
            </div>
            <p className="text-sm leading-relaxed text-muted-foreground">
              지금 보고 있는 차트와 닮은 과거 시나리오를 새 창으로 띄워 비교할 수 있게 묶어뒀습니다. 패턴 자체만 보는 용도보다, 어디서 쉬고 어디를 넘지 못했는지까지 함께 보는 데 초점을 맞췄습니다.
            </p>
            <div className="grid gap-3 md:grid-cols-3">
              {referenceCases.map(referenceCase => (
                <button
                  key={referenceCase.key}
                  onClick={() => openReferenceWindow(referenceCase.key)}
                  className="rounded-lg border border-border bg-background/55 p-4 text-left transition-colors hover:border-primary/35 hover:bg-background/70"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <div className="text-sm font-semibold text-foreground">{referenceCase.title}</div>
                      <div className="mt-1 text-xs text-primary">{referenceCase.tag}</div>
                    </div>
                    <ExternalLink size={14} className="mt-0.5 text-muted-foreground" />
                  </div>
                  <p className="mt-3 text-xs leading-relaxed text-muted-foreground">{referenceCase.summary}</p>
                  <div className="mt-3 text-[11px] text-muted-foreground/80">{referenceCase.focus}</div>
                </button>
              ))}
            </div>
          </Card>

          <Card className="space-y-3">
            <div className="text-sm font-semibold">읽는 포인트</div>
            <SummaryCallout
              title="구름대 체크"
              body="윗꼬리만 치는지, 구름 상단을 딛고 눌림을 만드는지부터 먼저 확인합니다."
              tone="sky"
            />
            <SummaryCallout
              title="전고점 계단"
              body="직전 고점만 넘겼는지, 그 이전 고점까지 같이 정리했는지 구간별로 나눠 봅니다."
              tone="primary"
            />
            <SummaryCallout
              title="비교 창 활용"
              body="새 창은 현재 차트 옆에 띄워두고 neckline, cloud, 눌림 위치를 나란히 비교하는 용도로 쓰면 좋습니다."
              tone="amber"
            />
          </Card>
        </section>
      )}

      {isPrimaryLoading && (
        <Card className="flex items-center gap-2 p-4 text-sm text-muted-foreground">
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
        <section className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_360px]">
          <Card className="space-y-3 overflow-hidden">
            <div className="flex items-start justify-between gap-3 border-b border-border/70 px-4 py-3">
              <div>
                <div className="text-sm font-semibold">차트</div>
                <p className="mt-1 text-xs text-muted-foreground">첫 화면에서는 차트와 일목 구름대를 먼저 보고, 자세한 해석은 오른쪽 탭에서 확인합니다.</p>
              </div>
              <button
                onClick={() => openReferenceWindow()}
                className="inline-flex items-center gap-1.5 rounded-lg border border-border bg-background/60 px-3 py-2 text-xs text-muted-foreground transition-colors hover:text-foreground"
              >
                <ExternalLink size={13} />
                레퍼런스 창
              </button>
            </div>
            <div className="p-4 pt-0">
              {hasBars && barsQ.data ? (
                <CandleChart bars={barsQ.data} analysis={analysis} height={560} />
              ) : isChartLoading ? (
                <div className="flex h-[560px] flex-col items-center justify-center gap-2 text-sm text-muted-foreground">
                  <Loader2 size={18} className="animate-spin" />
                  <p>차트를 불러오는 중입니다.</p>
                  <p className="max-w-sm text-center text-xs text-muted-foreground/80">
                    분봉은 예열 상황에 따라 조금 더 걸릴 수 있습니다.
                  </p>
                </div>
              ) : isChartError ? (
                <div className="flex h-[560px] items-center justify-center p-4">
                  <QueryError message="차트 데이터를 불러오지 못했습니다." onRetry={() => barsQ.refetch()} />
                </div>
              ) : (
                <EmptyChartState
                  analysis={analysis ?? null}
                  timeframe={timeframe}
                  onRetry={() => barsQ.refetch()}
                  onFallbackDaily={() => setTimeframe('1d')}
                />
              )}
            </div>
          </Card>

          {analysis ? (
            <AnalysisPanel analysis={analysis} symbol={symbol} timeframe={timeframe} />
          ) : (
            <Card className="flex items-center justify-center text-sm text-muted-foreground">
              분석 결과가 준비되면 오른쪽에 해석이 표시됩니다.
            </Card>
          )}
        </section>
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
    (isIntraday ? '분봉 데이터가 아직 준비되지 않았습니다.' : '차트 데이터가 아직 준비되지 않았습니다.')
  const body =
    analysis?.fetch_message ||
    (isIntraday
      ? '장중 분봉 데이터가 부족하거나 백그라운드 예열이 아직 끝나지 않았습니다.'
      : '데이터 공급 상태에 따라 일시적으로 차트가 비어 있을 수 있습니다.')

  return (
    <div className="flex h-[560px] flex-col items-center justify-center gap-2 px-6 text-sm text-muted-foreground">
      <p className="font-medium text-foreground">{title}</p>
      <p className="max-w-md text-center text-xs text-muted-foreground/80">{body}</p>
      <div className="flex flex-wrap justify-center gap-2 pt-1">
        <button
          onClick={onRetry}
          className="rounded-lg border border-border bg-card px-3 py-2 text-xs text-muted-foreground transition-colors hover:text-foreground"
        >
          다시 시도
        </button>
        {isIntraday && (
          <button
            onClick={onFallbackDaily}
            className="rounded-lg border border-sky-500/30 bg-sky-500/10 px-3 py-2 text-xs text-sky-100 transition-colors hover:bg-sky-500/15"
          >
            일봉 먼저 보기
          </button>
        )}
      </div>
    </div>
  )
}

function SummaryCallout({
  title,
  body,
  tone,
}: {
  title: string
  body: string
  tone: 'primary' | 'sky' | 'amber'
}) {
  const toneClass = {
    primary: 'border-primary/20 bg-primary/6',
    sky: 'border-sky-400/20 bg-sky-400/6',
    amber: 'border-amber-400/20 bg-amber-400/6',
  }[tone]

  return (
    <div className={cn('rounded-lg border p-3', toneClass)}>
      <div className="text-xs font-medium text-muted-foreground">{title}</div>
      <div className="mt-1 text-sm font-medium leading-relaxed text-foreground">{body}</div>
    </div>
  )
}

function HeroMetric({ label, value, tone }: { label: string; value: string; tone?: string }) {
  return (
    <div className="rounded-lg border border-border bg-background/55 p-3">
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className={cn('mt-1 text-sm font-semibold', tone)}>{value}</div>
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
    return <Card className="text-xs text-muted-foreground">불러오는 중입니다...</Card>
  }

  if (!analysis) {
    return <Card className="text-xs text-muted-foreground">컨텍스트 데이터가 아직 없습니다.</Card>
  }

  return (
    <Card className={isPrimary ? 'border-primary/40' : undefined}>
      <div className="flex items-center justify-between gap-2">
        <div className="text-sm font-semibold">{labelOverride ?? analysis.timeframe_label}</div>
        {isPrimary && <Badge variant="default">현재</Badge>}
      </div>
      <div className="mt-3 grid gap-2 text-xs text-muted-foreground">
        <MetricLine label="상승 확률" value={fmtPct(analysis.p_up, 0)} />
        <MetricLine label="준비도" value={fmtPct(analysis.trade_readiness_score ?? 0, 0)} />
        <MetricLine label="신선도" value={fmtPct(analysis.freshness_score ?? 0, 0)} />
        <MetricLine label="재진입 구조" value={fmtPct(analysis.reentry_score ?? 0, 0)} />
        <MetricLine label="행동 가이드" value={analysis.action_plan_label} />
      </div>
    </Card>
  )
}

function MetricLine({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-3">
      <span>{label}</span>
      <span className="text-foreground">{value}</span>
    </div>
  )
}

function summarizeContext(primary: AnalysisResult | undefined, contexts: AnalysisResult[]): string {
  if (!primary) return '현재 분석 결과가 아직 없습니다.'
  if (contexts.length === 0) return `${primary.timeframe_label} 기준 단일 분석만 준비된 상태입니다.`

  const strongest = [...contexts].sort(
    (left, right) => (right.trade_readiness_score ?? 0) + right.p_up - ((left.trade_readiness_score ?? 0) + left.p_up),
  )[0]

  return `${primary.timeframe_label} 기준 현재 판단은 ${primary.action_plan_label}입니다. 보조 타임프레임 중에서는 ${strongest.timeframe_label} 쪽이 가장 강하며 준비도 ${fmtPct(strongest.trade_readiness_score ?? 0, 0)}, 신선도 ${fmtPct(strongest.freshness_score ?? 0, 0)}로 읽힙니다.`
}

function buildDataReadinessSummary(analysis: AnalysisResult, timeframe: Timeframe): string {
  if (analysis.is_provisional) {
    return `현재 ${timeframeLabel(timeframe)} 분석은 임시 결과일 수 있습니다. 데이터가 더 쌓이면 점수와 해석이 조정될 수 있습니다.`
  }
  if ((analysis.available_bars ?? 0) < minimumBarsForTimeframe(timeframe)) {
    return `${timeframeLabel(timeframe)} 기준으로는 아직 바 수가 적어 구조 해석을 보수적으로 보는 편이 좋습니다.`
  }
  if ((analysis.data_quality ?? 0) < 0.6) {
    return '데이터 품질이 낮아 지금 점수를 확정값처럼 보기 어렵습니다. 분봉이 더 쌓인 뒤 다시 보는 편이 안전합니다.'
  }
  if ((analysis.sample_reliability ?? 0) < 0.45) {
    return '유사 패턴 표본 신뢰도가 낮아 숫자보다 구조와 리스크 관리 비중을 더 높게 두는 편이 좋습니다.'
  }
  return '현재 타임프레임 기준으로 데이터 품질과 표본 신뢰도는 무난한 편입니다. 숫자와 패턴 해석을 함께 봐도 됩니다.'
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

function actionPlanVariant(plan: string): 'bullish' | 'warning' | 'muted' | 'neutral' {
  if (plan === 'ready_now') return 'bullish'
  if (plan === 'watch') return 'neutral'
  if (plan === 'recheck') return 'warning'
  return 'muted'
}

function buildReferenceCases(
  analysis: AnalysisResult | undefined,
  symbol: string | undefined,
  timeframe: Timeframe,
) {
  const patternType = analysis?.patterns[0]?.pattern_type ?? 'double_bottom'
  const symbolLabel = analysis?.symbol.name ?? symbol ?? '현재 종목'
  const timeframeText = timeframeLabel(timeframe)

  return [
    {
      key: 'double-bottom-breakout',
      title: '쌍바닥 돌파 상승',
      tag: '정석 breakout',
      summary: `${symbolLabel}의 ${timeframeText} 구조와 비교하기 좋은 기본 레퍼런스입니다. neckline 돌파 뒤 눌림이 짧고, 이전 공급대까지 한 번에 정리하는 흐름을 보여줍니다.`,
      focus: '체크 포인트: neckline 안착 -> 이전 고점 정리 -> 거래량 유지',
    },
    {
      key: 'double-bottom-partial-breakout',
      title: '직전 고점만 넘긴 케이스',
      tag: 'partial breakout',
      summary: `${symbolLabel}처럼 위쪽 매물대가 남아 있을 때 참고하기 좋은 유형입니다. 바로 앞 고점은 넘지만 전전 고점에서 다시 쉬거나 되밀리는 흐름을 비교할 수 있습니다.`,
      focus: '체크 포인트: 1차 전고점 돌파 성공, 2차 전고점 저항 확인',
    },
    {
      key: patternType === 'double_bottom' ? 'double-bottom-cloud-support' : 'cloud-support-relaunch',
      title: '구름대 상단 지지 후 재출발',
      tag: 'Ichimoku pullback',
      summary: '228,500원처럼 바로 못 넘는 가격대가 있을 때, 구름 상단까지 쉬었다가 지지받고 다시 가는 상황을 따로 비교할 수 있게 준비했습니다.',
      focus: '체크 포인트: 구름 상단 터치 -> 지지 확인 -> 재가속',
    },
  ]
}
