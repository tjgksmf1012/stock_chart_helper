import type { MouseEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { Star } from 'lucide-react'

import type { DashboardItem } from '@/types/api'
import { Badge } from '@/components/ui/Badge'
import { Card } from '@/components/ui/Card'
import { ProbBar } from '@/components/ui/ProbBar'
import { cn, fmtPct, fmtTurnoverBillion, PATTERN_NAMES, STATE_COLORS, STATE_LABELS } from '@/lib/utils'
import { useAppStore } from '@/store/app'

interface DashboardCardProps {
  item: DashboardItem
}

export function DashboardCard({ item }: DashboardCardProps) {
  const nav = useNavigate()
  const { addToWatchlist, removeFromWatchlist, isWatched, setTimeframe } = useAppStore()
  const watched = isWatched(item.symbol.code)

  const toggleWatch = (e: MouseEvent) => {
    e.stopPropagation()
    if (watched) {
      removeFromWatchlist(item.symbol.code)
    } else {
      addToWatchlist({ code: item.symbol.code, name: item.symbol.name, market: item.symbol.market })
    }
  }

  return (
    <Card
      className="cursor-pointer space-y-3"
      onClick={() => {
        setTimeframe(item.timeframe)
        nav(`/chart/${item.symbol.code}`)
      }}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-1.5">
            <span className="font-mono text-xs text-muted-foreground">#{item.rank}</span>
            <span className="truncate text-sm font-semibold">{item.symbol.name}</span>
            <span className="font-mono text-xs text-muted-foreground">{item.symbol.code}</span>
          </div>
          <div className="mt-1 flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
            <span>{item.symbol.market}</span>
            <span>•</span>
            <span>{item.timeframe_label}</span>
            <Badge variant={item.data_quality >= 0.8 ? 'bullish' : item.data_quality >= 0.6 ? 'muted' : 'warning'}>
              품질 {fmtPct(item.data_quality, 0)}
            </Badge>
          </div>
          {item.pattern_type ? (
            <div className="mt-2 flex flex-wrap items-center gap-1.5">
              <span className="text-xs text-muted-foreground">
                {PATTERN_NAMES[item.pattern_type] ?? item.pattern_type}
              </span>
              {item.state && (
                <span className={cn('rounded px-1 py-0.5 text-xs', STATE_COLORS[item.state])}>
                  {STATE_LABELS[item.state]}
                </span>
              )}
            </div>
          ) : (
            <div className="mt-2 text-xs text-muted-foreground">뚜렷한 패턴 없음</div>
          )}
        </div>

        <div className="flex items-center gap-2">
          <div className="text-right">
            <div className="text-xs text-muted-foreground">임박도</div>
            <div className="font-mono text-sm font-semibold text-primary">{fmtPct(item.completion_proximity, 0)}</div>
          </div>
          <button
            onClick={toggleWatch}
            className={cn(
              'rounded p-1.5 transition-colors',
              watched ? 'text-yellow-400 hover:text-yellow-300' : 'text-muted-foreground hover:text-yellow-400',
            )}
            title={watched ? '관심 종목 제거' : '관심 종목 추가'}
          >
            <Star size={14} className={watched ? 'fill-yellow-400' : ''} />
          </button>
        </div>
      </div>

      <ProbBar p_up={item.p_up} p_down={item.p_down} />

      <div className="grid grid-cols-2 gap-2 text-xs text-muted-foreground">
        <span>신뢰도 {fmtPct(item.confidence)}</span>
        <span className="text-right">신선도 {fmtPct(item.recency_score)}</span>
        <span>거래대금 {fmtTurnoverBillion(item.avg_turnover_billion)}</span>
        <span className="text-right">표본 {item.sample_size}건</span>
      </div>

      <p className="line-clamp-2 text-xs leading-relaxed text-muted-foreground">{item.reason_summary}</p>

      {item.no_signal_flag && <Badge variant="warning">No Signal</Badge>}
    </Card>
  )
}
