import { useEffect, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Activity, AlertTriangle, Layers3, Loader2, RefreshCw } from 'lucide-react'

import { DashboardSection } from '@/components/dashboard/DashboardSection'
import { Card } from '@/components/ui/Card'
import { dashboardApi } from '@/lib/api'
import { DEFAULT_TIMEFRAME, TIMEFRAME_OPTIONS, timeframeLabel } from '@/lib/timeframes'
import { fmtDateTime } from '@/lib/utils'
import { useAppStore } from '@/store/app'
import type { DashboardItem, DashboardResponse } from '@/types/api'

type IntradayView = 'all' | 'live' | 'stored' | 'public' | 'mixed' | 'cooldown'
type IntradayPreset = 'all' | 'ready-now' | 'watch' | 'recheck' | 'cooling'

export default function DashboardPage() {
  const { selectedTimeframe, setTimeframe } = useAppStore()
  const timeframe = selectedTimeframe ?? DEFAULT_TIMEFRAME
  const intradayMode = ['60m', '30m', '15m', '1m'].includes(timeframe)
  const opts = { staleTime: 30_000, refetchInterval: 60_000 }
  const [isTriggeringScan, setIsTriggeringScan] = useState(false)
  const [intradayView, setIntradayView] = useState<IntradayView>('all')
  const [intradayPreset, setIntradayPreset] = useState<IntradayPreset>('all')
  const lastFinishedAtRef = useRef<string | null>(null)

  const longQ = useQuery({ queryKey: ['dashboard', timeframe, 'long'], queryFn: () => dashboardApi.longHigh(timeframe), ...opts })
  const shortQ = useQuery({ queryKey: ['dashboard', timeframe, 'short'], queryFn: () => dashboardApi.shortHigh(timeframe), ...opts })
  const simQ = useQuery({ queryKey: ['dashboard', timeframe, 'sim'], queryFn: () => dashboardApi.highSimilarity(timeframe), ...opts })
  const armedQ = useQuery({ queryKey: ['dashboard', timeframe, 'armed'], queryFn: () => dashboardApi.armed(timeframe), ...opts })
  const formingQ = useQuery({ queryKey: ['dashboard', timeframe, 'forming'], queryFn: () => dashboardApi.forming(timeframe), ...opts })
  const liveQ = useQuery({
    queryKey: ['dashboard', timeframe, 'live'],
    queryFn: () => dashboardApi.liveIntraday(timeframe),
    enabled: intradayMode,
    ...opts,
  })
  const noSigQ = useQuery({ queryKey: ['dashboard', timeframe, 'nosig'], queryFn: () => dashboardApi.noSignal(timeframe), ...opts })
  const statusQ = useQuery({
    queryKey: ['dashboard', timeframe, 'scan-status'],
    queryFn: () => dashboardApi.scanStatus(timeframe),
    staleTime: 5_000,
    refetchInterval: 15_000,
  })

  const isRefreshing =
    longQ.isFetching ||
    shortQ.isFetching ||
    simQ.isFetching ||
    armedQ.isFetching ||
    formingQ.isFetching ||
    liveQ.isFetching ||
    noSigQ.isFetching

  const isScanActive = isTriggeringScan || statusQ.data?.is_running

  const refreshBoards = () => {
    longQ.refetch()
    shortQ.refetch()
    simQ.refetch()
    armedQ.refetch()
    formingQ.refetch()
    if (intradayMode) liveQ.refetch()
    noSigQ.refetch()
    statusQ.refetch()
  }

  const triggerScan = async () => {
    setIsTriggeringScan(true)
    try {
      await dashboardApi.refreshScan(timeframe)
      statusQ.refetch()
    } finally {
      setIsTriggeringScan(false)
    }
  }

  useEffect(() => {
    const lastFinishedAt = statusQ.data?.last_finished_at
    if (!lastFinishedAt) return

    if (!lastFinishedAtRef.current) {
      lastFinishedAtRef.current = lastFinishedAt
      return
    }

    if (lastFinishedAtRef.current !== lastFinishedAt && statusQ.data?.status === 'ready') {
      lastFinishedAtRef.current = lastFinishedAt
      refreshBoards()
    }
  }, [statusQ.data?.last_finished_at, statusQ.data?.status])

  useEffect(() => {
    setIntradayView('all')
    setIntradayPreset('all')
  }, [timeframe])

  const filterDashboard = (data: DashboardResponse | undefined): DashboardResponse | undefined => {
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
              ? item.live_intraday_candidate &&
                !item.no_signal_flag &&
                ['confirmed', 'trigger_ready', 'breakout_watch'].includes(item.setup_stage)
              : intradayPreset === 'watch'
                ? !item.no_signal_flag &&
                  ['late_base', 'early_trigger_watch', 'base_building'].includes(item.setup_stage) &&
                  item.formation_quality >= 0.5
                : intradayPreset === 'recheck'
                  ? ['stored', 'public', 'mixed', 'budget'].includes(item.intraday_collection_mode) &&
                    item.data_quality >= 0.45
                  : item.intraday_collection_mode === 'cooldown' || item.no_signal_flag

        return matchesView && matchesPreset
      }),
    }
  }

  const filteredSections = [
    filterDashboard(longQ.data),
    filterDashboard(armedQ.data),
    filterDashboard(liveQ.data),
    filterDashboard(formingQ.data),
    filterDashboard(simQ.data),
    filterDashboard(shortQ.data),
    filterDashboard(noSigQ.data),
  ]

  const intradaySummary = intradayMode ? buildIntradaySummary(filteredSections) : null

  return (
    <div className="space-y-8">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <h1 className="text-xl font-bold">대시보드</h1>
          <p className="mt-0.5 text-xs text-muted-foreground">
            KRX 기준으로 타임프레임별 상승 확률, 패턴 완성 임박도, 상위 추세 정렬, 데이터 품질을 함께 보는 메인 스캔 화면입니다.
          </p>
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

      <Card className="flex items-start gap-3 border-primary/20 bg-primary/5 p-4">
        <Layers3 size={16} className="mt-0.5 text-primary" />
        <div className="space-y-1">
          <div className="text-sm font-semibold">완성 신호와 형성 후보를 분리해서 봅니다</div>
          <p className="text-xs leading-relaxed text-muted-foreground">
            이제 카드 정렬은 단순 확률만이 아니라 형성 품질, 상위 타임프레임 정렬, 표본 신뢰도, 데이터 품질까지 함께 반영합니다.
            이미 끝난 패턴과 아직 베이스를 만드는 후보를 같은 강도로 보지 않도록 나눠두었습니다.
          </p>
        </div>
      </Card>

      {intradayMode && (
        <Card className="flex items-start gap-3 border-yellow-500/30 bg-yellow-500/5 p-4">
          <AlertTriangle size={16} className="mt-0.5 text-yellow-400" />
          <div className="space-y-1">
            <div className="text-sm font-semibold text-yellow-300">분봉은 후보 압축 후 보수적으로 해석합니다</div>
            <p className="text-xs leading-relaxed text-muted-foreground">
              {timeframeLabel(timeframe)} 스캔은 일봉 상위 후보를 먼저 좁힌 뒤 들어갑니다. 분봉은 KIS와 저장 캐시 도움을 받더라도
              일봉·주봉보다 불안정할 수 있어서, 형성 품질과 상위 정렬이 약하면 쉽게 No Signal로 내려가도록 설계했습니다.
            </p>
          </div>
        </Card>
      )}

      {intradayMode && (
        <Card className="flex items-start gap-3 border-sky-500/20 bg-sky-500/5 p-4">
          <Activity size={16} className="mt-0.5 text-sky-300" />
          <div className="space-y-1">
            <div className="text-sm font-semibold text-sky-200">Live KIS 후보는 시간대와 품질 기준으로만 열립니다</div>
            <p className="text-xs leading-relaxed text-muted-foreground">
              장초반과 마감 전에는 live 후보를 더 넓게 쓰고, 점심장과 장외에는 저장 분봉과 공개 소스를 우선합니다.
              후보 안에서도 진입 적합도, 완성 임박도, 유동성, 신호 최신성이 높은 종목이 먼저 live 분봉을 사용합니다.
            </p>
          </div>
        </Card>
      )}

      {intradayMode && (
        <div className="flex flex-wrap gap-2">
          {([
            ['all', '전체'],
            ['live', 'live'],
            ['stored', 'stored'],
            ['public', 'public'],
            ['mixed', 'mixed'],
            ['cooldown', 'cooldown'],
          ] as Array<[IntradayView, string]>).map(([value, label]) => (
            <button
              key={value}
              onClick={() => setIntradayView(value)}
              className={`rounded-md px-2.5 py-1.5 text-xs transition-colors ${
                intradayView === value
                  ? 'bg-primary text-primary-foreground'
                  : 'border border-border bg-card text-muted-foreground hover:text-foreground'
              }`}
            >
              {label}
            </button>
          ))}
        </div>
      )}

      {intradayMode && (
        <div className="flex flex-wrap gap-2">
          {([
            ['all', '프리셋 전체'],
            ['ready-now', '바로 볼 종목'],
            ['watch', '지켜볼 후보'],
            ['recheck', '재확인 필요'],
            ['cooling', '냉각/관망'],
          ] as Array<[IntradayPreset, string]>).map(([value, label]) => (
            <button
              key={value}
              onClick={() => setIntradayPreset(value)}
              className={`rounded-md px-2.5 py-1.5 text-xs transition-colors ${
                intradayPreset === value
                  ? 'bg-emerald-600 text-white'
                  : 'border border-border bg-card text-muted-foreground hover:text-foreground'
              }`}
            >
              {label}
            </button>
          ))}
        </div>
      )}

      {intradayMode && intradaySummary && (
        <Card className="space-y-4">
          <div>
            <div className="text-sm font-semibold">프리셋 요약</div>
            <p className="mt-1 text-xs text-muted-foreground">
              현재 모드와 프리셋으로 걸러진 후보를 빠르게 읽을 수 있도록 요약한 숫자입니다.
            </p>
          </div>

          <div className="grid grid-cols-2 gap-3 xl:grid-cols-6">
            <StatusCell label="후보 수" value={`${intradaySummary.totalCount}개`} />
            <StatusCell label="live 추적" value={`${intradaySummary.liveCount}개`} />
            <StatusCell label="confirmed" value={`${intradaySummary.confirmedCount}개`} />
            <StatusCell label="관망/No Signal" value={`${intradaySummary.noSignalCount}개`} />
            <StatusCell label="평균 품질" value={`${Math.round(intradaySummary.avgQuality * 100)}%`} />
            <StatusCell label="평균 진입 적합도" value={`${Math.round(intradaySummary.avgEntry * 100)}%`} />
          </div>
        </Card>
      )}

      {intradayMode && intradaySummary && (
        <Card className="space-y-4">
          <div>
            <div className="text-sm font-semibold">프리셋 컨텍스트</div>
            <p className="mt-1 text-xs text-muted-foreground">
              현재 프리셋 기준으로 우세한 운용 모드와 세팅 단계를 같이 읽어주는 보조 요약입니다.
            </p>
          </div>

          <div className="grid grid-cols-2 gap-3 xl:grid-cols-4">
            <StatusCell label="평균 edge" value={`${Math.round(intradaySummary.avgEdge * 100)}%`} />
            <StatusCell label="평균 손익비" value={intradaySummary.avgRewardRisk.toFixed(2)} />
            <StatusCell label="우세 운용 모드" value={intradaySummary.dominantMode} />
            <StatusCell label="우세 세팅 단계" value={intradaySummary.dominantStage} />
          </div>

          <div className="rounded-lg border border-cyan-500/20 bg-cyan-500/5 p-3 text-xs text-cyan-100">
            {intradaySummary.guidance}
          </div>

          <div className="flex flex-wrap gap-2">
            <button
              onClick={() => {
                setIntradayView('all')
                setIntradayPreset('all')
              }}
              className="rounded-md border border-border bg-card px-2.5 py-1.5 text-xs text-muted-foreground transition-colors hover:text-foreground"
            >
              전체 보기
            </button>
            <button
              onClick={() => setIntradayView('live')}
              className="rounded-md border border-emerald-500/30 bg-emerald-500/10 px-2.5 py-1.5 text-xs text-emerald-100 transition-colors hover:bg-emerald-500/15"
            >
              live만 보기
            </button>
            <button
              onClick={() => setIntradayPreset('ready-now')}
              className="rounded-md border border-sky-500/30 bg-sky-500/10 px-2.5 py-1.5 text-xs text-sky-100 transition-colors hover:bg-sky-500/15"
            >
              confirmed/즉시 대응
            </button>
            <button
              onClick={() => setIntradayPreset('watch')}
              className="rounded-md border border-violet-500/30 bg-violet-500/10 px-2.5 py-1.5 text-xs text-violet-100 transition-colors hover:bg-violet-500/15"
            >
              forming/watch
            </button>
            <button
              onClick={() => setIntradayPreset('cooling')}
              className="rounded-md border border-amber-500/30 bg-amber-500/10 px-2.5 py-1.5 text-xs text-amber-100 transition-colors hover:bg-amber-500/15"
            >
              관망/냉각
            </button>
          </div>
        </Card>
      )}

      <Card className="space-y-4">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
          <div className="space-y-1">
            <div className="flex items-center gap-2 text-sm font-semibold">
              <Activity size={15} className={statusQ.data?.is_running ? 'text-primary' : 'text-muted-foreground'} />
              {timeframeLabel(timeframe)} 스캔 상태
            </div>
            <p className="text-xs text-muted-foreground">
              최근 스캔 결과와 후보 선정 방식을 확인하고, 필요하면 현재 타임프레임 기준으로 다시 스캔할 수 있습니다.
            </p>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={refreshBoards}
              className="flex items-center gap-1.5 text-xs text-muted-foreground transition-colors hover:text-foreground"
            >
              <RefreshCw size={13} className={isRefreshing ? 'animate-spin' : ''} />
              새로고침
            </button>
            <button
              onClick={triggerScan}
              disabled={Boolean(isScanActive)}
              className="inline-flex items-center justify-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {isScanActive ? <Loader2 size={14} className="animate-spin" /> : <RefreshCw size={14} />}
              {isScanActive ? '스캔 진행 중' : '현재 타임프레임 다시 스캔'}
            </button>
          </div>
        </div>

        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <StatusCell label="상태" value={statusLabel(statusQ.data?.status)} />
          <StatusCell label="마지막 완료" value={fmtDateTime(statusQ.data?.last_finished_at)} />
          <StatusCell label="캐시 결과 수" value={`${statusQ.data?.cached_result_count ?? 0}개`} />
          <StatusCell label="유니버스" value={statusQ.data?.universe_size ? `${statusQ.data.universe_size}개` : '-'} />
        </div>

        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <StatusCell label="후보 선정" value={candidateSourceLabel(statusQ.data?.candidate_source)} />
          <StatusCell label="후보 개수" value={statusQ.data?.candidate_count ? `${statusQ.data.candidate_count}개` : '-'} />
          <StatusCell label="실행 주체" value={sourceLabel(statusQ.data?.source)} />
          <StatusCell label="소요 시간" value={statusQ.data?.duration_ms ? `${(statusQ.data.duration_ms / 1000).toFixed(1)}초` : '-'} />
        </div>

        {intradayMode && (
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <StatusCell label="Live 단계" value={livePhaseLabel(statusQ.data?.intraday_live_phase)} />
            <StatusCell
              label="Live 사용 수"
              value={statusQ.data?.intraday_live_candidate_count != null ? `${statusQ.data.intraday_live_candidate_count}개` : '-'}
            />
            <StatusCell
              label="Live 한도"
              value={statusQ.data?.intraday_live_candidate_limit != null ? `${statusQ.data.intraday_live_candidate_limit}개` : '-'}
            />
            <StatusCell label="운용 메모" value={livePhaseNote(statusQ.data?.intraday_live_phase)} />
          </div>
        )}

        {statusQ.data?.last_error && (
          <div className="rounded-lg border border-red-500/20 bg-red-500/5 p-3 text-xs text-red-200">
            최근 오류: {statusQ.data.last_error}
          </div>
        )}
      </Card>

      <DashboardSection
        title="상승 확률 상위"
        subtitle="상승 확률, 형성 품질, 상위 타임프레임 정렬이 함께 좋은 종목입니다."
        data={filterDashboard(longQ.data)}
        isLoading={longQ.isLoading}
        intradayPreset={intradayMode ? intradayPreset : undefined}
      />

      <DashboardSection
        title="패턴 완성 임박"
        subtitle="거의 다 만들어졌고 돌파 감시 단계에 가까운 후보입니다."
        data={filterDashboard(armedQ.data)}
        isLoading={armedQ.isLoading}
        intradayPreset={intradayMode ? intradayPreset : undefined}
      />

      {intradayMode && (
        <DashboardSection
          title="Live 분봉 후보"
          subtitle="지금 실제 live KIS 분봉까지 열어 확인 중인 후보입니다. 저장 분봉이나 공개 소스 기반 후보보다 우선 관찰할 묶음입니다."
          data={filterDashboard(liveQ.data)}
          isLoading={liveQ.isLoading}
          intradayPreset={intradayPreset}
        />
      )}

      <DashboardSection
        title="형성 중 후보"
        subtitle="아직 forming 상태지만 상위 추세와 구조가 받쳐주는 베이스 후보입니다. 완성 신호가 아니라 관찰용 후보군으로 보세요."
        data={filterDashboard(formingQ.data)}
        isLoading={formingQ.isLoading}
        intradayPreset={intradayMode ? intradayPreset : undefined}
      />

      <DashboardSection
        title="교과서 유사형 패턴"
        subtitle="교과서와의 유사도가 높은 구조입니다. 이제는 형성 품질과 최신성도 함께 보정합니다."
        data={filterDashboard(simQ.data)}
        isLoading={simQ.isLoading}
        intradayPreset={intradayMode ? intradayPreset : undefined}
      />

      <DashboardSection
        title="하락 확률 상위"
        subtitle="약세 패턴과 하락 방향 정렬이 함께 들어온 종목입니다."
        data={filterDashboard(shortQ.data)}
        isLoading={shortQ.isLoading}
        intradayPreset={intradayMode ? intradayPreset : undefined}
      />

      <DashboardSection
        title="No Signal / 관망"
        subtitle="데이터 품질, 표본 신뢰도, 손익비, 형성 과정 점수 중 하나 이상이 부족해 보수적으로 관망 처리한 종목입니다."
        data={filterDashboard(noSigQ.data)}
        isLoading={noSigQ.isLoading}
        intradayPreset={intradayMode ? intradayPreset : undefined}
      />
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

function buildIntradaySummary(sections: Array<DashboardResponse | undefined>) {
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

  if (items.length === 0) {
    return {
      totalCount: 0,
      liveCount: 0,
      confirmedCount: 0,
      noSignalCount: 0,
      avgQuality: 0,
      avgEntry: 0,
      avgEdge: 0,
      avgRewardRisk: 0,
      dominantMode: '-',
      dominantStage: '-',
      guidance: '현재 프리셋에 맞는 후보가 많지 않습니다. 조건을 조금 완화하거나 다른 타임프레임도 함께 보는 편이 좋습니다.',
    }
  }

  const totals = items.reduce(
    (acc, item) => {
      acc.liveCount += item.live_intraday_candidate ? 1 : 0
      acc.confirmedCount += item.state === 'confirmed' ? 1 : 0
      acc.noSignalCount += item.no_signal_flag ? 1 : 0
      acc.qualitySum += item.data_quality
      acc.entrySum += item.entry_score
      acc.edgeSum += item.historical_edge_score
      acc.rewardRiskSum += item.reward_risk_ratio
      acc.modeCounts[item.intraday_collection_mode] = (acc.modeCounts[item.intraday_collection_mode] ?? 0) + 1
      acc.stageCounts[item.setup_stage] = (acc.stageCounts[item.setup_stage] ?? 0) + 1
      return acc
    },
    {
      liveCount: 0,
      confirmedCount: 0,
      noSignalCount: 0,
      qualitySum: 0,
      entrySum: 0,
      edgeSum: 0,
      rewardRiskSum: 0,
      modeCounts: {} as Record<string, number>,
      stageCounts: {} as Record<string, number>,
    },
  )

  return {
    totalCount: items.length,
    liveCount: totals.liveCount,
    confirmedCount: totals.confirmedCount,
    noSignalCount: totals.noSignalCount,
    avgQuality: totals.qualitySum / items.length,
    avgEntry: totals.entrySum / items.length,
    avgEdge: totals.edgeSum / items.length,
    avgRewardRisk: totals.rewardRiskSum / items.length,
    dominantMode: dominantLabel(totals.modeCounts),
    dominantStage: dominantLabel(totals.stageCounts),
    guidance: buildSummaryGuidance(items),
  }
}

function dominantLabel(counts: Record<string, number>): string {
  const entries = Object.entries(counts)
  if (entries.length === 0) return '-'
  return entries.sort((a, b) => b[1] - a[1])[0][0]
}

function buildSummaryGuidance(items: DashboardItem[]): string {
  const liveCount = items.filter(item => item.live_intraday_candidate).length
  const confirmedCount = items.filter(item => item.state === 'confirmed').length
  const avgEdge = items.reduce((sum, item) => sum + item.historical_edge_score, 0) / items.length
  const avgRewardRisk = items.reduce((sum, item) => sum + item.reward_risk_ratio, 0) / items.length

  if (liveCount >= Math.max(2, Math.round(items.length * 0.4)) && confirmedCount >= Math.max(1, Math.round(items.length * 0.25))) {
    return 'live 추적 비중과 confirmed 비중이 모두 괜찮습니다. 무효화 기준만 빠르게 점검하고 상단 후보부터 보면 됩니다.'
  }

  if (avgEdge >= 0.58 && avgRewardRisk >= 1.4) {
    return '평균 edge와 손익비는 무난한 편입니다. 넓게 보기보다 상위 몇 개를 깊게 검토하는 흐름이 좋습니다.'
  }

  return '확인 단계의 후보가 더 많은 상태입니다. 진입보다 트리거 재확인과 품질 회복 여부를 우선 보는 편이 좋습니다.'
}

function statusLabel(status: string | undefined): string {
  switch (status) {
    case 'running':
      return '실행 중'
    case 'queued':
      return '대기 중'
    case 'warming':
      return '예열 중'
    case 'ready':
      return '준비됨'
    case 'error':
      return '오류'
    default:
      return '대기'
  }
}

function sourceLabel(source: string | null | undefined): string {
  switch (source) {
    case 'manual':
      return '수동 실행'
    case 'background':
      return '백그라운드'
    case 'scheduled':
      return '예약 실행'
    case 'fallback':
      return '초기 예열'
    default:
      return '-'
  }
}

function livePhaseLabel(phase: string | null | undefined): string {
  switch (phase) {
    case 'open_drive':
      return '장초반 확대'
    case 'regular_session':
      return '일반 장중'
    case 'midday':
      return '점심장 축소'
    case 'closing_drive':
      return '마감 전 확대'
    case 'off_hours':
      return '장외 절약 모드'
    default:
      return '-'
  }
}

function livePhaseNote(phase: string | null | undefined): string {
  switch (phase) {
    case 'open_drive':
      return '초기 추세 확인 구간이라 live 후보를 넓게 봅니다.'
    case 'regular_session':
      return '기본 후보만 live로 확인하고 나머지는 절약 모드로 둡니다.'
    case 'midday':
      return '노이즈가 많은 시간대라 live 사용을 더 줄입니다.'
    case 'closing_drive':
      return '마감 전 재가속 확인을 위해 live 후보를 다시 늘립니다.'
    case 'off_hours':
      return '장외에는 저장 분봉과 공개 소스를 우선 사용합니다.'
    default:
      return '-'
  }
}

function candidateSourceLabel(source: string | null | undefined): string {
  switch (source) {
    case 'daily_seed':
      return '일봉 상위 후보'
    case 'krx_universe':
      return 'KRX 유니버스'
    case 'krx_universe_fallback':
      return 'KRX 대체 유니버스'
    case 'fallback':
      return '기본 후보'
    default:
      return '-'
  }
}
