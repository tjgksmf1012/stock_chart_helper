import { useEffect, useMemo, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Activity, Layers3, Loader2, RefreshCw, Sparkles } from 'lucide-react'

import { DashboardSection } from '@/components/dashboard/DashboardSection'
import { Card } from '@/components/ui/Card'
import { QueryError } from '@/components/ui/QueryError'
import { dashboardApi } from '@/lib/api'
import { DEFAULT_TIMEFRAME, TIMEFRAME_OPTIONS, timeframeLabel } from '@/lib/timeframes'
import { cn, fmtDateTime, fmtPct, INTRADAY_COLLECTION_MODE_LABELS, SETUP_STAGE_LABELS } from '@/lib/utils'
import { useAppStore } from '@/store/app'
import type { DashboardItem, DashboardResponse, ScanStatusResponse, Timeframe } from '@/types/api'

type IntradayView = 'all' | 'live' | 'stored' | 'public' | 'mixed' | 'cooldown'
type IntradayPreset = 'all' | 'ready-now' | 'watch' | 'recheck' | 'cooling'

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
  const { selectedTimeframe, setTimeframe } = useAppStore()
  const timeframe = selectedTimeframe ?? DEFAULT_TIMEFRAME
  const intradayMode = ['60m', '30m', '15m', '1m'].includes(timeframe)
  const [isTriggeringScan, setIsTriggeringScan] = useState(false)
  const [intradayView, setIntradayView] = useState<IntradayView>('all')
  const [intradayPreset, setIntradayPreset] = useState<IntradayPreset>('all')
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

          <button
            onClick={triggerScan}
            disabled={Boolean(isScanActive)}
            className="inline-flex w-full items-center justify-center gap-2 rounded-lg bg-primary px-4 py-2.5 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {isScanActive ? <Loader2 size={14} className="animate-spin" /> : <RefreshCw size={14} />}
            {isScanActive ? `${timeframeLabel(timeframe)} 스캔 진행 중` : `${timeframeLabel(timeframe)} 다시 스캔`}
          </button>

          <div className="rounded-lg border border-border bg-background/60 p-3 text-xs leading-relaxed text-muted-foreground">
            {statusSubline(status, timeframe)}
          </div>

          {statusQ.isError && !statusQ.isLoading && (
            <QueryError compact message="스캔 상태를 불러오지 못했습니다." onRetry={() => statusQ.refetch()} />
          )}
        </Card>
      </section>

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
      return 'KRX 전체 유니버스'
    case 'krx_universe_fallback':
      return 'KRX 대체 유니버스'
    case 'fallback':
      return '기본 후보'
    default:
      return '-'
  }
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
