import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useMutation, useQueries, useQuery } from '@tanstack/react-query'
import { Activity, Layers3, Loader2, RefreshCw, Sparkles } from 'lucide-react'

import { DashboardSection } from '@/components/dashboard/DashboardSection'
import { Badge } from '@/components/ui/Badge'
import { Card } from '@/components/ui/Card'
import { QueryError } from '@/components/ui/QueryError'
import { dashboardApi, outcomesApi, symbolsApi, systemApi } from '@/lib/api'
import { TIMEFRAME_OPTIONS, normalizeDisplayTimeframe, timeframeLabel } from '@/lib/timeframes'
import { cn, fmtDateTime, fmtPct, fmtPrice, INTRADAY_COLLECTION_MODE_LABELS, PATTERN_NAMES, SETUP_STAGE_LABELS } from '@/lib/utils'
import { useAppStore } from '@/store/app'
import type { DashboardItem, DashboardResponse, OutcomeEvaluationResponse, OutcomeRecord, OutcomesSummary, OutcomeStatus, PriceInfo, ScanStatusResponse, Timeframe } from '@/types/api'

type IntradayView = 'all' | 'live' | 'stored' | 'public' | 'mixed' | 'cooldown'
type IntradayPreset = 'all' | 'ready-now' | 'watch' | 'recheck' | 'cooling'
type CandidateMovement = 'new' | 'steady' | 'weakening'

interface CandidateSnapshot {
  score: number
  actionPlan: string
  noSignal: boolean
  updatedAt: string
}

interface FocusCandidate {
  item: DashboardItem
  movement: CandidateMovement
  watched: boolean
  score: number
}

interface WatchlistDeck {
  triggerClose: DashboardItem[]
  riskClose: DashboardItem[]
}

interface RoutineDeck {
  premarket: DashboardItem[]
  intraday: DashboardItem[]
  afterMarket: DashboardItem[]
}

type RoutineMode = 'premarket' | 'intraday' | 'afterMarket'
type RoutineModeSelection = 'auto' | RoutineMode

interface RoutineColumnDef {
  mode: RoutineMode
  title: string
  subtitle: string
  tone: 'primary' | 'sky' | 'amber'
  items: DashboardItem[]
  empty: string
}

const DASHBOARD_SNAPSHOT_PREFIX = 'stock-chart-helper:dashboard-snapshot:v1'

const INTRADAY_VIEW_OPTIONS: Array<[IntradayView, string]> = [
  ['all', '전체'],
  ['live', 'Live'],
  ['stored', '저장'],
  ['public', '공개'],
  ['mixed', '혼합'],
  ['cooldown', '쿨다운'],
]

const INTRADAY_PRESET_OPTIONS: Array<[IntradayPreset, string]> = [
  ['all', '전체'],
  ['ready-now', '지금 볼 후보'],
  ['watch', '지켜볼 후보'],
  ['recheck', '재확인 필요'],
  ['cooling', '관망'],
]

export default function DashboardPage() {
  const nav = useNavigate()
  const { selectedTimeframe, setTimeframe, isWatched } = useAppStore()
  const timeframe = normalizeDisplayTimeframe(selectedTimeframe)
  const intradayMode = ['60m', '30m', '15m', '1m'].includes(timeframe)
  const [isTriggeringScan, setIsTriggeringScan] = useState(false)
  const [intradayView, setIntradayView] = useState<IntradayView>('all')
  const [intradayPreset, setIntradayPreset] = useState<IntradayPreset>('all')
  const [snapshotBaseline, setSnapshotBaseline] = useState<Record<string, CandidateSnapshot>>({})
  const lastFinishedAtRef = useRef<string | null>(null)
  const lastStatusRef = useRef<string | null>(null)

  const overviewQ = useQuery({
    queryKey: ['dashboard', timeframe, 'overview'],
    queryFn: () => dashboardApi.overview(timeframe),
    staleTime: 30_000,
    refetchInterval: 60_000,
  })

  const statusQ = useQuery({
    queryKey: ['dashboard', timeframe, 'scan-status'],
    queryFn: () => dashboardApi.scanStatus(timeframe),
    staleTime: 5_000,
    refetchInterval: query => {
      const current = query.state.data as ScanStatusResponse | undefined
      return current?.is_running || current?.candidate_source === 'placeholder_seed' ? 5_000 : 15_000
    },
  })

  const outcomesQ = useQuery({
    queryKey: ['outcomes', 'dashboard', timeframe],
    queryFn: outcomesApi.list,
    staleTime: 60_000,
  })
  const outcomesSummaryQ = useQuery({
    queryKey: ['outcomes', 'summary', 'dashboard'],
    queryFn: outcomesApi.summary,
    staleTime: 60_000,
  })

  useEffect(() => {
    const lastFinishedAt = statusQ.data?.last_finished_at
    const status = statusQ.data?.status ?? null
    const previousFinishedAt = lastFinishedAtRef.current
    const previousStatus = lastStatusRef.current

    if (status === 'ready' && lastFinishedAt && (previousFinishedAt !== lastFinishedAt || previousStatus !== 'ready')) {
      overviewQ.refetch()
    }

    if (lastFinishedAt) {
      lastFinishedAtRef.current = lastFinishedAt
    }
    lastStatusRef.current = status
  }, [overviewQ, statusQ.data?.last_finished_at, statusQ.data?.status])

  useEffect(() => {
    setIntradayView('all')
    setIntradayPreset('all')
    lastFinishedAtRef.current = null
    lastStatusRef.current = null
  }, [timeframe])

  const triggerScan = async () => {
    setIsTriggeringScan(true)
    try {
      await dashboardApi.refreshScan(timeframe)
      await Promise.all([statusQ.refetch(), overviewQ.refetch()])
    } finally {
      setIsTriggeringScan(false)
    }
  }

  const refreshBoards = () => {
    overviewQ.refetch()
    statusQ.refetch()
  }

  const overview = overviewQ.data
  const sections = useMemo(() => {
    const filter = (data: DashboardResponse | undefined) => filterDashboard(data, intradayMode, intradayView, intradayPreset)

    return {
      longData: filter(overview?.long_high_probability),
      armedData: filter(overview?.pattern_armed),
      liveData: filter(overview?.live_intraday_candidates),
      formingData: filter(overview?.forming_candidates),
      simData: filter(overview?.high_textbook_similarity),
      shortData: filter(overview?.short_high_probability),
      noSigData: filter(overview?.watchlist_no_signal),
    }
  }, [intradayMode, intradayPreset, intradayView, overview])

  const summary = useMemo(
    () =>
      buildDashboardSummary([
        sections.longData,
        sections.armedData,
        sections.liveData,
        sections.formingData,
        sections.simData,
        sections.shortData,
        sections.noSigData,
      ]),
    [sections],
  )

  const allDashboardItems = useMemo(
    () =>
      dedupeDashboardItems([
        sections.longData,
        sections.armedData,
        sections.liveData,
        sections.formingData,
        sections.simData,
        sections.shortData,
        sections.noSigData,
      ]),
    [sections],
  )

  useEffect(() => {
    setSnapshotBaseline(readDashboardSnapshot(timeframe))
  }, [timeframe])

  useEffect(() => {
    if (allDashboardItems.length === 0) return
    writeDashboardSnapshot(timeframe, allDashboardItems, overview?.generated_at)
  }, [allDashboardItems, overview?.generated_at, timeframe])

  const focusDeck = useMemo(() => buildFocusDeck(allDashboardItems, snapshotBaseline, isWatched), [allDashboardItems, snapshotBaseline, isWatched])
  const watchlistDeck = useMemo(() => buildWatchlistDeck(allDashboardItems, isWatched), [allDashboardItems, isWatched])
  const routineDeck = useMemo(() => buildRoutineDeck(focusDeck, allDashboardItems, isWatched), [allDashboardItems, focusDeck, isWatched])
  const routineSymbols = useMemo(() => uniqueRoutineSymbols(routineDeck), [routineDeck])
  const routinePriceQueries = useQueries({
    queries: routineSymbols.map(code => ({
      queryKey: ['price', 'routine', code],
      queryFn: () => symbolsApi.getPrice(code),
      enabled: routineSymbols.length > 0,
      staleTime: 45_000,
      refetchInterval: 90_000,
    })),
  })
  const routinePrices = useMemo(
    () =>
      routineSymbols.reduce<Record<string, PriceInfo | undefined>>((acc, code, index) => {
        acc[code] = routinePriceQueries[index]?.data
        return acc
      }, {}),
    [routinePriceQueries, routineSymbols],
  )
  const kisPrime = useMutation({
    mutationFn: () => systemApi.primeKis({ symbol: routineSymbols[0], timeframe: '1m' }),
    onSuccess: () => {
      statusQ.refetch()
      routinePriceQueries.forEach(query => query.refetch())
    },
  })
  const pendingOutcomeRecords = useMemo(
    () =>
      (outcomesQ.data ?? [])
        .filter(record => record.outcome === 'pending')
        .filter(record => record.timeframe === timeframe || !record.timeframe)
        .slice(0, 6),
    [outcomesQ.data, timeframe],
  )
  const updateOutcomeMutation = useMutation({
    mutationFn: ({ id, outcome }: { id: number; outcome: OutcomeStatus }) =>
      outcomesApi.update(id, {
        outcome,
        exit_date: new Date().toISOString().slice(0, 10),
      }),
    onSuccess: () => {
      outcomesQ.refetch()
      outcomesSummaryQ.refetch()
    },
  })
  const evaluateOutcomesMutation = useMutation({
    mutationFn: outcomesApi.evaluatePending,
    onSuccess: () => {
      outcomesQ.refetch()
      outcomesSummaryQ.refetch()
    },
  })

  const openCandidate = (item: DashboardItem) => {
    setTimeframe(item.timeframe)
    nav(`/chart/${item.symbol.code}`)
  }

  const status = statusQ.data
  const isScanActive = isTriggeringScan || status?.is_running
  const intradaySummary = intradayMode ? buildIntradaySummary(Object.values(sections)) : null
  const liveEmptyMessage = getLiveSectionEmptyMessage(status, timeframe)
  const sectionEmptyMessage = getDefaultSectionEmptyMessage(status, timeframe)

  return (
    <div className="space-y-6">
      <section className="grid gap-4 xl:grid-cols-[minmax(0,1.3fr)_360px]">
        <Card className="space-y-5 border-primary/15 bg-[linear-gradient(180deg,rgba(37,99,235,0.12),rgba(15,23,42,0.18))]">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
            <div className="space-y-3">
              <div className="inline-flex items-center gap-2 rounded-full border border-primary/20 bg-primary/10 px-3 py-1 text-[11px] font-medium text-primary">
                <Sparkles size={12} />
                핵심 후보를 먼저 보여주는 대시보드
              </div>
              <div>
                <h1 className="text-2xl font-bold tracking-tight">대시보드</h1>
                <p className="mt-2 max-w-2xl text-sm leading-relaxed text-muted-foreground">
                  지금 바로 볼 종목과 조금 더 기다릴 종목을 분리해서 보여줍니다. 점수는 많지만 화면에서는 우선순위와
                  다음 액션이 먼저 보이도록 정리했습니다.
                </p>
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
                      : 'border-border bg-background/60 text-muted-foreground hover:text-foreground',
                  )}
                >
                  {option.label}
                </button>
              ))}
            </div>
          </div>

          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <HeroMetric
              label="전체 후보"
              value={`${summary.totalCount}개`}
              hint={`${summary.readyCount}개 즉시 검토, ${summary.watchCount}개 관찰`}
            />
            <HeroMetric
              label="평균 상승 확률"
              value={summary.totalCount > 0 ? fmtPct(summary.avgUp, 0) : '-'}
              hint={summary.bestAction}
            />
            <HeroMetric
              label="평균 준비도"
              value={summary.totalCount > 0 ? fmtPct(summary.avgReadiness, 0) : '-'}
              hint={`데이터 품질 ${summary.totalCount > 0 ? fmtPct(summary.avgQuality, 0) : '-'}`}
            />
            <HeroMetric
              label="지금 흐름"
              value={statusHeadline(status)}
              hint={statusSubline(status, timeframe)}
            />
          </div>

          {intradayMode && (
            <div className="space-y-3 rounded-lg border border-sky-500/20 bg-sky-500/5 p-4">
              <div className="flex flex-col gap-2 lg:flex-row lg:items-center lg:justify-between">
                <div>
                  <div className="text-sm font-semibold text-sky-100">분봉 후보 필터</div>
                  <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
                    장중에는 live 후보를 더 우선하고, 장외에는 저장 데이터 기준으로 보수적으로 정리합니다.
                  </p>
                </div>
                {intradaySummary && (
                  <div className="rounded-lg border border-sky-400/20 bg-background/50 px-3 py-2 text-xs text-sky-100">
                    {intradaySummary.guidance}
                  </div>
                )}
              </div>

              <div className="flex flex-wrap gap-2">
                {INTRADAY_VIEW_OPTIONS.map(([value, label]) => (
                  <button
                    key={value}
                    onClick={() => setIntradayView(value)}
                    className={cn(
                      'rounded-lg border px-3 py-1.5 text-xs transition-colors',
                      intradayView === value
                        ? 'border-sky-400/30 bg-sky-500/20 text-sky-100'
                        : 'border-border bg-background/50 text-muted-foreground hover:text-foreground',
                    )}
                  >
                    {label}
                  </button>
                ))}
              </div>

              <div className="flex flex-wrap gap-2">
                {INTRADAY_PRESET_OPTIONS.map(([value, label]) => (
                  <button
                    key={value}
                    onClick={() => setIntradayPreset(value)}
                    className={cn(
                      'rounded-lg border px-3 py-1.5 text-xs transition-colors',
                      intradayPreset === value
                        ? 'border-emerald-500/30 bg-emerald-500/20 text-emerald-100'
                        : 'border-border bg-background/50 text-muted-foreground hover:text-foreground',
                    )}
                  >
                    {label}
                  </button>
                ))}
              </div>
            </div>
          )}
        </Card>

        <Card className="space-y-4">
          <div className="flex items-center justify-between gap-3">
            <div>
              <div className="flex items-center gap-2 text-sm font-semibold">
                <Activity size={15} className={status?.is_running ? 'text-primary' : 'text-muted-foreground'} />
                스캔 상태
              </div>
              <p className="mt-1 text-xs text-muted-foreground">최근 스캔과 데이터 준비 상황을 빠르게 확인합니다.</p>
            </div>

            <button
              onClick={refreshBoards}
              className="inline-flex items-center gap-1.5 text-xs text-muted-foreground transition-colors hover:text-foreground"
            >
              <RefreshCw size={13} className={overviewQ.isFetching ? 'animate-spin' : ''} />
              새로고침
            </button>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <StatusCell label="상태" value={statusLabel(status?.status)} />
            <StatusCell label="마지막 완료" value={fmtDateTime(status?.last_finished_at)} />
            <StatusCell label="캐시 결과" value={`${status?.cached_result_count ?? 0}개`} />
            <StatusCell label="후보 생성 방식" value={candidateSourceLabel(status?.candidate_source)} />
          </div>

          {candidateSourceWarning(status?.candidate_source) && (
            <div className="rounded-lg border border-amber-400/30 bg-amber-400/10 p-3 text-xs leading-relaxed text-amber-200">
              {candidateSourceWarning(status?.candidate_source)}
            </div>
          )}

          <button
            onClick={triggerScan}
            disabled={Boolean(isScanActive)}
            className="inline-flex w-full items-center justify-center gap-2 rounded-lg bg-primary px-4 py-2.5 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {isScanActive ? <Loader2 size={14} className="animate-spin" /> : <RefreshCw size={14} />}
            {isScanActive ? `${timeframeLabel(timeframe)} 스캔 중 · 보통 2~3분` : `${timeframeLabel(timeframe)} 다시 스캔`}
          </button>

          <button
            onClick={() => kisPrime.mutate()}
            disabled={kisPrime.isPending || routineSymbols.length === 0}
            className="inline-flex w-full items-center justify-center gap-2 rounded-lg border border-emerald-400/25 bg-emerald-400/10 px-4 py-2.5 text-sm font-medium text-emerald-100 transition-colors hover:bg-emerald-400/15 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {kisPrime.isPending ? <Loader2 size={14} className="animate-spin" /> : <Activity size={14} />}
            KIS 토큰 + 현재가 프라임
          </button>

          <div className="rounded-lg border border-border bg-background/60 p-3 text-xs leading-relaxed text-muted-foreground">
            {kisPrime.data?.message || statusSubline(status, timeframe)}
          </div>

          {statusQ.isError && !statusQ.isLoading && (
            <QueryError compact message="스캔 상태를 불러오지 못했습니다." onRetry={() => statusQ.refetch()} />
          )}
        </Card>
      </section>

      <section className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_320px]">
        <Card className="space-y-4">
          <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <div className="text-sm font-semibold">오늘의 핵심 3-3-3</div>
              <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
                우선 확인 3개, 재확인 3개, 보류 3개만 먼저 잡아 피로도를 줄였습니다.
              </p>
            </div>
            <Badge variant="muted">{timeframeLabel(timeframe)} 기준</Badge>
          </div>

          <div className="grid gap-3 xl:grid-cols-3">
            <FocusColumn
              title="우선"
              tone="primary"
              items={focusDeck.priority}
              empty="지금 바로 볼 핵심 후보가 아직 없습니다."
              onOpen={openCandidate}
            />
            <FocusColumn
              title="재확인"
              tone="sky"
              items={focusDeck.recheck}
              empty="다시 확인할 후보가 아직 없습니다."
              onOpen={openCandidate}
            />
            <FocusColumn
              title="보류"
              tone="amber"
              items={focusDeck.hold}
              empty="보류 후보가 아직 없습니다."
              onOpen={openCandidate}
            />
          </div>
        </Card>

        <Card className="space-y-4">
          <div>
            <div className="text-sm font-semibold">신호 변화</div>
            <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
              같은 후보가 계속 반복되어 보이는 피로감을 줄이기 위해 이전 스냅샷과 비교합니다.
            </p>
          </div>
          <div className="grid grid-cols-3 gap-2">
            <MovementStat label="신규" value={focusDeck.movementCounts.new} className="text-emerald-300" />
            <MovementStat label="유지" value={focusDeck.movementCounts.steady} className="text-sky-300" />
            <MovementStat label="약화" value={focusDeck.movementCounts.weakening} className="text-amber-300" />
          </div>
          <div className="rounded-lg border border-border bg-background/60 p-3 text-xs leading-relaxed text-muted-foreground">
            관심종목은 같은 점수라면 위로 끌어올리고, 무효화/관망 신호는 자동으로 보류 쪽에 모읍니다.
          </div>
        </Card>
      </section>

      {(watchlistDeck.triggerClose.length > 0 || watchlistDeck.riskClose.length > 0) && (
        <section className="grid gap-4 xl:grid-cols-2">
          <Card className="space-y-4 border-amber-400/20 bg-amber-400/5">
            <div>
              <div className="text-sm font-semibold">내 관심종목 중 트리거 가까운 것</div>
              <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
                관심종목 중에서 오늘 바로 다시 볼 가치가 큰 후보만 먼저 묶었습니다.
              </p>
            </div>
            <div className="space-y-2">
              {watchlistDeck.triggerClose.length === 0 ? (
                <div className="rounded-lg border border-border bg-background/60 p-3 text-xs text-muted-foreground">
                  오늘은 관심종목 중 즉시 재확인할 후보가 아직 없습니다.
                </div>
              ) : (
                watchlistDeck.triggerClose.map(item => (
                  <RoutineRow key={`watch-trigger-${item.timeframe}-${item.symbol.code}`} item={item} mode="intraday" price={routinePrices[item.symbol.code]} onOpen={openCandidate} />
                ))
              )}
            </div>
          </Card>

          <Card className="space-y-4 border-red-500/20 bg-red-500/5">
            <div>
              <div className="text-sm font-semibold">내 관심종목 중 무효화 위험</div>
              <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
                관심종목인데 구조가 약해졌거나 무효화 확인이 필요한 후보를 따로 모아뒀습니다.
              </p>
            </div>
            <div className="space-y-2">
              {watchlistDeck.riskClose.length === 0 ? (
                <div className="rounded-lg border border-border bg-background/60 p-3 text-xs text-muted-foreground">
                  지금은 무효화 위험이 크게 올라온 관심종목이 없습니다.
                </div>
              ) : (
                watchlistDeck.riskClose.map(item => (
                  <RoutineRow key={`watch-risk-${item.timeframe}-${item.symbol.code}`} item={item} mode="afterMarket" price={routinePrices[item.symbol.code]} onOpen={openCandidate} />
                ))
              )}
            </div>
          </Card>
        </section>
      )}

      <RoutineDesk deck={routineDeck} prices={routinePrices} isFetchingPrices={routinePriceQueries.some(query => query.isFetching)} onOpen={openCandidate} />

      <PendingDecisionDesk
        records={pendingOutcomeRecords}
        isLoading={outcomesQ.isLoading}
        isUpdating={updateOutcomeMutation.isPending}
        isEvaluating={evaluateOutcomesMutation.isPending}
        evaluationResult={evaluateOutcomesMutation.data}
        onOpen={code => nav(`/chart/${code}`)}
        onUpdate={(id, outcome) => updateOutcomeMutation.mutate({ id, outcome })}
        onEvaluate={() => evaluateOutcomesMutation.mutate()}
      />

      <PersonalPerformanceDesk summary={outcomesSummaryQ.data} isLoading={outcomesSummaryQ.isLoading} />

      <section className="grid gap-4 lg:grid-cols-[minmax(0,1.2fr)_minmax(0,0.8fr)]">
        <Card className="space-y-4">
          <div className="flex items-center gap-2 text-sm font-semibold">
            <Layers3 size={15} className="text-primary" />
            한눈에 보는 흐름
          </div>
          <div className="grid gap-3 md:grid-cols-3">
            <QuickBoard
              title="바로 볼 후보"
              value={`${summary.readyCount}개`}
              description="준비도와 진입 구간이 살아 있는 종목입니다."
            />
            <QuickBoard
              title="조금 더 지켜볼 후보"
              value={`${summary.watchCount}개`}
              description="패턴은 괜찮지만 트리거나 품질 확인이 더 필요한 종목입니다."
            />
            <QuickBoard
              title="관망 / 리스크"
              value={`${summary.riskCount}개`}
              description="신호가 약하거나 보수적으로 봐야 하는 종목입니다."
            />
          </div>
        </Card>

        <Card className="space-y-4">
          <div className="text-sm font-semibold">읽는 순서</div>
          <div className="space-y-3 text-sm text-muted-foreground">
            <FlowStep
              title="1. 지금 볼 후보 먼저"
              body="상단 두 섹션은 바로 체크할 종목 위주로 정리했습니다."
            />
            <FlowStep
              title="2. 형성 중 후보 확인"
              body="진입 직전이 아니라도 구조가 살아 있는 종목은 별도로 모아둡니다."
            />
            <FlowStep
              title="3. 나머지는 필요할 때만"
              body="유사도, 숏 후보, 관망 구간은 아래 보조 섹션에서 천천히 보면 됩니다."
            />
          </div>
        </Card>
      </section>

      <DashboardSection
        title="지금 볼 후보"
        subtitle="상승 확률, 준비도, 진입 구간이 함께 괜찮은 종목부터 보여줍니다."
        data={sections.longData}
        isLoading={overviewQ.isLoading}
        isError={overviewQ.isError}
        onRetry={() => overviewQ.refetch()}
        intradayPreset={intradayMode ? intradayPreset : undefined}
        emptyMessage={sectionEmptyMessage}
      />

      {intradayMode && (
        <DashboardSection
          title="Live 분봉 우선 후보"
          subtitle="실제 live 분봉까지 연결된 후보를 우선으로 정리했습니다."
          data={sections.liveData}
          isLoading={overviewQ.isLoading}
          isError={overviewQ.isError}
          onRetry={() => overviewQ.refetch()}
          intradayPreset={intradayPreset}
          emptyMessage={liveEmptyMessage}
        />
      )}

      <DashboardSection
        title="형성 중 후보"
        subtitle="완성 직전은 아니지만 구조가 살아 있어 관찰 가치가 있는 후보입니다."
        data={sections.formingData}
        isLoading={overviewQ.isLoading}
        isError={overviewQ.isError}
        onRetry={() => overviewQ.refetch()}
        intradayPreset={intradayMode ? intradayPreset : undefined}
        emptyMessage={sectionEmptyMessage}
      />

      <section className="grid gap-4 xl:grid-cols-2">
        <DashboardSection
          title="패턴 완성 임박"
          subtitle="거의 다 만들어졌고 트리거 근처까지 온 후보입니다."
          data={sections.armedData}
          isLoading={overviewQ.isLoading}
          isError={overviewQ.isError}
          onRetry={() => overviewQ.refetch()}
          intradayPreset={intradayMode ? intradayPreset : undefined}
          emptyMessage={sectionEmptyMessage}
        />

        <DashboardSection
          title="교과서 유사도 상위"
          subtitle="모양은 좋지만 현재 시장 맥락까지 함께 봐야 하는 후보입니다."
          data={sections.simData}
          isLoading={overviewQ.isLoading}
          isError={overviewQ.isError}
          onRetry={() => overviewQ.refetch()}
          intradayPreset={intradayMode ? intradayPreset : undefined}
          emptyMessage={sectionEmptyMessage}
        />

        <DashboardSection
          title="하락 시나리오 후보"
          subtitle="숏 방향 또는 약세 구조가 강한 종목입니다."
          data={sections.shortData}
          isLoading={overviewQ.isLoading}
          isError={overviewQ.isError}
          onRetry={() => overviewQ.refetch()}
          intradayPreset={intradayMode ? intradayPreset : undefined}
          emptyMessage={sectionEmptyMessage}
        />

        <DashboardSection
          title="관망 / No Signal"
          subtitle="억지로 해석하지 않는 편이 좋은 종목입니다."
          data={sections.noSigData}
          isLoading={overviewQ.isLoading}
          isError={overviewQ.isError}
          onRetry={() => overviewQ.refetch()}
          intradayPreset={intradayMode ? intradayPreset : undefined}
          emptyMessage={sectionEmptyMessage}
        />
      </section>
    </div>
  )
}

function HeroMetric({ label, value, hint }: { label: string; value: string; hint: string }) {
  return (
    <div className="rounded-lg border border-border/80 bg-background/55 p-4">
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className="mt-2 text-xl font-semibold">{value}</div>
      <p className="mt-2 text-xs leading-relaxed text-muted-foreground">{hint}</p>
    </div>
  )
}

function QuickBoard({ title, value, description }: { title: string; value: string; description: string }) {
  return (
    <div className="rounded-lg border border-border bg-background/60 p-4">
      <div className="text-xs text-muted-foreground">{title}</div>
      <div className="mt-1 text-xl font-semibold">{value}</div>
      <p className="mt-2 text-xs leading-relaxed text-muted-foreground">{description}</p>
    </div>
  )
}

function FlowStep({ title, body }: { title: string; body: string }) {
  return (
    <div className="rounded-lg border border-border bg-background/55 p-3">
      <div className="text-sm font-medium text-foreground">{title}</div>
      <p className="mt-1 text-xs leading-relaxed text-muted-foreground">{body}</p>
    </div>
  )
}

function StatusCell({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-border bg-background/60 p-3">
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className="mt-1 text-sm font-medium">{value}</div>
    </div>
  )
}

function FocusColumn({
  title,
  tone,
  items,
  empty,
  onOpen,
}: {
  title: string
  tone: 'primary' | 'sky' | 'amber'
  items: FocusCandidate[]
  empty: string
  onOpen: (item: DashboardItem) => void
}) {
  const toneClass = {
    primary: 'border-primary/25 bg-primary/10 text-primary',
    sky: 'border-sky-400/25 bg-sky-400/10 text-sky-200',
    amber: 'border-amber-400/25 bg-amber-400/10 text-amber-200',
  }[tone]

  return (
    <div className="space-y-2">
      <div className={cn('rounded-lg border px-3 py-2 text-xs font-semibold', toneClass)}>{title}</div>
      {items.length === 0 ? (
        <div className="rounded-lg border border-border bg-background/55 p-3 text-xs leading-relaxed text-muted-foreground">{empty}</div>
      ) : (
        items.map(candidate => <FocusCandidateCard key={`${candidate.item.timeframe}-${candidate.item.symbol.code}-${title}`} candidate={candidate} onOpen={onOpen} />)
      )}
    </div>
  )
}

function FocusCandidateCard({ candidate, onOpen }: { candidate: FocusCandidate; onOpen: (item: DashboardItem) => void }) {
  const { item, movement, watched } = candidate
  const patternName = item.pattern_type ? PATTERN_NAMES[item.pattern_type] ?? item.pattern_type : 'No Signal'

  return (
    <button
      onClick={() => onOpen(item)}
      className="w-full rounded-lg border border-border bg-background/60 p-3 text-left transition-colors hover:border-primary/35 hover:bg-background/75"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="truncate text-sm font-semibold text-foreground">{item.symbol.name}</span>
            <span className="font-mono text-[11px] text-muted-foreground">{item.symbol.code}</span>
            {watched && <Badge variant="warning">관심</Badge>}
          </div>
          <div className="mt-1 truncate text-xs text-muted-foreground">{patternName}</div>
        </div>
        <MovementBadge movement={movement} />
      </div>
      <div className="mt-3 grid grid-cols-3 gap-2 text-[11px]">
        <MiniMetric label="상승" value={fmtPct(item.p_up, 0)} />
        <MiniMetric label="준비" value={fmtPct(item.trade_readiness_score ?? 0, 0)} />
        <MiniMetric label="신선" value={fmtPct(item.freshness_score ?? 0, 0)} />
      </div>
      <p className="mt-3 line-clamp-2 text-xs leading-relaxed text-muted-foreground">{item.next_trigger || item.action_plan_summary || item.reason_summary}</p>
    </button>
  )
}

function MovementBadge({ movement }: { movement: CandidateMovement }) {
  const config = {
    new: ['신규', 'border-emerald-400/25 bg-emerald-400/10 text-emerald-200'],
    steady: ['유지', 'border-sky-400/25 bg-sky-400/10 text-sky-200'],
    weakening: ['약화', 'border-amber-400/25 bg-amber-400/10 text-amber-200'],
  } satisfies Record<CandidateMovement, [string, string]>

  const [label, className] = config[movement]
  return <span className={cn('shrink-0 rounded-md border px-1.5 py-0.5 text-[11px] font-medium', className)}>{label}</span>
}

function MiniMetric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-border bg-card/60 px-2 py-1">
      <div className="text-muted-foreground">{label}</div>
      <div className="mt-0.5 font-semibold text-foreground">{value}</div>
    </div>
  )
}

function MovementStat({ label, value, className }: { label: string; value: number; className: string }) {
  return (
    <div className="rounded-lg border border-border bg-background/60 p-3 text-center">
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className={cn('mt-1 text-lg font-bold', className)}>{value}</div>
    </div>
  )
}

function RoutineDesk({
  deck,
  prices,
  isFetchingPrices,
  onOpen,
}: {
  deck: RoutineDeck
  prices: Record<string, PriceInfo | undefined>
  isFetchingPrices: boolean
  onOpen: (item: DashboardItem) => void
}) {
  const autoSessionMode = getKstRoutineMode()
  const [modeSelection, setModeSelection] = useState<RoutineModeSelection>('auto')
  const sessionMode: RoutineMode = modeSelection === 'auto' ? autoSessionMode : modeSelection
  const sessionMeta = getRoutineModeMeta(sessionMode)
  const currentItems = deck[sessionMode]
  const routineColumns: RoutineColumnDef[] = [
    {
      mode: 'premarket',
      title: '장전 5선',
      subtitle: '오늘 먼저 볼 후보만 압축',
      tone: 'primary',
      items: deck.premarket,
      empty: '장전 후보가 아직 없습니다.',
    },
    {
      mode: 'intraday',
      title: '장중 모니터',
      subtitle: '현재가와 조건 충족 여부 확인',
      tone: 'sky',
      items: deck.intraday,
      empty: '장중 모니터 대상이 아직 없습니다.',
    },
    {
      mode: 'afterMarket',
      title: '장후 정리',
      subtitle: '보류·무효화·기록 대상 정리',
      tone: 'amber',
      items: deck.afterMarket,
      empty: '장후 정리할 후보가 아직 없습니다.',
    },
  ]
  const orderedColumns = [
    ...routineColumns.filter(column => column.mode === sessionMode),
    ...routineColumns.filter(column => column.mode !== sessionMode),
  ]

  return (
    <section className="space-y-4">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <div className="text-sm font-semibold">오늘 운용 루틴</div>
          <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
            장전에는 후보를 압축하고, 장중에는 현재가와 트리거를 확인하고, 장후에는 무효화와 기록 대상을 정리합니다.
          </p>
        </div>
        <div className="inline-flex items-center gap-1.5 text-xs text-muted-foreground">
          <RefreshCw size={12} className={isFetchingPrices ? 'animate-spin' : ''} />
          상위 후보 현재가 자동 갱신
        </div>
      </div>

      <Card className={cn('space-y-4', sessionMeta.panelClass)}>
        <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
          <div className="space-y-2">
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant={sessionMeta.badgeVariant}>{sessionMeta.label}</Badge>
              <span className="text-sm font-semibold text-foreground">{sessionMeta.title}</span>
            </div>
            <p className="max-w-3xl text-sm leading-relaxed text-muted-foreground">{sessionMeta.summary}</p>
          </div>
          <div className="grid grid-cols-3 gap-2 text-xs sm:min-w-72">
            <RoutineCount label="장전" value={deck.premarket.length} active={sessionMode === 'premarket'} />
            <RoutineCount label="장중" value={deck.intraday.length} active={sessionMode === 'intraday'} />
            <RoutineCount label="장후" value={deck.afterMarket.length} active={sessionMode === 'afterMarket'} />
          </div>
        </div>

        <div className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_320px]">
          <div className="grid gap-2 md:grid-cols-3">
            {sessionMeta.checkpoints.map(checkpoint => (
              <div key={checkpoint.title} className="rounded-lg border border-border bg-background/55 p-3">
                <div className="text-xs font-medium text-foreground">{checkpoint.title}</div>
                <p className="mt-1 text-xs leading-relaxed text-muted-foreground">{checkpoint.body}</p>
              </div>
            ))}
          </div>
          <div className="rounded-lg border border-border bg-background/55 p-3">
            <div className="text-xs text-muted-foreground">현재 모드 핵심 후보</div>
            <div className="mt-1 text-lg font-semibold text-foreground">{currentItems.length}개</div>
            <p className="mt-1 text-xs leading-relaxed text-muted-foreground">{sessionMeta.primaryAction}</p>
          </div>
        </div>
      </Card>

      <div className="flex flex-wrap gap-2">
        {(['auto', 'premarket', 'intraday', 'afterMarket'] as RoutineModeSelection[]).map(mode => (
          <button
            key={mode}
            onClick={() => setModeSelection(mode)}
            className={cn(
              'rounded-lg border px-3 py-1.5 text-xs transition-colors',
              modeSelection === mode
                ? 'border-primary/25 bg-primary/10 text-primary'
                : 'border-border bg-background/60 text-muted-foreground hover:text-foreground',
            )}
          >
            {mode === 'auto' ? `자동 · ${getRoutineModeMeta(autoSessionMode).label}` : getRoutineModeMeta(mode).label}
          </button>
        ))}
      </div>

      <div className="flex flex-wrap gap-2">
        {routineColumns.map(column => (
          <span
            key={column.mode}
            className={cn(
              'rounded-lg border px-3 py-1.5 text-xs',
              column.mode === sessionMode
                ? 'border-primary/25 bg-primary/10 text-primary'
                : 'border-border bg-background/60 text-muted-foreground',
            )}
          >
            {column.title}
            {column.mode === sessionMode ? ' · 현재 모드' : ''}
          </span>
        ))}
      </div>

      <div className="grid gap-4 xl:grid-cols-3">
        {orderedColumns.map(column => (
          <RoutineColumn
            key={column.mode}
            title={column.title}
            subtitle={column.subtitle}
            tone={column.tone}
            items={column.items}
            prices={prices}
            mode={column.mode}
            isActive={column.mode === sessionMode}
            empty={column.empty}
            onOpen={onOpen}
          />
        ))}
      </div>
    </section>
  )
}

function RoutineCount({ label, value, active }: { label: string; value: number; active: boolean }) {
  return (
    <div className={cn('rounded-lg border p-2 text-center', active ? 'border-primary/25 bg-primary/10' : 'border-border bg-background/55')}>
      <div className="text-[11px] text-muted-foreground">{label}</div>
      <div className="mt-0.5 text-sm font-semibold text-foreground">{value}개</div>
    </div>
  )
}

function getKstRoutineMode(now = new Date()): RoutineMode {
  const kst = new Date(now.toLocaleString('en-US', { timeZone: 'Asia/Seoul' }))
  const day = kst.getDay()
  const hour = kst.getHours()
  const minute = kst.getMinutes()
  const minutes = hour * 60 + minute
  const isWeekend = day === 0 || day === 6

  if (isWeekend) return 'afterMarket'
  if (minutes < 9 * 60) return 'premarket'
  if (minutes <= 15 * 60 + 30) return 'intraday'
  return 'afterMarket'
}

function getRoutineModeMeta(mode: RoutineMode) {
  if (mode === 'premarket') {
    return {
      label: '장전',
      title: '오늘의 5선과 핵심 가격대만 먼저 압축',
      summary: '장 시작 전에는 종목 수를 줄이고 트리거, 무효화, 관심종목 여부를 먼저 확인합니다. 새 후보와 재확인 후보를 섞어 오늘 볼 순서를 정합니다.',
      primaryAction: '상위 후보 5개만 열어 트리거와 무효화 가격을 확인하세요.',
      badgeVariant: 'default' as const,
      panelClass: 'border-primary/20 bg-primary/5',
      checkpoints: [
        { title: '후보 압축', body: '우선 후보와 재확인 후보를 합쳐 오늘 볼 5개만 남깁니다.' },
        { title: '가격대 확인', body: '트리거, 무효화, 목표가가 너무 가까운지 먼저 봅니다.' },
        { title: '관심종목 우선', body: '내 관심종목이면 같은 점수에서도 위로 올려 확인합니다.' },
      ],
    }
  }
  if (mode === 'intraday') {
    return {
      label: '장중',
      title: '현재가와 트리거 근접 여부를 계속 감시',
      summary: '장중에는 후보 설명보다 현재가 위치가 중요합니다. KIS 현재가를 갱신하고 live 분봉 후보, 트리거 근처 후보, 관심종목을 먼저 봅니다.',
      primaryAction: '현재가를 갱신하고 트리거 근처 후보부터 차트로 열어 확인하세요.',
      badgeVariant: 'neutral' as const,
      panelClass: 'border-sky-400/20 bg-sky-400/5',
      checkpoints: [
        { title: '현재가 갱신', body: '상위 후보 현재가와 데이터 출처가 KIS인지 확인합니다.' },
        { title: '트리거 감시', body: '돌파 추격보다 가격대 근처 유지와 눌림 지지를 봅니다.' },
        { title: '분봉은 보조', body: '분봉은 타이밍 보조로만 쓰고 판단 기준은 일봉 가격대에 둡니다.' },
      ],
    }
  }
  return {
    label: '장후',
    title: '미정리 판단과 무효화 후보를 닫는 시간',
    summary: '장후에는 새로운 매수 후보를 더 늘리기보다 오늘의 판단 기록을 닫고, 실패/손절/취소를 정리해 내 성과 데이터가 쌓이게 만듭니다.',
    primaryAction: '미정리 판단을 자동 점검하고 성공, 실패, 손절, 취소 중 하나로 닫으세요.',
    badgeVariant: 'warning' as const,
    panelClass: 'border-amber-400/20 bg-amber-400/5',
    checkpoints: [
      { title: '자동 점검', body: '현재가 기준으로 목표가와 무효화 터치 여부를 먼저 확인합니다.' },
      { title: '수동 정리', body: '자동 판정이 애매하면 성공, 실패, 손절, 취소를 직접 닫습니다.' },
      { title: '내 성과 반영', body: '정리된 기록이 패턴별 내 성과와 다음 개인화의 재료가 됩니다.' },
    ],
  }
}

function RoutineColumn({
  title,
  subtitle,
  tone,
  items,
  prices,
  mode,
  isActive,
  empty,
  onOpen,
}: {
  title: string
  subtitle: string
  tone: 'primary' | 'sky' | 'amber'
  items: DashboardItem[]
  prices: Record<string, PriceInfo | undefined>
  mode: 'premarket' | 'intraday' | 'afterMarket'
  isActive: boolean
  empty: string
  onOpen: (item: DashboardItem) => void
}) {
  const toneClass = {
    primary: 'border-primary/20 bg-primary/10',
    sky: 'border-sky-400/20 bg-sky-400/10',
    amber: 'border-amber-400/20 bg-amber-400/10',
  }[tone]

  return (
    <Card className={cn('space-y-3', toneClass, isActive && 'ring-1 ring-primary/35')}>
      <div className="flex items-start justify-between gap-2">
        <div>
          <div className="text-sm font-semibold">{title}</div>
          <div className="mt-1 text-xs text-muted-foreground">{subtitle}</div>
        </div>
        {isActive && <Badge variant="default">집중</Badge>}
      </div>

      <div className="rounded-lg border border-border bg-background/55 p-2 text-xs text-muted-foreground">
        {getRoutineModeMeta(mode).primaryAction}
      </div>

      {items.length === 0 ? (
        <div className="rounded-lg border border-border bg-background/55 p-3 text-xs text-muted-foreground">{empty}</div>
      ) : (
        <div className="space-y-2">
          {items.map(item => (
            <RoutineRow key={`${mode}-${item.timeframe}-${item.symbol.code}`} item={item} price={prices[item.symbol.code]} mode={mode} onOpen={onOpen} />
          ))}
        </div>
      )}
    </Card>
  )
}

function RoutineRow({
  item,
  price,
  mode,
  onOpen,
}: {
  item: DashboardItem
  price: PriceInfo | undefined
  mode: 'premarket' | 'intraday' | 'afterMarket'
  onOpen: (item: DashboardItem) => void
}) {
  const patternName = item.pattern_type ? PATTERN_NAMES[item.pattern_type] ?? item.pattern_type : 'No Signal'

  return (
    <button
      onClick={() => onOpen(item)}
      className="w-full rounded-lg border border-border bg-background/60 p-3 text-left transition-colors hover:border-primary/35 hover:bg-background/75"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="truncate text-sm font-semibold text-foreground">{item.symbol.name}</span>
            <span className="font-mono text-[11px] text-muted-foreground">{item.symbol.code}</span>
          </div>
          <div className="mt-1 truncate text-xs text-muted-foreground">{patternName}</div>
        </div>
        <span className="shrink-0 rounded-md border border-border bg-card/70 px-1.5 py-0.5 text-[11px] text-muted-foreground">
          {item.action_plan_label}
        </span>
      </div>

      <div className="mt-3 grid grid-cols-3 gap-2 text-[11px]">
        <MiniMetric label="상승" value={fmtPct(item.p_up, 0)} />
        <MiniMetric label="준비" value={fmtPct(item.trade_readiness_score ?? 0, 0)} />
        <MiniMetric label="손익" value={item.reward_risk_ratio.toFixed(2)} />
      </div>

      {mode === 'intraday' && (
        <div className="mt-3 grid grid-cols-[1fr_auto] gap-2 rounded-md border border-border bg-card/60 px-2 py-2 text-xs">
          <span className="text-muted-foreground">현재가</span>
          <span className="font-mono font-semibold text-foreground">{price ? fmtPrice(price.close) : '-'}</span>
          <span className="text-muted-foreground">출처</span>
          <span className={cn('text-right', price?.source === 'kis' ? 'text-emerald-300' : 'text-muted-foreground')}>{price?.source ?? '-'}</span>
        </div>
      )}

      <p className="mt-3 line-clamp-2 text-xs leading-relaxed text-muted-foreground">{routineActionText(item, mode)}</p>
    </button>
  )
}

const PENDING_OUTCOME_LABELS: Record<OutcomeStatus, string> = {
  pending: '대기',
  win: '성공',
  loss: '실패',
  stopped_out: '손절',
  cancelled: '취소',
}

const PENDING_OUTCOME_TONES: Record<OutcomeStatus, string> = {
  pending: 'border-sky-400/25 bg-sky-400/10 text-sky-100',
  win: 'border-emerald-400/25 bg-emerald-400/10 text-emerald-100',
  loss: 'border-red-400/25 bg-red-400/10 text-red-100',
  stopped_out: 'border-amber-400/25 bg-amber-400/10 text-amber-100',
  cancelled: 'border-border bg-background/70 text-muted-foreground',
}

function PendingDecisionDesk({
  records,
  isLoading,
  isUpdating,
  isEvaluating,
  evaluationResult,
  onOpen,
  onUpdate,
  onEvaluate,
}: {
  records: OutcomeRecord[]
  isLoading: boolean
  isUpdating: boolean
  isEvaluating: boolean
  evaluationResult: OutcomeEvaluationResponse | undefined
  onOpen: (code: string) => void
  onUpdate: (id: number, outcome: OutcomeStatus) => void
  onEvaluate: () => void
}) {
  if (isLoading || records.length === 0) {
    return (
      <section className="rounded-lg border border-border bg-card/55 p-4">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <div className="text-sm font-semibold">미정리 판단</div>
            <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
              {isLoading ? '저장한 판단 기록을 확인하는 중입니다.' : '현재 장후에 닫아야 할 대기 기록이 없습니다.'}
            </p>
            {evaluationResult && !isLoading && (
              <p className="mt-2 text-xs text-muted-foreground">
                마지막 자동 점검: {evaluationResult.checked}건 확인, {evaluationResult.updated}건 정리
              </p>
            )}
          </div>
          {isLoading ? (
            <Loader2 size={14} className="animate-spin text-muted-foreground" />
          ) : (
            <button
              onClick={onEvaluate}
              disabled={isEvaluating}
              className="inline-flex items-center justify-center gap-2 rounded-lg border border-border bg-background/60 px-3 py-2 text-xs text-muted-foreground transition-colors hover:text-foreground disabled:cursor-not-allowed disabled:opacity-60"
            >
              {isEvaluating ? <Loader2 size={13} className="animate-spin" /> : <RefreshCw size={13} />}
              자동 점검
            </button>
          )}
        </div>
      </section>
    )
  }

  return (
    <section className="space-y-3 rounded-lg border border-amber-400/20 bg-amber-400/10 p-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <div className="text-sm font-semibold">미정리 판단</div>
          <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
            저장해둔 시나리오는 성공, 실패, 손절, 취소 중 하나로 닫아야 내 성과 데이터가 쌓입니다.
          </p>
          {evaluationResult && (
            <p className="mt-2 text-xs text-amber-100">
              자동 점검: {evaluationResult.checked}건 확인, {evaluationResult.updated}건 정리, {evaluationResult.skipped}건 보류
            </p>
          )}
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            onClick={onEvaluate}
            disabled={isEvaluating}
            className="inline-flex items-center justify-center gap-2 rounded-lg border border-amber-400/25 bg-amber-400/10 px-3 py-2 text-xs text-amber-100 transition-colors hover:bg-amber-400/15 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {isEvaluating ? <Loader2 size={13} className="animate-spin" /> : <RefreshCw size={13} />}
            현재가로 자동 점검
          </button>
          <span className="rounded-md border border-amber-400/25 bg-amber-400/10 px-2 py-2 text-xs text-amber-100">
            대기 {records.length}건
          </span>
        </div>
      </div>

      <div className="grid gap-2 xl:grid-cols-2">
        {records.map(record => (
          <div key={record.id ?? `${record.symbol_code}-${record.signal_date}`} className="rounded-lg border border-border bg-background/60 p-3">
            <div className="flex flex-wrap items-start justify-between gap-2">
              <button onClick={() => onOpen(record.symbol_code)} className="min-w-0 text-left">
                <div className="flex flex-wrap items-center gap-1.5">
                  <span className="text-sm font-semibold text-foreground">{record.symbol_name}</span>
                  <span className="font-mono text-[11px] text-muted-foreground">{record.symbol_code}</span>
                  <span className={cn('rounded-md border px-1.5 py-0.5 text-[11px]', PENDING_OUTCOME_TONES.pending)}>
                    {PENDING_OUTCOME_LABELS.pending}
                  </span>
                </div>
                <div className="mt-1 flex flex-wrap gap-3 text-[11px] text-muted-foreground">
                  <span>{PATTERN_NAMES[record.pattern_type] ?? record.pattern_type}</span>
                  <span>{record.signal_date}</span>
                  <span>진입 {record.entry_price > 0 ? fmtPrice(record.entry_price) : '-'}</span>
                </div>
              </button>

              {record.id != null && (
                <div className="flex shrink-0 flex-wrap justify-end gap-1">
                  {(['win', 'loss', 'stopped_out', 'cancelled'] as OutcomeStatus[]).map(outcome => (
                    <button
                      key={outcome}
                      onClick={() => onUpdate(record.id!, outcome)}
                      disabled={isUpdating}
                      className={cn(
                        'rounded-md border px-2 py-1 text-[11px] transition-colors disabled:cursor-not-allowed disabled:opacity-50',
                        PENDING_OUTCOME_TONES[outcome],
                      )}
                    >
                      {PENDING_OUTCOME_LABELS[outcome]}
                    </button>
                  ))}
                </div>
              )}
            </div>
          </div>
        ))}
      </div>
    </section>
  )
}

function PersonalPerformanceDesk({ summary, isLoading }: { summary: OutcomesSummary | undefined; isLoading: boolean }) {
  const bestPattern = useMemo(() => bestPersonalPattern(summary), [summary])
  const styleProfile = summary?.style_profile
  const total = summary?.total_records ?? 0
  const completed = summary?.completed ?? 0
  const pending = summary?.pending ?? 0
  const cancelled = summary?.cancelled ?? 0

  return (
    <section className="rounded-lg border border-border bg-card/55 p-4">
      <div className="flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <div className="text-sm font-semibold">내 성과 요약</div>
          <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
            판단을 저장하고 결과를 닫을수록 이 영역이 내 스타일을 보여주는 성과판이 됩니다.
          </p>
        </div>
        {isLoading && <Loader2 size={14} className="animate-spin text-muted-foreground" />}
      </div>

      {styleProfile && (
        <div className="mt-3 rounded-lg border border-violet-400/20 bg-violet-400/5 p-3">
          <div className="flex flex-wrap items-center gap-2">
            <span className="rounded-md border border-violet-400/30 bg-violet-400/10 px-2 py-1 text-[11px] font-semibold text-violet-100">
              {styleProfile.style_label}
            </span>
            <span className="text-xs text-muted-foreground">
              신뢰도 {fmtPct(styleProfile.confidence ?? 0, 0)} / 종료 기록 {styleProfile.sample_count ?? 0}건
            </span>
          </div>
          <p className="mt-2 text-xs leading-relaxed text-muted-foreground">{styleProfile.summary}</p>
        </div>
      )}

      <div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
        <PerformanceMetric label="전체 기록" value={`${total}건`} />
        <PerformanceMetric label="종료 기록" value={`${completed}건`} />
        <PerformanceMetric label="내 승률" value={completed > 0 ? fmtPct(summary?.win_rate ?? 0, 0) : '-'} tone="text-emerald-300" />
        <PerformanceMetric label="대기 / 취소" value={`${pending} / ${cancelled}`} />
        <PerformanceMetric
          label="강한 패턴"
          value={bestPattern ? `${PATTERN_NAMES[bestPattern.pattern] ?? bestPattern.pattern} ${fmtPct(bestPattern.winRate, 0)}` : '-'}
          tone="text-primary"
        />
      </div>

      {total === 0 && !isLoading && (
        <div className="mt-3 rounded-lg border border-border bg-background/60 p-3 text-xs leading-relaxed text-muted-foreground">
          아직 저장된 판단이 없습니다. 차트 화면에서 좋은 셋업을 볼 때 `신호 저장`을 눌러두면, 이후 결과가 자동/수동으로 정리되고 여기서 내 성과가 쌓입니다.
        </div>
      )}
    </section>
  )
}

function PerformanceMetric({ label, value, tone }: { label: string; value: string; tone?: string }) {
  return (
    <div className="rounded-lg border border-border bg-background/60 p-3">
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className={cn('mt-1 truncate text-sm font-semibold text-foreground', tone)}>{value}</div>
    </div>
  )
}

function filterDashboard(
  data: DashboardResponse | undefined,
  intradayMode: boolean,
  intradayView: IntradayView,
  intradayPreset: IntradayPreset,
): DashboardResponse | undefined {
  if (!intradayMode || !data) return data

  return {
    ...data,
    items: data.items.filter(item => {
      const matchesView =
        intradayView === 'all'
          ? true
          : intradayView === 'live'
            ? item.live_intraday_candidate
            : !item.live_intraday_candidate && item.intraday_collection_mode === intradayView

      const matchesPreset =
        intradayPreset === 'all'
          ? true
          : intradayPreset === 'ready-now'
            ? item.live_intraday_candidate && !item.no_signal_flag && ['confirmed', 'trigger_ready', 'breakout_watch'].includes(item.setup_stage)
            : intradayPreset === 'watch'
              ? !item.no_signal_flag && ['late_base', 'early_trigger_watch', 'base_building'].includes(item.setup_stage) && item.formation_quality >= 0.5
              : intradayPreset === 'recheck'
                ? ['stored', 'public', 'mixed', 'budget'].includes(item.intraday_collection_mode) && item.data_quality >= 0.45
                : item.intraday_collection_mode === 'cooldown' || item.no_signal_flag

      return matchesView && matchesPreset
    }),
  }
}

function buildDashboardSummary(sections: Array<DashboardResponse | undefined>) {
  const items = dedupeDashboardItems(sections)
  if (items.length === 0) {
    return {
      totalCount: 0,
      readyCount: 0,
      watchCount: 0,
      riskCount: 0,
      avgUp: 0,
      avgReadiness: 0,
      avgQuality: 0,
      bestAction: '후보가 준비되면 이 영역이 채워집니다.',
    }
  }

  const readyCount = items.filter(item => item.action_plan === 'ready_now').length
  const watchCount = items.filter(item => item.action_plan === 'watch').length
  const riskCount = items.filter(item => item.no_signal_flag || item.action_plan === 'recheck').length

  return {
    totalCount: items.length,
    readyCount,
    watchCount,
    riskCount,
    avgUp: average(items.map(item => item.p_up)),
    avgReadiness: average(items.map(item => item.trade_readiness_score ?? 0)),
    avgQuality: average(items.map(item => item.data_quality)),
    bestAction:
      readyCount > 0
        ? `즉시 검토 후보 ${readyCount}개가 먼저 보입니다.`
        : watchCount > 0
          ? `트리거 확인이 필요한 후보 ${watchCount}개가 중심입니다.`
          : '관망 또는 데이터 보강이 필요한 종목 비중이 높습니다.',
  }
}

function buildIntradaySummary(sections: Array<DashboardResponse | undefined>) {
  const items = dedupeDashboardItems(sections)
  if (items.length === 0) {
    return null
  }

  const liveCount = items.filter(item => item.live_intraday_candidate).length
  const placeholderCount = items.filter(item => item.fetch_status === 'placeholder_pending').length
  const dominantMode = dominantLabel(items.map(item => item.intraday_collection_mode), value => INTRADAY_COLLECTION_MODE_LABELS[value] ?? value)
  const dominantStage = dominantLabel(items.map(item => item.setup_stage), value => SETUP_STAGE_LABELS[value] ?? value)

  return {
    guidance:
      liveCount > 0
        ? `현재 ${liveCount}개는 live 우선 후보입니다.`
        : placeholderCount === items.length
          ? '지금은 임시 후보가 먼저 표시되고 있습니다.'
          : `${dominantMode} 중심으로 정리되고, 셋업은 ${dominantStage} 비중이 큽니다.`,
  }
}

function dedupeDashboardItems(sections: Array<DashboardResponse | undefined>) {
  const seen = new Set<string>()
  const items: DashboardItem[] = []

  for (const section of sections) {
    for (const item of section?.items ?? []) {
      const key = `${item.timeframe}-${item.symbol.code}`
      if (seen.has(key)) continue
      seen.add(key)
      items.push(item)
    }
  }

  return items
}

function buildFocusDeck(items: DashboardItem[], snapshot: Record<string, CandidateSnapshot>, isWatched: (code: string) => boolean) {
  const candidates = items.map(item => {
    const previous = snapshot[dashboardSnapshotKey(item)]
    const movement = candidateMovement(item, previous)
    const watched = isWatched(item.symbol.code)

    return {
      item,
      movement,
      watched,
      score: dashboardPriorityScore(item, movement, watched),
    }
  })

  const sortByScore = (left: FocusCandidate, right: FocusCandidate) => right.score - left.score
  const priority = candidates
    .filter(candidate => !candidate.item.no_signal_flag && candidate.item.action_plan === 'ready_now')
    .sort(sortByScore)
    .slice(0, 3)
  const usedKeys = new Set(priority.map(candidate => dashboardSnapshotKey(candidate.item)))
  const recheck = candidates
    .filter(candidate => !usedKeys.has(dashboardSnapshotKey(candidate.item)) && !candidate.item.no_signal_flag && candidate.item.action_plan !== 'ready_now')
    .sort(sortByScore)
    .slice(0, 3)

  for (const candidate of recheck) usedKeys.add(dashboardSnapshotKey(candidate.item))

  const hold = candidates
    .filter(candidate => !usedKeys.has(dashboardSnapshotKey(candidate.item)) && (candidate.item.no_signal_flag || candidate.item.action_plan === 'recheck' || candidate.movement === 'weakening'))
    .sort(sortByScore)
    .slice(0, 3)

  return {
    priority,
    recheck,
    hold,
    movementCounts: {
      new: candidates.filter(candidate => candidate.movement === 'new').length,
      steady: candidates.filter(candidate => candidate.movement === 'steady').length,
      weakening: candidates.filter(candidate => candidate.movement === 'weakening').length,
    },
  }
}

function buildWatchlistDeck(items: DashboardItem[], isWatched: (code: string) => boolean): WatchlistDeck {
  const watchedItems = items.filter(item => isWatched(item.symbol.code))
  const triggerClose = [...watchedItems]
    .filter(item => !item.no_signal_flag && ['ready_now', 'watch'].includes(item.action_plan))
    .sort(
      (left, right) =>
        dashboardPriorityScore(right, 'steady', true) - dashboardPriorityScore(left, 'steady', true),
    )
    .slice(0, 4)

  const riskClose = [...watchedItems]
    .filter(item => item.no_signal_flag || item.action_plan === 'recheck' || item.risk_flags.length > 0)
    .sort((left, right) => afterMarketPriority(right) - afterMarketPriority(left))
    .slice(0, 4)

  return { triggerClose, riskClose }
}

function buildRoutineDeck(focusDeck: ReturnType<typeof buildFocusDeck>, items: DashboardItem[], isWatched: (code: string) => boolean): RoutineDeck {
  const byScore = [...items].sort((left, right) => dashboardPriorityScore(right, 'steady', isWatched(right.symbol.code)) - dashboardPriorityScore(left, 'steady', isWatched(left.symbol.code)))
  const premarket = uniqueItems([...focusDeck.priority.map(candidate => candidate.item), ...focusDeck.recheck.map(candidate => candidate.item), ...byScore]).slice(0, 5)
  const intraday = uniqueItems([
    ...items.filter(item => item.live_intraday_candidate),
    ...focusDeck.priority.map(candidate => candidate.item),
    ...items.filter(item => !item.no_signal_flag && ['ready_now', 'watch'].includes(item.action_plan)),
    ...byScore,
  ]).slice(0, 5)
  const afterMarket = uniqueItems([
    ...focusDeck.hold.map(candidate => candidate.item),
    ...items.filter(item => item.no_signal_flag || item.action_plan === 'recheck' || item.risk_flags.length > 0),
    ...items.filter(item => item.freshness_score < 0.35),
  ])
    .sort((left, right) => afterMarketPriority(right) - afterMarketPriority(left))
    .slice(0, 5)

  return { premarket, intraday, afterMarket }
}

function uniqueItems(items: DashboardItem[]) {
  const seen = new Set<string>()
  const unique: DashboardItem[] = []

  for (const item of items) {
    const key = dashboardSnapshotKey(item)
    if (seen.has(key)) continue
    seen.add(key)
    unique.push(item)
  }

  return unique
}

function uniqueRoutineSymbols(deck: RoutineDeck) {
  return Array.from(new Set([...deck.premarket, ...deck.intraday, ...deck.afterMarket].map(item => item.symbol.code))).slice(0, 8)
}

function afterMarketPriority(item: DashboardItem) {
  return (
    (item.no_signal_flag ? 0.35 : 0) +
    (item.action_plan === 'recheck' ? 0.25 : 0) +
    Math.min(item.risk_flags.length * 0.08, 0.24) +
    (item.freshness_score < 0.35 ? 0.16 : 0) +
    (1 - (item.data_quality ?? 0)) * 0.08
  )
}

function routineActionText(item: DashboardItem, mode: 'premarket' | 'intraday' | 'afterMarket') {
  if (mode === 'premarket') {
    return item.next_trigger || item.action_plan_summary || '장전에는 가격대와 무효화 기준을 먼저 확인합니다.'
  }
  if (mode === 'intraday') {
    if (item.live_intraday_candidate) return item.live_intraday_reason || item.next_trigger || '현재가가 핵심 가격대에 붙는지 확인합니다.'
    return item.next_trigger || '현재가가 트리거 근처에 오는지 관찰합니다.'
  }
  if (item.no_signal_flag) return item.reason_summary || '신호가 약하므로 내일 후보에서 제외할지 확인합니다.'
  if (item.risk_flags.length > 0) return item.risk_flags[0]
  if (item.action_plan === 'recheck') return '무효화 또는 재확인 기준에 닿았는지 장후에 정리합니다.'
  return '오늘 판단을 기록하고 다음 스캔에서 유지 여부를 확인합니다.'
}

function bestPersonalPattern(summary: OutcomesSummary | undefined) {
  if (!summary?.by_pattern) return null
  const entries = Object.entries(summary.by_pattern)
    .filter(([, stats]) => stats.total > 0)
    .sort((left, right) => {
      const [, leftStats] = left
      const [, rightStats] = right
      return rightStats.win_rate - leftStats.win_rate || rightStats.total - leftStats.total
    })
  const best = entries[0]
  if (!best) return null
  return { pattern: best[0], winRate: best[1].win_rate, total: best[1].total }
}

function dashboardPriorityScore(item: DashboardItem, movement: CandidateMovement, watched: boolean) {
  const base =
    (item.action_priority_score ?? 0) * 0.28 +
    (item.trade_readiness_score ?? 0) * 0.24 +
    (item.entry_window_score ?? 0) * 0.18 +
    (item.freshness_score ?? 0) * 0.12 +
    (item.historical_edge_score ?? 0) * 0.08 +
    (item.data_quality ?? 0) * 0.06 +
    (item.confluence_score ?? 0) * 0.04

  const movementBonus = movement === 'new' ? 0.12 : movement === 'weakening' ? -0.12 : 0
  const watchBonus = watched ? 0.08 : 0
  const penalty = item.no_signal_flag ? 0.18 : item.action_plan === 'recheck' ? 0.08 : 0

  return base + movementBonus + watchBonus - penalty
}

function candidateMovement(item: DashboardItem, previous: CandidateSnapshot | undefined): CandidateMovement {
  if (!previous) return 'new'

  const currentScore = item.action_priority_score ?? item.trade_readiness_score ?? 0
  if (item.no_signal_flag || item.action_plan === 'recheck') return 'weakening'
  if (currentScore < previous.score - 0.08) return 'weakening'
  return 'steady'
}

function readDashboardSnapshot(timeframe: Timeframe): Record<string, CandidateSnapshot> {
  if (typeof window === 'undefined') return {}

  try {
    const raw = window.localStorage.getItem(`${DASHBOARD_SNAPSHOT_PREFIX}:${timeframe}`)
    if (!raw) return {}
    return JSON.parse(raw) as Record<string, CandidateSnapshot>
  } catch {
    return {}
  }
}

function writeDashboardSnapshot(timeframe: Timeframe, items: DashboardItem[], updatedAt?: string) {
  if (typeof window === 'undefined') return

  const snapshot = items.reduce<Record<string, CandidateSnapshot>>((acc, item) => {
    acc[dashboardSnapshotKey(item)] = {
      score: item.action_priority_score ?? item.trade_readiness_score ?? 0,
      actionPlan: item.action_plan,
      noSignal: item.no_signal_flag,
      updatedAt: updatedAt ?? new Date().toISOString(),
    }
    return acc
  }, {})

  try {
    window.localStorage.setItem(`${DASHBOARD_SNAPSHOT_PREFIX}:${timeframe}`, JSON.stringify(snapshot))
  } catch {
    // Local storage is a convenience only; the dashboard should still render without it.
  }
}

function dashboardSnapshotKey(item: DashboardItem) {
  return `${item.timeframe}:${item.symbol.code}`
}

function average(values: number[]) {
  if (values.length === 0) return 0
  return values.reduce((sum, value) => sum + value, 0) / values.length
}

function dominantLabel(values: string[], formatter?: (value: string) => string) {
  if (values.length === 0) return '-'

  const counts = values.reduce<Record<string, number>>((acc, value) => {
    acc[value] = (acc[value] ?? 0) + 1
    return acc
  }, {})

  const winner = Object.entries(counts).sort((left, right) => right[1] - left[1])[0]?.[0]
  if (!winner) return '-'
  return formatter ? formatter(winner) : winner
}

function statusHeadline(status: ScanStatusResponse | undefined) {
  if (!status) return '불러오는 중'
  if (status.is_running) return '스캔 진행 중'
  if (status.status === 'warming') return '백그라운드 준비 중'
  if (status.status === 'ready') return '준비 완료'
  if (status.status === 'error') return '확인 필요'
  return '대기 중'
}

function statusSubline(status: ScanStatusResponse | undefined, timeframe: Timeframe) {
  if (!status) return `${timeframeLabel(timeframe)} 상태를 불러오는 중입니다.`
  if (status.is_running) {
    const cachedCount = status.cached_result_count ?? 0
    return cachedCount > 0
      ? `재스캔 진행 중입니다 (보통 2~3분). 기존 ${cachedCount}개 결과는 그대로 보입니다.`
      : `${timeframeLabel(timeframe)} 스캔 진행 중입니다. 보통 2~3분 소요됩니다.`
  }
  if (status.status === 'warming' && (status.cached_result_count ?? 0) === 0) {
    return `${timeframeLabel(timeframe)} 결과를 백그라운드에서 준비 중입니다. 임시 후보가 먼저 보일 수 있습니다.`
  }
  if (status.candidate_source === 'placeholder_seed') {
    return `지금은 ${timeframeLabel(timeframe)} 임시 후보를 먼저 보여주고 있으며, 실제 분석 결과가 준비되면 자동으로 교체됩니다.`
  }
  if (status.intraday_live_phase === 'off_hours') {
    return '장외 시간에는 live 분봉 후보를 일부러 비우고 저장 데이터 기준으로 보수적으로 보여줍니다.'
  }
  if (status.last_error) {
    return `최근 오류가 있었지만 마지막 캐시 결과는 유지되고 있습니다. 오류: ${status.last_error}`
  }
  return `${timeframeLabel(timeframe)} 기준 최근 스캔 결과를 표시하고 있습니다.`
}

function statusLabel(status: string | undefined): string {
  switch (status) {
    case 'running':
      return '실행 중'
    case 'queued':
      return '대기 중'
    case 'warming':
      return '준비 중'
    case 'ready':
      return '준비 완료'
    case 'error':
      return '오류'
    default:
      return '대기'
  }
}

function candidateSourceLabel(source: string | null | undefined): string {
  switch (source) {
    case 'daily_seed':
      return '일봉 우선 후보'
    case 'fallback_seed':
      return 'fallback 후보'
    case 'placeholder_seed':
      return '임시 후보'
    case 'background_pending':
      return '백그라운드 대기'
    case 'cache_ready':
      return '캐시 완료'
    case 'krx_universe':
      return 'KRX 전체 스캔'
    case 'krx_universe_fdr':
      return 'KRX 대체 스캔 (FDR)'
    case 'krx_universe_fallback':
      return 'KRX 대체 유니버스'
    case 'static_fallback':
      return '⚠️ 15종목 제한 스캔'
    case 'fallback':
      return '기본 후보'
    default:
      return '-'
  }
}

function candidateSourceWarning(source: string | null | undefined): string | null {
  if (source === 'static_fallback') {
    return 'pykrx와 FDR 유니버스 로드가 모두 실패해 하드코딩된 15개 종목만 스캔됐습니다. 백엔드 로그를 확인하세요.'
  }
  if (source === 'krx_universe_fdr') {
    return 'pykrx 시가총액 기준 스캔 실패 — FDR 대체 유니버스로 스캔됐습니다.'
  }
  return null
}

function getDefaultSectionEmptyMessage(status: ScanStatusResponse | undefined, timeframe: Timeframe): string | undefined {
  if (!status) return undefined
  if (status.status === 'warming' && (status.cached_result_count ?? 0) === 0) {
    return `${timeframeLabel(timeframe)} 결과를 백그라운드에서 준비 중입니다. 지금은 카드가 비어 보여도 정상입니다.`
  }
  if (status.candidate_source === 'placeholder_seed') {
    return `${timeframeLabel(timeframe)} 임시 후보를 먼저 보여주는 단계입니다. 실제 분석이 끝나면 카드가 자동으로 채워집니다.`
  }
  if (status.candidate_source === 'fallback_seed') {
    return `${timeframeLabel(timeframe)} fallback 후보 기준이라 지금은 결과가 적게 보일 수 있습니다.`
  }
  return undefined
}

function getLiveSectionEmptyMessage(status: ScanStatusResponse | undefined, timeframe: Timeframe): string | undefined {
  if (!status) return undefined
  if (status.status === 'warming' && (status.cached_result_count ?? 0) === 0) {
    return `${timeframeLabel(timeframe)} live 후보를 수집 중입니다. 준비가 끝나면 자동으로 채워집니다.`
  }
  if (status.intraday_live_phase === 'off_hours') {
    return '장외 시간에는 live 분봉 후보를 비워두는 것이 정상입니다. 대신 형성 중 후보를 먼저 확인해 보세요.'
  }
  if (status.candidate_source === 'placeholder_seed') {
    return `${timeframeLabel(timeframe)} 임시 후보가 먼저 표시되는 단계라 live 후보 영역이 잠시 비어 있을 수 있습니다.`
  }
  if ((status.intraday_live_candidate_limit ?? 0) === 0) {
    return '지금 시간대 기준으로는 live 분봉까지 우선 확인할 후보가 아직 없습니다.'
  }
  return '현재 조건에서 live 분봉으로 바로 볼 만한 후보가 없습니다.'
}
