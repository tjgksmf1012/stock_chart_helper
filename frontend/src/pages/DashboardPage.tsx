import { useEffect, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Activity, AlertTriangle, Layers3, Loader2, RefreshCw } from 'lucide-react'

import { DashboardSection } from '@/components/dashboard/DashboardSection'
import { Card } from '@/components/ui/Card'
import { dashboardApi } from '@/lib/api'
import { DEFAULT_TIMEFRAME, TIMEFRAME_OPTIONS, timeframeLabel } from '@/lib/timeframes'
import { fmtDateTime } from '@/lib/utils'
import { useAppStore } from '@/store/app'
import type { DashboardItem, DashboardResponse, ScanStatusResponse, Timeframe } from '@/types/api'

type IntradayView = 'all' | 'live' | 'stored' | 'public' | 'mixed' | 'cooldown'
type IntradayPreset = 'all' | 'ready-now' | 'watch' | 'recheck' | 'cooling'

const INTRADAY_VIEW_OPTIONS: Array<[IntradayView, string]> = [
  ['all', '전체'],
  ['live', 'live'],
  ['stored', '저장'],
  ['public', '공개'],
  ['mixed', '혼합'],
  ['cooldown', '쿨다운'],
]

const INTRADAY_PRESET_OPTIONS: Array<[IntradayPreset, string]> = [
  ['all', '프리셋 전체'],
  ['ready-now', '지금 볼 종목'],
  ['watch', '지켜볼 후보'],
  ['recheck', '재확인 필요'],
  ['cooling', '관망 / 정리'],
]

export default function DashboardPage() {
  const { selectedTimeframe, setTimeframe } = useAppStore()
  const timeframe = selectedTimeframe ?? DEFAULT_TIMEFRAME
  const intradayMode = ['60m', '30m', '15m', '1m'].includes(timeframe)
  const opts = { staleTime: 30_000, refetchInterval: 60_000 }
  const [isTriggeringScan, setIsTriggeringScan] = useState(false)
  const [intradayView, setIntradayView] = useState<IntradayView>('all')
  const [intradayPreset, setIntradayPreset] = useState<IntradayPreset>('all')
  const lastFinishedAtRef = useRef<string | null>(null)
  const lastStatusRef = useRef<string | null>(null)

  const overviewQ = useQuery({
    queryKey: ['dashboard', timeframe, 'overview'],
    queryFn: () => dashboardApi.overview(timeframe),
    ...opts,
  })
  const longQ = useQuery({
    queryKey: ['dashboard', timeframe, 'long-high-probability'],
    queryFn: () => dashboardApi.longHigh(timeframe),
    ...opts,
    enabled: false,
  })
  const armedQ = useQuery({
    queryKey: ['dashboard', timeframe, 'pattern-armed'],
    queryFn: () => dashboardApi.armed(timeframe),
    ...opts,
    enabled: false,
  })
  const liveQ = useQuery({
    queryKey: ['dashboard', timeframe, 'live-intraday-candidates'],
    queryFn: () => dashboardApi.liveIntraday(timeframe),
    ...opts,
    enabled: false,
  })
  const formingQ = useQuery({
    queryKey: ['dashboard', timeframe, 'forming-candidates'],
    queryFn: () => dashboardApi.forming(timeframe),
    ...opts,
    enabled: false,
  })
  const simQ = useQuery({
    queryKey: ['dashboard', timeframe, 'high-textbook-similarity'],
    queryFn: () => dashboardApi.highSimilarity(timeframe),
    ...opts,
    enabled: false,
  })
  const shortQ = useQuery({
    queryKey: ['dashboard', timeframe, 'short-high-probability'],
    queryFn: () => dashboardApi.shortHigh(timeframe),
    ...opts,
    enabled: false,
  })
  const noSigQ = useQuery({
    queryKey: ['dashboard', timeframe, 'watchlist-no-signal'],
    queryFn: () => dashboardApi.noSignal(timeframe),
    ...opts,
    enabled: false,
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

  const sectionQueries = [overviewQ] as const
  const isRefreshing = sectionQueries.some(query => query.isFetching)

  const isScanActive = isTriggeringScan || statusQ.data?.is_running

  const refreshBoards = () => {
    sectionQueries.forEach(query => query.refetch())
    statusQ.refetch()
  }

  const triggerScan = async () => {
    setIsTriggeringScan(true)
    try {
      await dashboardApi.refreshScan(timeframe)
      statusQ.refetch()
      sectionQueries.forEach(query => query.refetch())
    } finally {
      setIsTriggeringScan(false)
    }
  }

  useEffect(() => {
    const lastFinishedAt = statusQ.data?.last_finished_at
    const status = statusQ.data?.status ?? null
    const previousFinishedAt = lastFinishedAtRef.current
    const previousStatus = lastStatusRef.current

    if (status === 'ready' && lastFinishedAt && (previousFinishedAt !== lastFinishedAt || previousStatus !== 'ready')) {
      sectionQueries.forEach(query => query.refetch())
    }

    if (lastFinishedAt) {
      lastFinishedAtRef.current = lastFinishedAt
    }
    lastStatusRef.current = status
  }, [statusQ.data?.last_finished_at, statusQ.data?.status])

  useEffect(() => {
    setIntradayView('all')
    setIntradayPreset('all')
    lastFinishedAtRef.current = null
    lastStatusRef.current = null
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

  const overview = overviewQ.data
  const longData = filterDashboard(overview?.long_high_probability)
  const armedData = filterDashboard(overview?.pattern_armed)
  const liveData = filterDashboard(overview?.live_intraday_candidates)
  const formingData = filterDashboard(overview?.forming_candidates)
  const simData = filterDashboard(overview?.high_textbook_similarity)
  const shortData = filterDashboard(overview?.short_high_probability)
  const noSigData = filterDashboard(overview?.watchlist_no_signal)

  const filteredSections: Array<DashboardResponse | undefined> = [
    longData,
    armedData,
    liveData,
    formingData,
    simData,
    shortData,
    noSigData,
  ]

  const intradaySummary = intradayMode ? buildIntradaySummary(filteredSections) : null
  const intradayEmptyMessage =
    intradayMode && statusQ.data?.status === 'warming' && (statusQ.data?.cached_result_count ?? 0) === 0
      ? `${timeframeLabel(timeframe)} 후보를 백그라운드에서 예열 중입니다. 잠시 후 카드가 자동으로 채워집니다.`
      : undefined
  const intradayFallbackMessage =
    intradayMode && ['fallback_seed', 'placeholder_seed'].includes(statusQ.data?.candidate_source ?? '')
      ? statusQ.data?.candidate_source === 'placeholder_seed'
        ? `지금은 ${timeframeLabel(timeframe)} 빠른 예열 후보를 먼저 보여주고 있습니다. 백그라운드 분봉 스캔이 끝나면 실제 분석 결과로 자동 교체됩니다.`
        : `지금은 ${timeframeLabel(timeframe)} 즉시 fallback 후보를 먼저 보여주고 있습니다. 백그라운드 정리가 끝나면 카드가 더 정확한 결과로 바뀝니다.`
      : null
  const liveEmptyMessage = getLiveSectionEmptyMessage(statusQ.data, timeframe) ?? intradayEmptyMessage
  const sectionEmptyMessage = getDefaultSectionEmptyMessage(statusQ.data, timeframe) ?? intradayEmptyMessage

  return (
    <div className="space-y-8">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <h1 className="text-xl font-bold">대시보드</h1>
          <p className="mt-0.5 max-w-3xl text-xs text-muted-foreground">
            KRX 기준으로 타임프레임별 패턴, 거래 준비도, 데이터 품질을 한 번에 보고 지금 바로 볼 후보와 조금 더 지켜볼 후보를 나눠 읽는 메인 화면입니다.
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
          <div className="text-sm font-semibold">지금 볼 후보와 지켜볼 후보를 분리해서 봅니다</div>
          <p className="text-xs leading-relaxed text-muted-foreground">
            카드 정렬은 단순 상승 확률만이 아니라 거래 준비도, 상위 타임프레임 정렬, 데이터 품질까지 함께 반영합니다. 이미 끝난 패턴과 아직 베이스를 만드는 후보를
            같은 강도로 보지 않도록 설계했습니다.
          </p>
        </div>
      </Card>

      {intradayMode && (
        <Card className="flex items-start gap-3 border-yellow-500/30 bg-yellow-500/5 p-4">
          <AlertTriangle size={16} className="mt-0.5 text-yellow-400" />
          <div className="space-y-1">
            <div className="text-sm font-semibold text-yellow-300">분봉 후보 해석은 더 보수적으로 읽습니다</div>
            <p className="text-xs leading-relaxed text-muted-foreground">
              {timeframeLabel(timeframe)} 대시보드는 먼저 빠른 후보를 수집하고 그 위에 분봉 해석을 붙입니다. 분봉은 KIS, 저장 캐시, 공개 소스의 품질 차이가 있기 때문에
              데이터 상태가 약하면 자동으로 관망 또는 No Signal 쪽으로 더 보수적으로 밀립니다.
            </p>
          </div>
        </Card>
      )}

      {intradayMode && (
        <Card className="flex items-start gap-3 border-sky-500/20 bg-sky-500/5 p-4">
          <Activity size={16} className="mt-0.5 text-sky-300" />
          <div className="space-y-1">
            <div className="text-sm font-semibold text-sky-200">Live KIS 후보는 정말 급한 경우만 우선합니다</div>
            <p className="text-xs leading-relaxed text-muted-foreground">
              장 시작 직후나 마감 직전처럼 실시간성이 중요한 구간에서만 live 후보 비중을 높이고, 점심시간이나 장외 시간에는 저장 분봉과 공개 소스를 우선 씁니다. 후보 중에서도
              진입 적합성과 패턴 완성 임박, 최신성이 높은 종목만 live 분봉으로 더 깊게 확인합니다.
            </p>
          </div>
        </Card>
      )}

      {intradayMode && intradayFallbackMessage && (
        <Card className="flex items-start gap-3 border-cyan-500/20 bg-cyan-500/5 p-4">
          <Loader2 size={16} className={statusQ.data?.is_running ? 'mt-0.5 animate-spin text-cyan-300' : 'mt-0.5 text-cyan-300'} />
          <div className="space-y-1">
            <div className="text-sm font-semibold text-cyan-100">지금은 빠른 후보를 먼저 보여주는 단계입니다</div>
            <p className="text-xs leading-relaxed text-muted-foreground">{intradayFallbackMessage}</p>
          </div>
        </Card>
      )}

      {intradayMode && (
        <div className="flex flex-wrap gap-2">
          {INTRADAY_VIEW_OPTIONS.map(([value, label]) => (
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
          {INTRADAY_PRESET_OPTIONS.map(([value, label]) => (
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
              현재 필터로 좁힌 후보를 빠르게 읽을 수 있도록 핵심 숫자만 모아 둔 영역입니다.
            </p>
          </div>

          <div className="grid grid-cols-2 gap-3 xl:grid-cols-6">
            <StatusCell label="후보 수" value={`${intradaySummary.totalCount}개`} />
            <StatusCell label="실제 분석" value={`${intradaySummary.realCount}개`} />
            <StatusCell label="임시 후보" value={`${intradaySummary.placeholderCount}개`} />
            <StatusCell label="live 추적" value={`${intradaySummary.liveCount}개`} />
            <StatusCell label="confirmed" value={`${intradaySummary.confirmedCount}개`} />
            <StatusCell label="관망 / No Signal" value={`${intradaySummary.noSignalCount}개`} />
            <StatusCell label="평균 품질" value={intradaySummary.isProvisionalOnly ? '임시값' : `${Math.round(intradaySummary.avgQuality * 100)}%`} />
            <StatusCell label="평균 진입 적합도" value={intradaySummary.isProvisionalOnly ? '임시값' : `${Math.round(intradaySummary.avgEntry * 100)}%`} />
          </div>
        </Card>
      )}

      {intradayMode && intradaySummary && (
        <Card className="space-y-4">
          <div>
            <div className="text-sm font-semibold">프리셋 컨텍스트</div>
            <p className="mt-1 text-xs text-muted-foreground">
              현재 프리셋 기준으로 데이터 품질과 셋업 분포를 같이 읽을 수 있게 만든 보조 요약입니다.
            </p>
          </div>

          <div className="grid grid-cols-2 gap-3 xl:grid-cols-4">
            <StatusCell label="평균 edge" value={intradaySummary.isProvisionalOnly ? '임시값' : `${Math.round(intradaySummary.avgEdge * 100)}%`} />
            <StatusCell label="평균 손익비" value={intradaySummary.isProvisionalOnly ? '임시값' : intradaySummary.avgRewardRisk.toFixed(2)} />
            <StatusCell label="우세한 수집 모드" value={intradaySummary.dominantMode} />
            <StatusCell label="우세한 셋업 단계" value={intradaySummary.dominantStage} />
          </div>

          <div className="rounded-lg border border-cyan-500/20 bg-cyan-500/5 p-3 text-xs text-cyan-100">{intradaySummary.guidance}</div>

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
              confirmed / 즉시 확인
            </button>
            <button
              onClick={() => setIntradayPreset('watch')}
              className="rounded-md border border-violet-500/30 bg-violet-500/10 px-2.5 py-1.5 text-xs text-violet-100 transition-colors hover:bg-violet-500/15"
            >
              forming / watch
            </button>
            <button
              onClick={() => setIntradayPreset('cooling')}
              className="rounded-md border border-amber-500/30 bg-amber-500/10 px-2.5 py-1.5 text-xs text-amber-100 transition-colors hover:bg-amber-500/15"
            >
              관망 / 정리
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
              최근 스캔 결과와 후보 생성 방식을 확인하고, 필요하면 현재 타임프레임 기준으로 바로 다시 스캔할 수 있습니다.
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
          <StatusCell label="후보 생성 방식" value={candidateSourceLabel(statusQ.data?.candidate_source)} />
          <StatusCell label="후보 개수" value={statusQ.data?.candidate_count ? `${statusQ.data.candidate_count}개` : '-'} />
          <StatusCell label="실행 주체" value={sourceLabel(statusQ.data?.source)} />
          <StatusCell label="소요 시간" value={statusQ.data?.duration_ms ? `${(statusQ.data.duration_ms / 1000).toFixed(1)}초` : '-'} />
        </div>

        {intradayMode && (
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <StatusCell label="Live 단계" value={livePhaseLabel(statusQ.data?.intraday_live_phase)} />
            <StatusCell label="Live 사용 수" value={statusQ.data?.intraday_live_candidate_count != null ? `${statusQ.data.intraday_live_candidate_count}개` : '-'} />
            <StatusCell label="Live 시도 상한" value={statusQ.data?.intraday_live_candidate_limit != null ? `${statusQ.data.intraday_live_candidate_limit}개` : '-'} />
            <StatusCell label="운영 메모" value={livePhaseNote(statusQ.data?.intraday_live_phase)} />
          </div>
        )}

        {statusQ.data?.last_error && (
          <div className="rounded-lg border border-red-500/20 bg-red-500/5 p-3 text-xs text-red-200">
            최근 오류: {statusQ.data.last_error}
          </div>
        )}

        {statusQ.isError && !statusQ.isLoading && (
          <div className="rounded-lg border border-amber-500/20 bg-amber-500/5 p-3 text-xs text-amber-100">
            스캔 상태를 불러오지 못했습니다. 카드 자체는 마지막 캐시를 보여주고 있지만, 현재 예열이나 스캔이 진행 중인지 다시 확인할 필요가 있습니다.
          </div>
        )}
      </Card>

      <DashboardSection
        title="상승 확률 상위"
        subtitle="상승 확률, 거래 준비도, 상위 타임프레임 정렬까지 함께 좋은 종목입니다."
        data={longData}
        isLoading={overviewQ.isLoading}
        isError={overviewQ.isError}
        onRetry={() => overviewQ.refetch()}
        intradayPreset={intradayMode ? intradayPreset : undefined}
        emptyMessage={sectionEmptyMessage}
      />

      <DashboardSection
        title="패턴 완성 임박"
        subtitle="거의 다 만들어졌고 돌파 감시 단계에 가까운 후보입니다."
        data={armedData}
        isLoading={overviewQ.isLoading}
        isError={overviewQ.isError}
        onRetry={() => overviewQ.refetch()}
        intradayPreset={intradayMode ? intradayPreset : undefined}
        emptyMessage={sectionEmptyMessage}
      />

      {intradayMode && (
        <DashboardSection
          title="Live 분봉 후보"
          subtitle="실제 live KIS 분봉까지 연결해 확인 중인 후보입니다. 저장 분봉이나 공개 소스 기반 후보보다 우선 관찰할 묶음입니다."
          data={liveData}
          isLoading={overviewQ.isLoading}
          isError={overviewQ.isError}
          onRetry={() => overviewQ.refetch()}
          intradayPreset={intradayPreset}
          emptyMessage={liveEmptyMessage}
        />
      )}

      <DashboardSection
        title="형성 중 후보"
        subtitle="아직 forming 상태지만 구조가 살아 있어 관찰 가치가 있는 후보입니다. 완성 신호가 아니라 관찰용 후보군으로 보세요."
        data={formingData}
        isLoading={overviewQ.isLoading}
        isError={overviewQ.isError}
        onRetry={() => overviewQ.refetch()}
        intradayPreset={intradayMode ? intradayPreset : undefined}
        emptyMessage={sectionEmptyMessage}
      />

      <DashboardSection
        title="교과서 유사형"
        subtitle="교과서 구조와 유사도가 높은 후보입니다. 다만 최근성, 데이터 품질, 행동 가이드까지 같이 봐야 합니다."
        data={simData}
        isLoading={overviewQ.isLoading}
        isError={overviewQ.isError}
        onRetry={() => overviewQ.refetch()}
        intradayPreset={intradayMode ? intradayPreset : undefined}
        emptyMessage={sectionEmptyMessage}
      />

      <DashboardSection
        title="하락 확률 상위"
        subtitle="약세 패턴과 하락 방향 정렬까지 함께 들어온 종목입니다."
        data={shortData}
        isLoading={overviewQ.isLoading}
        isError={overviewQ.isError}
        onRetry={() => overviewQ.refetch()}
        intradayPreset={intradayMode ? intradayPreset : undefined}
        emptyMessage={sectionEmptyMessage}
      />

      <DashboardSection
        title="No Signal / 관망"
        subtitle="데이터 품질, 구조, 손익비, 활성 과정 중 하나 이상이 부족해 보수적으로 관망 처리한 종목입니다."
        data={noSigData}
        isLoading={overviewQ.isLoading}
        isError={overviewQ.isError}
        onRetry={() => overviewQ.refetch()}
        intradayPreset={intradayMode ? intradayPreset : undefined}
        emptyMessage={sectionEmptyMessage}
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
      realCount: 0,
      placeholderCount: 0,
      isProvisionalOnly: false,
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

  const realItems = items.filter(item => !isPlaceholderItem(item))
  const placeholderCount = items.length - realItems.length
  const metricItems = realItems.length > 0 ? realItems : items

  const totals = items.reduce(
    (acc, item) => {
      acc.liveCount += item.live_intraday_candidate ? 1 : 0
      acc.confirmedCount += item.state === 'confirmed' ? 1 : 0
      acc.noSignalCount += item.no_signal_flag ? 1 : 0
      acc.modeCounts[item.intraday_collection_mode] = (acc.modeCounts[item.intraday_collection_mode] ?? 0) + 1
      acc.stageCounts[item.setup_stage] = (acc.stageCounts[item.setup_stage] ?? 0) + 1
      return acc
    },
    {
      liveCount: 0,
      confirmedCount: 0,
      noSignalCount: 0,
      modeCounts: {} as Record<string, number>,
      stageCounts: {} as Record<string, number>,
    },
  )

  const metricTotals = metricItems.reduce(
    (acc, item) => {
      acc.qualitySum += item.data_quality
      acc.entrySum += item.entry_score
      acc.edgeSum += item.historical_edge_score
      acc.rewardRiskSum += item.reward_risk_ratio
      return acc
    },
    {
      qualitySum: 0,
      entrySum: 0,
      edgeSum: 0,
      rewardRiskSum: 0,
    },
  )

  return {
    totalCount: items.length,
    realCount: realItems.length,
    placeholderCount,
    isProvisionalOnly: realItems.length === 0 && placeholderCount > 0,
    liveCount: totals.liveCount,
    confirmedCount: totals.confirmedCount,
    noSignalCount: totals.noSignalCount,
    avgQuality: metricTotals.qualitySum / metricItems.length,
    avgEntry: metricTotals.entrySum / metricItems.length,
    avgEdge: metricTotals.edgeSum / metricItems.length,
    avgRewardRisk: metricTotals.rewardRiskSum / metricItems.length,
    dominantMode: dominantLabel(totals.modeCounts, modeLabel),
    dominantStage: dominantLabel(totals.stageCounts, setupStageLabel),
    guidance: buildSummaryGuidance(items),
  }
}

function dominantLabel(counts: Record<string, number>, formatter?: (value: string) => string): string {
  const entries = Object.entries(counts)
  if (entries.length === 0) return '-'
  const winner = entries.sort((a, b) => b[1] - a[1])[0][0]
  return formatter ? formatter(winner) : winner
}

function buildSummaryGuidance(items: DashboardItem[]): string {
  const realItems = items.filter(item => !isPlaceholderItem(item))
  if (realItems.length === 0 && items.length > 0) {
    return '지금은 빠른 예열 후보만 먼저 보여주고 있습니다. 평균 점수보다 후보 대강과 액션 분포만 가볍게 보고, 실제 분봉 스캔 완료 뒤 다시 판단하는 편이 좋습니다.'
  }

  const metricItems = realItems.length > 0 ? realItems : items
  const liveCount = items.filter(item => item.live_intraday_candidate).length
  const confirmedCount = metricItems.filter(item => item.state === 'confirmed').length
  const avgEdge = metricItems.reduce((sum, item) => sum + item.historical_edge_score, 0) / metricItems.length
  const avgRewardRisk = metricItems.reduce((sum, item) => sum + item.reward_risk_ratio, 0) / metricItems.length

  if (liveCount >= Math.max(2, Math.round(metricItems.length * 0.4)) && confirmedCount >= Math.max(1, Math.round(metricItems.length * 0.25))) {
    return 'live 추적 비중과 confirmed 비중이 모두 괜찮습니다. 무조건 많이 보기보다 상위 몇 개를 깊게 확인하는 편이 좋습니다.'
  }

  if (avgEdge >= 0.58 && avgRewardRisk >= 1.4) {
    return '평균 edge와 손익비는 무난한 편입니다. 많이 보기보다 상위 후보 몇 개에 집중하는 방식이 효율적입니다.'
  }

  return '확인 신호보다 후보가 더 많은 상태입니다. 진입보다 트리거 확인과 데이터 보강 여부를 먼저 보는 편이 좋습니다.'
}

function isPlaceholderItem(item: DashboardItem): boolean {
  return item.fetch_status === 'placeholder_pending'
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
    case 'cache':
      return '캐시 응답'
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
      return '장 시작 직후'
    case 'regular_session':
      return '정규장'
    case 'midday':
      return '점심시간 축소'
    case 'closing_drive':
      return '마감 전 집중'
    case 'off_hours':
      return '장외 절약 모드'
    default:
      return '-'
  }
}

function livePhaseNote(phase: string | null | undefined): string {
  switch (phase) {
    case 'open_drive':
      return '초기 추세 확인 구간이라 live 후보 비중을 더 높입니다.'
    case 'regular_session':
      return '강한 후보만 live로 확인하고 나머지는 절약 모드로 운용합니다.'
    case 'midday':
      return '노이즈가 많은 시간대라 live 사용 시도를 줄입니다.'
    case 'closing_drive':
      return '마감 전 돌파 확인을 위해 live 후보를 다시 늘립니다.'
    case 'off_hours':
      return '장외에는 저장 분봉과 공개 소스를 우선 씁니다.'
    default:
      return '-'
  }
}

function candidateSourceLabel(source: string | null | undefined): string {
  switch (source) {
    case 'daily_seed':
      return '일봉 상위 후보'
    case 'fallback_seed':
      return '즉시 fallback 후보'
    case 'placeholder_seed':
      return '빠른 예열 후보'
    case 'background_pending':
      return '백그라운드 예열 대기'
    case 'cache_ready':
      return '캐시 예열 결과'
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

function getDefaultSectionEmptyMessage(status: ScanStatusResponse | undefined, timeframe: Timeframe): string | undefined {
  if (!status) return undefined
  if (status.status === 'warming' && (status.cached_result_count ?? 0) === 0) {
    return `${timeframeLabel(timeframe)} 후보를 백그라운드에서 예열 중입니다. 잠시 후 카드가 자동으로 채워집니다.`
  }
  if (status.candidate_source === 'placeholder_seed') {
    return `지금은 ${timeframeLabel(timeframe)} 빠른 예열 후보를 먼저 보여주는 단계입니다. 실제 분석 카드가 곧 자동으로 교체됩니다.`
  }
  if (status.candidate_source === 'fallback_seed') {
    return `지금은 ${timeframeLabel(timeframe)} 빠른 fallback 후보를 먼저 보여주는 단계라 섹션별 후보 수가 적을 수 있습니다.`
  }
  return undefined
}

function getLiveSectionEmptyMessage(status: ScanStatusResponse | undefined, timeframe: Timeframe): string | undefined {
  if (!status) return undefined
  if (status.status === 'warming' && (status.cached_result_count ?? 0) === 0) {
    return `${timeframeLabel(timeframe)} live 후보를 수집 중입니다. 잠시 후 자동으로 다시 채워집니다.`
  }
  if (status.candidate_source === 'placeholder_seed') {
    return `지금은 ${timeframeLabel(timeframe)} 빠른 예열 후보만 먼저 보여주고 있어 live 분봉 후보가 잠시 비어 있을 수 있습니다.`
  }
  if (status.intraday_live_phase === 'off_hours') {
    return '지금은 장외 절약 모드라 live 분봉 후보를 비워 두고 있습니다. forming / watch 후보를 먼저 확인해 보세요.'
  }
  if ((status.intraday_live_candidate_limit ?? 0) === 0) {
    return '현재 시간대에서는 중요도 기준을 통과하는 live 분봉 후보가 아직 없습니다.'
  }
  if (status.candidate_source === 'fallback_seed') {
    return `지금은 ${timeframeLabel(timeframe)} 빠른 fallback 후보를 먼저 보여주고 있어 live 후보가 잠시 비어 있을 수 있습니다.`
  }
  return '현재 조건에서 바로 live 분봉까지 볼 만한 후보가 없습니다.'
}

function modeLabel(mode: string): string {
  switch (mode) {
    case 'live':
      return 'live'
    case 'stored':
      return '저장 캐시'
    case 'public':
      return '공개 소스'
    case 'mixed':
      return '혼합'
    case 'cooldown':
      return '쿨다운'
    case 'budget':
      return '절약 모드'
    default:
      return mode || '-'
  }
}

function setupStageLabel(stage: string): string {
  switch (stage) {
    case 'confirmed':
      return '확인 완료'
    case 'trigger_ready':
      return '트리거 대기'
    case 'breakout_watch':
      return '돌파 감시'
    case 'late_base':
      return '후반 베이스'
    case 'early_trigger_watch':
      return '초기 트리거 감시'
    case 'base_building':
      return '베이스 형성'
    case 'no_signal':
      return '관망'
    default:
      return stage || '-'
  }
}
