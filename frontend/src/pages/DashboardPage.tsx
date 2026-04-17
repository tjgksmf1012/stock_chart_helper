import { useEffect, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Activity, Loader2, RefreshCw } from 'lucide-react'

import { DashboardSection } from '@/components/dashboard/DashboardSection'
import { Card } from '@/components/ui/Card'
import { dashboardApi } from '@/lib/api'
import { DEFAULT_TIMEFRAME, TIMEFRAME_OPTIONS } from '@/lib/timeframes'
import { fmtDateTime } from '@/lib/utils'
import type { Timeframe } from '@/types/api'

export default function DashboardPage() {
  const [selectedTimeframe, setSelectedTimeframe] = useState<Timeframe>(DEFAULT_TIMEFRAME)
  const [isTriggeringScan, setIsTriggeringScan] = useState(false)
  const lastFinishedAtRef = useRef<string | null>(null)

  const opts = { staleTime: 30_000, refetchInterval: 60_000 }
  const longQ = useQuery({
    queryKey: ['dashboard', 'long', selectedTimeframe],
    queryFn: () => dashboardApi.longHigh(selectedTimeframe),
    ...opts,
  })
  const shortQ = useQuery({
    queryKey: ['dashboard', 'short', selectedTimeframe],
    queryFn: () => dashboardApi.shortHigh(selectedTimeframe),
    ...opts,
  })
  const simQ = useQuery({
    queryKey: ['dashboard', 'sim', selectedTimeframe],
    queryFn: () => dashboardApi.highSimilarity(selectedTimeframe),
    ...opts,
  })
  const armedQ = useQuery({
    queryKey: ['dashboard', 'armed', selectedTimeframe],
    queryFn: () => dashboardApi.armed(selectedTimeframe),
    ...opts,
  })
  const noSigQ = useQuery({
    queryKey: ['dashboard', 'nosig', selectedTimeframe],
    queryFn: () => dashboardApi.noSignal(selectedTimeframe),
    ...opts,
  })
  const statusQ = useQuery({
    queryKey: ['dashboard', 'scan-status', selectedTimeframe],
    queryFn: () => dashboardApi.scanStatus(selectedTimeframe),
    staleTime: 5_000,
    refetchInterval: 15_000,
  })

  const isRefreshing = longQ.isFetching || shortQ.isFetching || simQ.isFetching || armedQ.isFetching || noSigQ.isFetching
  const isScanActive = isTriggeringScan || statusQ.data?.is_running

  const refreshBoards = () => {
    longQ.refetch()
    shortQ.refetch()
    simQ.refetch()
    armedQ.refetch()
    noSigQ.refetch()
    statusQ.refetch()
  }

  const triggerScan = async () => {
    setIsTriggeringScan(true)
    try {
      await dashboardApi.refreshScan(selectedTimeframe)
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

  return (
    <div className="space-y-8">
      <div className="flex flex-col gap-4 xl:flex-row xl:items-end xl:justify-between">
        <div className="space-y-2">
          <div>
            <h1 className="text-xl font-bold">대시보드</h1>
            <p className="mt-0.5 text-sm text-muted-foreground">
              KRX 종목을 기준으로 선택한 타임프레임의 상승 확률, 패턴 완성 임박도, 신호 신선도를 빠르게 확인합니다.
            </p>
          </div>

          <div className="flex flex-wrap gap-2">
            {TIMEFRAME_OPTIONS.map(option => (
              <button
                key={option.value}
                onClick={() => setSelectedTimeframe(option.value)}
                className={`rounded-lg border px-3 py-1.5 text-sm transition-colors ${
                  selectedTimeframe === option.value
                    ? 'border-primary bg-primary text-primary-foreground'
                    : 'border-border bg-card text-muted-foreground hover:text-foreground'
                }`}
              >
                {option.label}
              </button>
            ))}
          </div>

          {selectedTimeframe !== '1d' && selectedTimeframe !== '1wk' && selectedTimeframe !== '1mo' && (
            <p className="text-xs text-amber-300/90">
              분봉 기준은 현재 KIS 없이 fallback 데이터로 계산됩니다. 그래서 일봉·주봉보다 보수적으로 점수를 낮춰서 반영합니다.
            </p>
          )}
        </div>

        <button
          onClick={refreshBoards}
          className="flex items-center gap-1.5 text-xs text-muted-foreground transition-colors hover:text-foreground"
        >
          <RefreshCw size={13} className={isRefreshing ? 'animate-spin' : ''} />
          새로고침
        </button>
      </div>

      <Card className="space-y-4">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
          <div className="space-y-1">
            <div className="flex items-center gap-2 text-sm font-semibold">
              <Activity size={15} className={statusQ.data?.is_running ? 'text-primary' : 'text-muted-foreground'} />
              스캔 상태
            </div>
            <p className="text-xs text-muted-foreground">
              현재 선택한 타임프레임 기준으로 전체 시장 스캔 캐시와 최근 실행 상태를 확인합니다.
            </p>
          </div>
          <button
            onClick={triggerScan}
            disabled={Boolean(isScanActive)}
            className="inline-flex items-center justify-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {isScanActive ? <Loader2 size={14} className="animate-spin" /> : <RefreshCw size={14} />}
            {isScanActive ? '스캔 진행 중' : '선택 타임프레임 스캔'}
          </button>
        </div>

        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-5">
          <StatusCell label="기준" value={labelFor(selectedTimeframe)} />
          <StatusCell label="상태" value={statusLabel(statusQ.data?.status)} />
          <StatusCell label="마지막 완료" value={fmtDateTime(statusQ.data?.last_finished_at)} />
          <StatusCell label="캐시 결과 수" value={`${statusQ.data?.cached_result_count ?? 0}개`} />
          <StatusCell label="스캔 대상 수" value={statusQ.data?.universe_size ? `${statusQ.data.universe_size}개` : '-'} />
        </div>

        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
          <StatusCell label="최근 실행 주체" value={sourceLabel(statusQ.data?.source)} />
          <StatusCell
            label="최근 소요 시간"
            value={statusQ.data?.duration_ms ? `${(statusQ.data.duration_ms / 1000).toFixed(1)}초` : '-'}
          />
          <StatusCell label="마지막 오류" value={statusQ.data?.last_error || '-'} />
        </div>
      </Card>

      <DashboardSection
        title="상승 확률 상위"
        subtitle={`${labelFor(selectedTimeframe)} 기준에서 진입 적합도와 상승 확률이 함께 높은 종목`}
        data={longQ.data}
        isLoading={longQ.isLoading}
      />

      <DashboardSection
        title="패턴 완성 임박"
        subtitle={`${labelFor(selectedTimeframe)} 기준에서 돌파·이탈 직전이거나 방금 확인된 패턴`}
        data={armedQ.data}
        isLoading={armedQ.isLoading}
      />

      <DashboardSection
        title="교과서 유사도 상위"
        subtitle={`${labelFor(selectedTimeframe)} 차트가 교과서형 구조와 가장 비슷한 종목`}
        data={simQ.data}
        isLoading={simQ.isLoading}
      />

      <DashboardSection
        title="하락 확률 상위"
        subtitle={`${labelFor(selectedTimeframe)} 기준에서 하락 쪽 우위가 강한 종목`}
        data={shortQ.data}
        isLoading={shortQ.isLoading}
      />

      <DashboardSection
        title="No Signal / 관망"
        subtitle={`${labelFor(selectedTimeframe)} 기준에서 아직 패턴이 부족하거나 신호가 낡은 종목`}
        data={noSigQ.data}
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

function labelFor(timeframe: Timeframe): string {
  return TIMEFRAME_OPTIONS.find(option => option.value === timeframe)?.label ?? timeframe
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
