import { useEffect, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Activity, AlertTriangle, Layers3, Loader2, RefreshCw } from 'lucide-react'

import { DashboardSection } from '@/components/dashboard/DashboardSection'
import { Card } from '@/components/ui/Card'
import { dashboardApi } from '@/lib/api'
import { DEFAULT_TIMEFRAME, TIMEFRAME_OPTIONS, timeframeLabel } from '@/lib/timeframes'
import { fmtDateTime } from '@/lib/utils'
import { useAppStore } from '@/store/app'
import type { DashboardResponse } from '@/types/api'

type IntradayView = 'all' | 'live' | 'stored' | 'public' | 'mixed' | 'cooldown'

export default function DashboardPage() {
  const { selectedTimeframe, setTimeframe } = useAppStore()
  const timeframe = selectedTimeframe ?? DEFAULT_TIMEFRAME
  const intradayMode = ['60m', '30m', '15m', '1m'].includes(timeframe)
  const opts = { staleTime: 30_000, refetchInterval: 60_000 }
  const [isTriggeringScan, setIsTriggeringScan] = useState(false)
  const [intradayView, setIntradayView] = useState<IntradayView>('all')
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
  }, [timeframe])

  const filterDashboard = (data: DashboardResponse | undefined): DashboardResponse | undefined => {
    if (!intradayMode || intradayView === 'all' || !data) return data
    return {
      ...data,
      items: data.items.filter(item => {
        if (intradayView === 'live') return item.live_intraday_candidate
        return !item.live_intraday_candidate && item.intraday_collection_mode === intradayView
      }),
    }
  }

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
      />

      <DashboardSection
        title="패턴 완성 임박"
        subtitle="거의 다 만들어졌고 돌파 감시 단계에 가까운 후보입니다."
        data={filterDashboard(armedQ.data)}
        isLoading={armedQ.isLoading}
      />

      {intradayMode && (
        <DashboardSection
          title="Live 분봉 후보"
          subtitle="지금 실제 live KIS 분봉까지 열어 확인 중인 후보입니다. 저장 분봉이나 공개 소스 기반 후보보다 우선 관찰할 묶음입니다."
          data={filterDashboard(liveQ.data)}
          isLoading={liveQ.isLoading}
        />
      )}

      <DashboardSection
        title="형성 중 후보"
        subtitle="아직 forming 상태지만 상위 추세와 구조가 받쳐주는 베이스 후보입니다. 완성 신호가 아니라 관찰용 후보군으로 보세요."
        data={filterDashboard(formingQ.data)}
        isLoading={formingQ.isLoading}
      />

      <DashboardSection
        title="교과서 유사형 패턴"
        subtitle="교과서와의 유사도가 높은 구조입니다. 이제는 형성 품질과 최신성도 함께 보정합니다."
        data={filterDashboard(simQ.data)}
        isLoading={simQ.isLoading}
      />

      <DashboardSection
        title="하락 확률 상위"
        subtitle="약세 패턴과 하락 방향 정렬이 함께 들어온 종목입니다."
        data={filterDashboard(shortQ.data)}
        isLoading={shortQ.isLoading}
      />

      <DashboardSection
        title="No Signal / 관망"
        subtitle="데이터 품질, 표본 신뢰도, 손익비, 형성 과정 점수 중 하나 이상이 부족해 보수적으로 관망 처리한 종목입니다."
        data={filterDashboard(noSigQ.data)}
        isLoading={noSigQ.isLoading}
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
