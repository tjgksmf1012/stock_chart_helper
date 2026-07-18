import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Bell, CheckCircle2, Clock, ShieldAlert } from 'lucide-react'

import { MarketRegimeBar, getRegimeWarning } from '@/components/dashboard/MarketRegimeBar'
import { LiveSignals } from '@/components/lab/LiveSignals'
import { ObservationSection } from '@/components/today/ObservationSection'
import { Card } from '@/components/ui/Card'
import { dashboardApi, labApi, outcomesApi } from '@/lib/api'
import { buildWatchlistDeck, dedupeDashboardItems } from '@/lib/dashboardDecks'
import { buildObservationDeck } from '@/lib/observationDeck'
import { normalizeDisplayTimeframe, timeframeLabel } from '@/lib/timeframes'
import { attachJosa, cn, fmtDateTime } from '@/lib/utils'
import { useAppStore } from '@/store/app'
import type { DashboardItem, OutcomeRecord, ScanStatusResponse, Timeframe } from '@/types/api'

/**
 * 오늘 탭 — "오늘 무엇을 할까"에 답하는 홈.
 * 증거 순서와 화면 순서를 일치시킨다:
 * ① 시장 체제 → ② 검증된 신호(측정된 엣지) → ③ 오늘 확인할 것 → ④ 관찰 후보(참고) → ⑤ 스캔 상태.
 */
export default function TodayPage() {
  const nav = useNavigate()
  const { selectedTimeframe, setTimeframe, isWatched } = useAppStore()
  const timeframe = normalizeDisplayTimeframe(selectedTimeframe)
  const [isTriggeringScan, setIsTriggeringScan] = useState(false)
  const [isCancellingScan, setIsCancellingScan] = useState(false)
  const lastFinishedAtRef = useRef<string | null>(null)
  const lastStatusRef = useRef<string | null>(null)

  const regimeQ = useQuery({
    queryKey: ['dashboard', 'market-regime'],
    queryFn: () => dashboardApi.marketRegime(),
    staleTime: 1_800_000,
    // 백그라운드 빌드 중엔 unknown 반환 → 30초마다 재시도
    refetchInterval: query => {
      const data = query.state.data
      if (!data || data.overall_regime === 'unknown') return 30_000
      return 1_800_000
    },
  })

  const signalsQ = useQuery({
    queryKey: ['lab-signals'],
    queryFn: labApi.signals,
    staleTime: 300_000,
    // 백엔드가 백그라운드로 계산 중(status=computing)이면 5초마다 폴링해 ready를 기다린다
    refetchInterval: q => (q.state.data?.status === 'computing' ? 5_000 : false),
  })
  const signalsComputing = signalsQ.data?.status === 'computing'

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
    queryKey: ['outcomes', 'today'],
    queryFn: outcomesApi.list,
    staleTime: 60_000,
  })

  const sectorQ = useQuery({
    queryKey: ['dashboard', timeframe, 'sector-heatmap'],
    queryFn: () => dashboardApi.sectorHeatmap(timeframe),
    staleTime: 1_800_000,
    // 섹터 맵이 백그라운드 빌드 중이면 빈 결과를 받으므로 30초마다 재시도
    refetchInterval: query => {
      const data = query.state.data
      if (!data || data.sectors.length === 0) return 30_000
      return false
    },
  })

  // 스캔이 막 끝났으면 결과를 새로 가져온다
  useEffect(() => {
    const lastFinishedAt = statusQ.data?.last_finished_at
    const status = statusQ.data?.status ?? null
    if (status === 'ready' && lastFinishedAt && (lastFinishedAtRef.current !== lastFinishedAt || lastStatusRef.current !== 'ready')) {
      overviewQ.refetch()
    }
    if (lastFinishedAt) lastFinishedAtRef.current = lastFinishedAt
    lastStatusRef.current = status
  }, [overviewQ, statusQ.data?.last_finished_at, statusQ.data?.status])

  const triggerScan = async () => {
    setIsTriggeringScan(true)
    try {
      await dashboardApi.refreshScan(timeframe)
      await Promise.all([statusQ.refetch(), overviewQ.refetch()])
    } finally {
      setIsTriggeringScan(false)
    }
  }

  const cancelScan = async () => {
    setIsCancellingScan(true)
    try {
      await dashboardApi.cancelScan(timeframe)
      await statusQ.refetch()
    } finally {
      setIsCancellingScan(false)
    }
  }

  // 스캔 결과가 오래됐으면(90분) 방문 시 자동 갱신 — 하루 1회(타임프레임별) 제한
  const autoScanTriggeredRef = useRef<Set<string>>(new Set())
  useEffect(() => {
    const status = statusQ.data
    if (!status || status.is_running || isTriggeringScan) return
    if (!status.last_finished_at) return

    const lastFinishedMs = new Date(status.last_finished_at).getTime()
    if (Number.isNaN(lastFinishedMs)) return
    const AUTO_SCAN_STALE_MS = 90 * 60 * 1000
    if (Date.now() - lastFinishedMs < AUTO_SCAN_STALE_MS) return

    const guardKey = `autoScan:${timeframe}:${new Date().toISOString().slice(0, 10)}`
    if (autoScanTriggeredRef.current.has(guardKey) || sessionStorage.getItem(guardKey)) return

    autoScanTriggeredRef.current.add(guardKey)
    sessionStorage.setItem(guardKey, '1')
    triggerScan()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [statusQ.data, timeframe, isTriggeringScan])

  const overview = overviewQ.data
  const allDashboardItems = useMemo(
    () =>
      dedupeDashboardItems([
        overview?.long_high_probability,
        overview?.pattern_armed,
        overview?.live_intraday_candidates,
        overview?.forming_candidates,
        overview?.high_textbook_similarity,
        overview?.short_high_probability,
        overview?.watchlist_no_signal,
      ]),
    [overview],
  )
  const watchlistDeck = useMemo(() => buildWatchlistDeck(allDashboardItems, isWatched), [allDashboardItems, isWatched])
  const observationDeck = useMemo(
    () =>
      buildObservationDeck({
        armed: overview?.pattern_armed,
        long: overview?.long_high_probability,
        live: overview?.live_intraday_candidates,
        forming: overview?.forming_candidates,
        sim: overview?.high_textbook_similarity,
        short: overview?.short_high_probability,
        nosig: overview?.watchlist_no_signal,
      }),
    [overview],
  )
  const pendingRecords = useMemo(
    () => (outcomesQ.data ?? []).filter(record => record.outcome === 'pending').slice(0, 5),
    [outcomesQ.data],
  )

  const status = statusQ.data
  const regimeWarning = regimeQ.data ? getRegimeWarning(regimeQ.data.overall_regime) : null

  const openCandidate = (item: DashboardItem) => nav(`/chart/${item.symbol.code}`)

  return (
    <div className="space-y-5">
      {regimeQ.data && <MarketRegimeBar data={regimeQ.data} />}
      {regimeWarning && (
        <div className="rounded-lg border border-amber-400/25 bg-amber-400/8 px-3 py-2 text-xs font-medium text-amber-400">
          {regimeWarning}
        </div>
      )}
      {status?.data_source_note && (
        <div
          className={cn(
            'rounded-lg border px-3 py-2 text-xs font-medium',
            status.data_source_degraded
              ? 'border-red-400/25 bg-red-400/8 text-red-300'
              : 'border-amber-400/25 bg-amber-400/8 text-amber-300',
          )}
        >
          ⚠️ {status.data_source_note}
        </div>
      )}

      <LiveSignals
        loading={signalsQ.isLoading || signalsComputing}
        error={signalsQ.isError}
        onRetry={() => signalsQ.refetch()}
        signals={signalsQ.data?.signals ?? []}
        note={signalsComputing ? null : signalsQ.data?.note ?? null}
        generatedAt={signalsQ.data?.generated_at ?? undefined}
        demotions={signalsQ.data?.demotions}
        eligible={signalsQ.data?.eligible_strategies}
        regimeGate={signalsQ.data?.regime_gate}
      />

      <TodayChecklist
        pending={pendingRecords}
        watchTrigger={watchlistDeck.triggerClose.slice(0, 3)}
        watchRisk={watchlistDeck.riskClose.slice(0, 3)}
        onOpenChart={openCandidate}
        onOpenJournal={() => nav('/journal')}
      />

      <ObservationSection
        deck={observationDeck}
        isLoading={overviewQ.isLoading}
        isError={overviewQ.isError}
        onRetry={() => overviewQ.refetch()}
        timeframe={timeframe}
        onTimeframeChange={setTimeframe}
        sectors={sectorQ.data}
        onOpen={openCandidate}
      />

      <ScanStrip
        status={status}
        timeframe={timeframe}
        isTriggering={isTriggeringScan}
        isCancelling={isCancellingScan}
        onTrigger={triggerScan}
        onCancel={cancelScan}
      />
    </div>
  )
}

function TodayChecklist({
  pending,
  watchTrigger,
  watchRisk,
  onOpenChart,
  onOpenJournal,
}: {
  pending: OutcomeRecord[]
  watchTrigger: DashboardItem[]
  watchRisk: DashboardItem[]
  onOpenChart: (item: DashboardItem) => void
  onOpenJournal: () => void
}) {
  const isEmpty = pending.length === 0 && watchTrigger.length === 0 && watchRisk.length === 0

  return (
    <Card className="space-y-3">
      <div className="text-sm font-semibold">오늘 확인할 것</div>

      {isEmpty ? (
        <div className="flex items-center gap-2 rounded-lg border border-border bg-background/50 p-3 text-xs text-muted-foreground">
          <CheckCircle2 size={14} className="text-emerald-300" />
          지금 처리할 항목이 없습니다. 검증된 신호와 관찰 후보만 보면 됩니다.
        </div>
      ) : (
        <div className="space-y-1.5">
          {watchTrigger.map(item => (
            <ChecklistRow
              key={`trigger-${item.symbol.code}`}
              icon={<Bell size={13} className="text-amber-300" />}
              text={`관심종목 ${attachJosa(item.symbol.name, '이/가')} 트리거 가격에 근접했습니다`}
              action="차트 보기"
              onClick={() => onOpenChart(item)}
            />
          ))}
          {watchRisk.map(item => (
            <ChecklistRow
              key={`risk-${item.symbol.code}`}
              icon={<ShieldAlert size={13} className="text-red-300" />}
              text={`관심종목 ${attachJosa(item.symbol.name, '은/는')} 손절 기준가 확인이 필요합니다`}
              action="차트 보기"
              onClick={() => onOpenChart(item)}
            />
          ))}
          {pending.map(record => (
            <ChecklistRow
              key={`pending-${record.id ?? record.symbol_code}`}
              icon={<Clock size={13} className="text-muted-foreground" />}
              text={`${record.symbol_name} 판단 기록이 미정리 상태입니다 (${record.signal_date} 신호)`}
              action="기록에서 닫기"
              onClick={onOpenJournal}
            />
          ))}
        </div>
      )}
    </Card>
  )
}

function ChecklistRow({
  icon,
  text,
  action,
  onClick,
}: {
  icon: React.ReactNode
  text: string
  action: string
  onClick: () => void
}) {
  return (
    <button
      onClick={onClick}
      className="flex w-full items-center gap-2.5 rounded-lg border border-border bg-background/50 px-3 py-2 text-left text-xs transition-colors hover:border-primary/30 hover:bg-muted/30"
    >
      {icon}
      <span className="min-w-0 flex-1 truncate text-foreground">{text}</span>
      <span className="shrink-0 text-[11px] text-muted-foreground">{action} →</span>
    </button>
  )
}

function ScanStrip({
  status,
  timeframe,
  isTriggering,
  isCancelling,
  onTrigger,
  onCancel,
}: {
  status: ScanStatusResponse | undefined
  timeframe: Timeframe
  isTriggering: boolean
  isCancelling: boolean
  onTrigger: () => void
  onCancel: () => void
}) {
  const isActive = isTriggering || status?.is_running

  if (isActive) {
    const scanned = Math.min(status?.scanned_count ?? 0, status?.universe_size ?? 0)
    const total = Math.max(status?.universe_size ?? 1, 1)
    return (
      <Card className="space-y-1.5 py-3">
        <div className="flex items-center justify-between text-[11px] text-muted-foreground">
          <span>{timeframeLabel(timeframe)} 스캔 진행 중 — 기존 결과는 그대로 유지됩니다</span>
          <div className="flex items-center gap-2">
            <span className="font-mono">
              {scanned} / {status?.universe_size ?? '-'}종목
            </span>
            {!status?.cancel_requested ? (
              <button
                onClick={onCancel}
                disabled={isCancelling}
                className="text-muted-foreground underline decoration-dotted transition-colors hover:text-foreground disabled:opacity-50"
              >
                {isCancelling ? '취소 중...' : '취소'}
              </button>
            ) : (
              <span>취소 반영 중</span>
            )}
          </div>
        </div>
        <div className="h-1.5 overflow-hidden rounded-full bg-muted/40">
          <div
            className="h-full rounded-full bg-primary transition-all duration-700"
            style={{ width: `${Math.min(100, Math.round((scanned / total) * 100))}%` }}
          />
        </div>
      </Card>
    )
  }

  return (
    <Card className="flex flex-wrap items-center justify-between gap-2 py-3 text-[11px] text-muted-foreground">
      <span>
        마지막 스캔 {status?.last_finished_at ? fmtDateTime(status.last_finished_at) : '-'} · 캐시 결과{' '}
        {status?.cached_result_count ?? 0}개
      </span>
      <button onClick={onTrigger} className="underline decoration-dotted transition-colors hover:text-foreground">
        {timeframeLabel(timeframe)} 빠른 갱신
      </button>
    </Card>
  )
}
