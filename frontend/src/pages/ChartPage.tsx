import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { useMutation, useQueries, useQuery } from '@tanstack/react-query'
import {
  ArrowLeft,
  ExternalLink,
  Bookmark,
  BookOpen,
  CheckCircle2,
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
import { outcomesApi, patternsApi, symbolsApi } from '@/lib/api'
import {
  getChartLookbackDays,
  getContextTimeframes,
  TIMEFRAME_OPTIONS,
  normalizeDisplayTimeframe,
  timeframeLabel,
} from '@/lib/timeframes'
import { cn, fmtDateTime, fmtNumber, fmtPct, fmtPrice, PATTERN_NAMES } from '@/lib/utils'
import { useAppStore } from '@/store/app'
import type { AnalysisResult, OutcomeIntent, OutcomeRecord, OutcomeStatus, PatternInfo, PatternStatsEntry, Timeframe } from '@/types/api'

export default function ChartPage() {
  const { symbol } = useParams<{ symbol: string }>()
  const nav = useNavigate()
  const { selectedTimeframe, setTimeframe, addToWatchlist, removeFromWatchlist, isWatched } = useAppStore()
  const timeframe = normalizeDisplayTimeframe(selectedTimeframe)
  const watched = symbol ? isWatched(symbol) : false
  const [searchQuery, setSearchQuery] = useState('')
  const [searchResults, setSearchResults] = useState<Array<{ code: string; name: string; market: string }>>([])
  const [savedId, setSavedId] = useState<number | null>(null)
  const [selectedIntent, setSelectedIntent] = useState<OutcomeIntent>('breakout_wait')
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
  const primaryPattern = useMemo(() => getPrimaryPattern(analysis), [analysis])
  const patternStatsQ = useQuery({
    queryKey: ['patterns', 'stats', 'chart-summary'],
    queryFn: patternsApi.stats,
    enabled: Boolean(primaryPattern),
    staleTime: 300_000,
  })
  const activePatternStats = useMemo(
    () => getPatternStats(patternStatsQ.data?.items ?? [], primaryPattern, timeframe),
    [patternStatsQ.data?.items, primaryPattern, timeframe],
  )
  const outcomesQ = useQuery({
    queryKey: ['outcomes', 'chart', symbol],
    queryFn: outcomesApi.list,
    enabled: !!symbol,
    staleTime: 45_000,
  })
  const chartOutcomeRecords = useMemo(
    () =>
      (outcomesQ.data ?? []).filter(
        record => record.symbol_code === symbol && record.timeframe === timeframe,
      ),
    [outcomesQ.data, symbol, timeframe],
  )
  const savedRecord = useMemo(
    () =>
      chartOutcomeRecords.find(
        record =>
          record.outcome === 'pending' &&
          record.pattern_type === (primaryPattern?.pattern_type ?? 'no_pattern'),
      ) ?? null,
    [chartOutcomeRecords, primaryPattern?.pattern_type],
  )
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
        intent: selectedIntent,
        outcome: 'pending',
        notes: `intent:${selectedIntent}`,
        p_up_at_signal: analysis.p_up,
        composite_score_at_signal: analysis.trade_readiness_score ?? 0,
        textbook_similarity_at_signal: analysis.textbook_similarity,
        trade_readiness_at_signal: analysis.trade_readiness_score ?? 0,
      })
    },
    onSuccess: result => {
      setSavedId(result.id)
      outcomesQ.refetch()
    },
  })

  const updateOutcomeMutation = useMutation({
    mutationFn: ({ id, outcome }: { id: number; outcome: OutcomeStatus }) =>
      outcomesApi.update(id, {
        outcome,
        exit_price: priceQ.data?.close,
        exit_date: new Date().toISOString().slice(0, 10),
      }),
    onSuccess: () => outcomesQ.refetch(),
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
                    if (!analysis || savedId != null || savedRecord) return
                    saveMutation.mutate()
                  }}
                  disabled={savedId != null || Boolean(savedRecord) || saveMutation.isPending || !analysis}
                  className={cn(
                    'inline-flex items-center gap-2 rounded-lg border px-3 py-2 text-xs font-medium transition-colors',
                    savedId != null || savedRecord
                      ? 'border-primary/30 bg-primary/15 text-primary'
                      : 'border-border bg-background/60 text-muted-foreground hover:text-foreground disabled:opacity-40',
                  )}
                >
                  <Bookmark size={13} className={savedId != null || savedRecord ? 'fill-current' : ''} />
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

            <div className="rounded-lg border border-border bg-background/55 p-3">
              <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
                <div>
                  <div className="text-sm font-semibold">판단 저장 방식</div>
                  <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
                    저장할 때 의도를 남겨두면 나중에 어떤 상황에서 강했고 약했는지 더 정확히 쌓입니다.
                  </p>
                </div>
                <div className="text-xs text-muted-foreground">
                  {savedRecord
                    ? `저장된 분류: ${OUTCOME_INTENT_LABELS[(savedRecord.intent as OutcomeIntent) ?? 'breakout_wait'] ?? '돌파 대기'}`
                    : OUTCOME_INTENT_DESCRIPTIONS[selectedIntent]}
                </div>
              </div>

              <div className="mt-3 flex flex-wrap gap-2">
                {OUTCOME_INTENT_OPTIONS.map(option => (
                  <button
                    key={option.value}
                    onClick={() => setSelectedIntent(option.value)}
                    disabled={savedId != null || Boolean(savedRecord)}
                    className={cn(
                      'rounded-lg border px-3 py-2 text-xs transition-colors disabled:cursor-not-allowed disabled:opacity-50',
                      selectedIntent === option.value
                        ? 'border-primary/30 bg-primary/15 text-primary'
                        : 'border-border bg-card/65 text-muted-foreground hover:text-foreground',
                    )}
                  >
                    {option.label}
                  </button>
                ))}
              </div>
            </div>

            <PriceActionBar analysis={analysis} currentPrice={priceQ.data?.close ?? null} pattern={primaryPattern} stats={activePatternStats} />

            <DecisionJournalCard
              records={chartOutcomeRecords}
              isLoading={outcomesQ.isLoading}
              isUpdating={updateOutcomeMutation.isPending}
              onUpdate={(id, outcome) => updateOutcomeMutation.mutate({ id, outcome })}
            />

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

const CHART_OUTCOME_LABELS: Record<OutcomeStatus, string> = {
  pending: '대기',
  win: '성공',
  loss: '실패',
  stopped_out: '손절',
  cancelled: '취소',
}

const CHART_OUTCOME_TONES: Record<OutcomeStatus, string> = {
  pending: 'border-sky-400/25 bg-sky-400/10 text-sky-100',
  win: 'border-emerald-400/25 bg-emerald-400/10 text-emerald-100',
  loss: 'border-red-400/25 bg-red-400/10 text-red-100',
  stopped_out: 'border-amber-400/25 bg-amber-400/10 text-amber-100',
  cancelled: 'border-border bg-background/70 text-muted-foreground',
}

const OUTCOME_INTENT_OPTIONS: Array<{ value: OutcomeIntent; label: string }> = [
  { value: 'observe', label: '관망' },
  { value: 'breakout_wait', label: '돌파 대기' },
  { value: 'pullback_candidate', label: '눌림 매수 후보' },
  { value: 'invalidation_watch', label: '무효화 감시' },
]

const OUTCOME_INTENT_LABELS: Record<OutcomeIntent, string> = {
  observe: '관망',
  breakout_wait: '돌파 대기',
  pullback_candidate: '눌림 매수 후보',
  invalidation_watch: '무효화 감시',
}

const OUTCOME_INTENT_DESCRIPTIONS: Record<OutcomeIntent, string> = {
  observe: '아직 진입보다 구조 관찰이 먼저인 경우에 남겨두는 기록입니다.',
  breakout_wait: '트리거 돌파가 확인될 때 대응하려는 시나리오입니다.',
  pullback_candidate: '돌파 후 눌림이나 구름대 지지 구간을 노리는 시나리오입니다.',
  invalidation_watch: '무효화선 이탈 여부를 먼저 확인하려는 방어적 시나리오입니다.',
}

function PriceActionBar({
  analysis,
  currentPrice,
  pattern,
  stats,
}: {
  analysis: AnalysisResult
  currentPrice: number | null
  pattern: PatternInfo | null
  stats: PatternStatsEntry | null
}) {
  const trigger = pattern?.neckline ?? null
  const invalidation = pattern?.invalidation_level ?? null
  const target = pattern?.target_level ?? null
  const patternName = pattern?.pattern_type ? PATTERN_NAMES[pattern.pattern_type] ?? pattern.pattern_type : '패턴 없음'

  return (
    <div className="rounded-lg border border-primary/20 bg-background/60 p-3">
      <div className="mb-3 flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between">
        <div className="text-sm font-semibold">핵심 가격 바</div>
        <div className="text-xs text-muted-foreground">{patternName} 기준으로 먼저 볼 가격대입니다.</div>
      </div>
      <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-5">
        <PriceLevel label="현재가" value={currentPrice} hint={pricePositionHint(currentPrice, trigger, invalidation)} tone="primary" />
        <PriceLevel label="트리거" value={trigger} hint={analysis.next_trigger || analysis.entry_window_summary} tone="sky" />
        <PriceLevel label="무효화" value={invalidation} hint={invalidation ? '이 가격 하회 시 시나리오 재검토' : analysis.risk_flags?.[0]} tone="amber" />
        <PriceLevel label="목표가" value={target} hint={target ? '도달 시 분할 대응 기준' : analysis.projection_label} tone="emerald" />
        <div className="rounded-lg border border-border bg-card/65 p-3">
          <div className="text-xs text-muted-foreground">과거 성과</div>
          <div className="mt-1 text-sm font-semibold text-foreground">{stats ? fmtPct(stats.win_rate, 0) : fmtPct(analysis.empirical_win_rate ?? 0, 0)}</div>
          <div className="mt-1 line-clamp-2 text-[11px] leading-relaxed text-muted-foreground">
            {stats ? `표본 ${stats.sample_size}건, 평균 ${stats.avg_bars_to_outcome.toFixed(1)}봉` : `표본 ${analysis.sample_size}건 기준`}
          </div>
        </div>
      </div>
    </div>
  )
}

function DecisionJournalCard({
  records,
  isLoading,
  isUpdating,
  onUpdate,
}: {
  records: OutcomeRecord[]
  isLoading: boolean
  isUpdating: boolean
  onUpdate: (id: number, outcome: OutcomeStatus) => void
}) {
  const pending = records.filter(record => record.outcome === 'pending')
  const completed = records.filter(record => record.outcome !== 'pending')
  const latest = [...records].sort((left, right) => String(right.recorded_at ?? '').localeCompare(String(left.recorded_at ?? ''))).slice(0, 4)

  return (
    <div className="rounded-lg border border-border bg-background/60 p-3">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <div className="flex items-center gap-2 text-sm font-semibold">
            <CheckCircle2 size={14} className="text-primary" />
            내 판단 기록
          </div>
          <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
            이 종목에서 남긴 판단을 같은 화면에서 닫아야 나중에 내 승률과 패턴별 성과가 쌓입니다.
          </p>
        </div>
        <div className="flex gap-2 text-[11px] text-muted-foreground">
          <span className="rounded-md border border-border bg-card/65 px-2 py-1">대기 {pending.length}</span>
          <span className="rounded-md border border-border bg-card/65 px-2 py-1">종료 {completed.length}</span>
        </div>
      </div>

      {isLoading ? (
        <div className="mt-3 flex items-center gap-2 rounded-lg border border-border bg-card/55 p-3 text-xs text-muted-foreground">
          <Loader2 size={13} className="animate-spin" />
          판단 기록을 불러오는 중입니다.
        </div>
      ) : latest.length === 0 ? (
        <div className="mt-3 rounded-lg border border-border bg-card/55 p-3 text-xs leading-relaxed text-muted-foreground">
          아직 이 종목의 기록이 없습니다. 위의 판단 저장 버튼으로 오늘 시나리오를 남겨두세요.
        </div>
      ) : (
        <div className="mt-3 space-y-2">
          {latest.map(record => (
            <div key={record.id ?? `${record.signal_date}-${record.pattern_type}`} className="rounded-lg border border-border bg-card/55 p-3">
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-1.5">
                    <span className={cn('rounded-md border px-1.5 py-0.5 text-[11px]', CHART_OUTCOME_TONES[record.outcome] ?? CHART_OUTCOME_TONES.pending)}>
                      {CHART_OUTCOME_LABELS[record.outcome] ?? record.outcome}
                    </span>
                    <span className="text-xs font-medium text-foreground">{PATTERN_NAMES[record.pattern_type] ?? record.pattern_type}</span>
                    <span className="font-mono text-[11px] text-muted-foreground">{record.signal_date}</span>
                  </div>
                  <div className="mt-2 flex flex-wrap gap-3 text-[11px] text-muted-foreground">
                    <span>분류 {OUTCOME_INTENT_LABELS[(record.intent as OutcomeIntent) ?? 'breakout_wait'] ?? '돌파 대기'}</span>
                    <span>진입 {formatOutcomePrice(record.entry_price)}</span>
                    {record.target_price != null && <span>목표 {formatOutcomePrice(record.target_price)}</span>}
                    {record.stop_price != null && <span>무효화 {formatOutcomePrice(record.stop_price)}</span>}
                    {record.p_up_at_signal != null && <span>상승 {fmtPct(record.p_up_at_signal, 0)}</span>}
                  </div>
                </div>

                {record.outcome === 'pending' && record.id != null && (
                  <div className="flex shrink-0 flex-wrap justify-end gap-1">
                    {(['win', 'loss', 'stopped_out', 'cancelled'] as OutcomeStatus[]).map(outcome => (
                      <button
                        key={outcome}
                        onClick={() => onUpdate(record.id!, outcome)}
                        disabled={isUpdating}
                        className={cn(
                          'rounded-md border px-2 py-1 text-[11px] transition-colors disabled:cursor-not-allowed disabled:opacity-50',
                          CHART_OUTCOME_TONES[outcome],
                        )}
                      >
                        {CHART_OUTCOME_LABELS[outcome]}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function formatOutcomePrice(value: number | null | undefined) {
  return value != null && value > 0 ? fmtPrice(value) : '-'
}

function PriceLevel({
  label,
  value,
  hint,
  tone,
}: {
  label: string
  value: number | null
  hint?: string | null
  tone: 'primary' | 'sky' | 'amber' | 'emerald'
}) {
  const toneClass = {
    primary: 'text-primary',
    sky: 'text-sky-200',
    amber: 'text-amber-200',
    emerald: 'text-emerald-200',
  }[tone]

  return (
    <div className="rounded-lg border border-border bg-card/65 p-3">
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className={cn('mt-1 font-mono text-sm font-semibold', toneClass)}>{value && value > 0 ? fmtPrice(value) : '-'}</div>
      <div className="mt-1 line-clamp-2 text-[11px] leading-relaxed text-muted-foreground">{hint || '조건이 준비되면 자동 표시됩니다.'}</div>
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

function getPrimaryPattern(analysis: AnalysisResult | undefined): PatternInfo | null {
  if (!analysis?.patterns?.length) return null
  return analysis.patterns.find(pattern => ['armed', 'confirmed', 'forming'].includes(pattern.state)) ?? analysis.patterns[0] ?? null
}

function getPatternStats(items: PatternStatsEntry[], pattern: PatternInfo | null, timeframe: Timeframe): PatternStatsEntry | null {
  if (!pattern) return null
  const samePattern = items.filter(item => item.pattern_type === pattern.pattern_type)
  return samePattern.find(item => item.timeframe === timeframe) ?? samePattern[0] ?? null
}

function pricePositionHint(currentPrice: number | null, trigger: number | null, invalidation: number | null) {
  if (!currentPrice || currentPrice <= 0) return '현재가를 불러오면 위치를 계산합니다.'
  if (trigger && currentPrice >= trigger) return '트리거 위에서 유지 중입니다.'
  if (trigger && currentPrice < trigger) {
    const gap = (trigger - currentPrice) / currentPrice
    return `트리거까지 ${fmtPct(gap, 1)} 남았습니다.`
  }
  if (invalidation && currentPrice <= invalidation) return '무효화 구간 근처라 보수적으로 봅니다.'
  return '핵심 가격대 안에서 위치를 확인 중입니다.'
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
