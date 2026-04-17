import { useNavigate } from 'react-router-dom'

import type { DashboardItem } from '@/types/api'
import { Card } from '@/components/ui/Card'
import { Badge } from '@/components/ui/Badge'
import { ProbBar } from '@/components/ui/ProbBar'
import { cn, fmtPct, PATTERN_NAMES, STATE_COLORS, STATE_LABELS } from '@/lib/utils'

interface DashboardCardProps {
  item: DashboardItem
}

export function DashboardCard({ item }: DashboardCardProps) {
  const nav = useNavigate()

  return (
    <Card className="space-y-2.5" onClick={() => nav(`/chart/${item.symbol.code}`)}>
      <div className="flex items-start justify-between">
        <div>
          <div className="flex items-center gap-1.5">
            <span className="font-mono text-xs text-muted-foreground">#{item.rank}</span>
            <span className="text-sm font-semibold">{item.symbol.name}</span>
            <span className="font-mono text-xs text-muted-foreground">{item.symbol.code}</span>
          </div>
          {item.pattern_type ? (
            <div className="mt-1 flex items-center gap-1.5">
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
            <div className="mt-1 text-xs text-muted-foreground">패턴 미감지</div>
          )}
        </div>
        <div className="text-right">
          <div className="text-xs text-muted-foreground">유사도</div>
          <div className="font-mono text-sm font-semibold text-primary">{fmtPct(item.textbook_similarity)}</div>
        </div>
      </div>

      <ProbBar p_up={item.p_up} p_down={item.p_down} />

      <div className="flex items-center justify-between text-xs text-muted-foreground">
        <span>신뢰도 {fmtPct(item.confidence)}</span>
        <span>진입 적합도 {fmtPct(item.entry_score)}</span>
      </div>

      {item.no_signal_flag && <Badge variant="warning">No Signal</Badge>}
    </Card>
  )
}
