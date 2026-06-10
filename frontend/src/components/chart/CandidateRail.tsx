import { useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { Loader2, Star } from 'lucide-react'

import { Card } from '@/components/ui/Card'
import { dashboardApi } from '@/lib/api'
import { dedupeDashboardItems } from '@/lib/dashboardDecks'
import { dashboardPriorityScore } from '@/lib/dashboardSnapshot'
import { timeframeLabel } from '@/lib/timeframes'
import { cn, PATTERN_NAMES } from '@/lib/utils'
import { useAppStore } from '@/store/app'
import type { DashboardItem, Timeframe } from '@/types/api'

/**
 * AlphaSquare-style left rail for the chart page: today's scan candidates,
 * one click to switch symbols without going back to the dashboard.
 * Shares the dashboard overview query cache (same queryKey).
 */

interface CandidateRailProps {
  activeSymbol: string
  timeframe: Timeframe
}

export function CandidateRail({ activeSymbol, timeframe }: CandidateRailProps) {
  const nav = useNavigate()
  const { isWatched } = useAppStore()

  const overviewQ = useQuery({
    queryKey: ['dashboard', timeframe, 'overview'],
    queryFn: () => dashboardApi.overview(timeframe),
    staleTime: 60_000,
  })

  const items = useMemo(() => {
    const overview = overviewQ.data
    if (!overview) return []
    // 관망(no signal) 섹션은 제외 — 레일은 "지금 볼 후보 빠르게 넘기기" 용도
    const deduped = dedupeDashboardItems([
      overview.long_high_probability,
      overview.pattern_armed,
      overview.live_intraday_candidates,
      overview.forming_candidates,
      overview.high_textbook_similarity,
      overview.short_high_probability,
    ])
    return deduped
      .map(item => ({ item, score: dashboardPriorityScore(item, 'steady', isWatched(item.symbol.code)) }))
      .sort((left, right) => right.score - left.score)
      .slice(0, 30)
      .map(entry => entry.item)
  }, [overviewQ.data, isWatched])

  return (
    <Card className="flex h-full flex-col overflow-hidden">
      <div className="border-b border-border/70 px-3 py-3">
        <div className="text-sm font-semibold">오늘의 후보</div>
        <p className="mt-0.5 text-xs text-muted-foreground">
          {timeframeLabel(timeframe)} 스캔 {items.length > 0 ? `${items.length}개` : ''} · 클릭해서 차트 전환
        </p>
      </div>
      <div className="min-h-0 flex-1 space-y-0.5 overflow-y-auto p-2">
        {overviewQ.isLoading ? (
          <div className="flex h-32 flex-col items-center justify-center gap-2 text-xs text-muted-foreground">
            <Loader2 size={15} className="animate-spin" />
            후보를 불러오는 중
          </div>
        ) : items.length === 0 ? (
          <p className="px-2 py-4 text-xs leading-relaxed text-muted-foreground">
            지금은 표시할 후보가 없습니다. 스캔이 끝나면 자동으로 채워집니다.
          </p>
        ) : (
          items.map(item => (
            <CandidateRow
              key={`${item.timeframe}-${item.symbol.code}`}
              item={item}
              active={item.symbol.code === activeSymbol}
              watched={isWatched(item.symbol.code)}
              onOpen={() => nav(`/chart/${item.symbol.code}`)}
            />
          ))
        )}
      </div>
    </Card>
  )
}

function CandidateRow({
  item,
  active,
  watched,
  onOpen,
}: {
  item: DashboardItem
  active: boolean
  watched: boolean
  onOpen: () => void
}) {
  const pUpPct = Math.round(item.p_up * 100)
  return (
    <button
      onClick={onOpen}
      className={cn(
        'w-full rounded-lg border px-2.5 py-2 text-left transition-colors',
        active
          ? 'border-primary/40 bg-primary/10'
          : 'border-transparent hover:border-border hover:bg-muted/40',
      )}
    >
      <div className="flex items-center justify-between gap-2">
        <span className="flex min-w-0 items-center gap-1 text-sm font-medium">
          {watched && <Star size={11} className="shrink-0 fill-amber-300 text-amber-300" />}
          <span className="truncate">{item.symbol.name}</span>
        </span>
        <span
          className={cn(
            'shrink-0 font-mono text-xs font-semibold',
            pUpPct >= 55 ? 'text-emerald-300' : pUpPct <= 45 ? 'text-red-300' : 'text-muted-foreground',
          )}
        >
          {pUpPct}%
        </span>
      </div>
      <div className="mt-0.5 flex items-center justify-between gap-2 text-[11px] text-muted-foreground">
        <span className="truncate">
          {item.pattern_type ? PATTERN_NAMES[item.pattern_type] ?? item.pattern_type : '패턴 없음'}
        </span>
        <span className={cn('shrink-0', actionPlanTone(item.action_plan))}>{item.action_plan_label}</span>
      </div>
    </button>
  )
}

function actionPlanTone(actionPlan: string): string {
  switch (actionPlan) {
    case 'ready_now':
      return 'text-emerald-300'
    case 'watch':
      return 'text-sky-300'
    case 'recheck':
      return 'text-amber-300'
    default:
      return ''
  }
}
