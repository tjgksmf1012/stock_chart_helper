import { useMemo, useState } from 'react'
import { ChevronDown, Loader2 } from 'lucide-react'

import type { DashboardResponse } from '@/types/api'
import { QueryError } from '@/components/ui/QueryError'
import { cn } from '@/lib/utils'
import { DashboardCard } from './DashboardCard'

interface DashboardSectionProps {
  title: string
  subtitle: string
  data: DashboardResponse | undefined
  isLoading: boolean
  isError?: boolean
  onRetry?: () => void
  intradayPreset?: string
  emptyMessage?: string
}

const INITIAL_VISIBLE_COUNT = 4

export function DashboardSection({
  title,
  subtitle,
  data,
  isLoading,
  isError,
  onRetry,
  intradayPreset,
  emptyMessage,
}: DashboardSectionProps) {
  const [expanded, setExpanded] = useState(false)
  const items = data?.items ?? []
  const visibleItems = useMemo(
    () => (expanded ? items : items.slice(0, INITIAL_VISIBLE_COUNT)),
    [expanded, items],
  )

  const hasItems = items.length > 0
  const hiddenCount = Math.max(0, items.length - INITIAL_VISIBLE_COUNT)
  const isPlaceholderOnly = hasItems && items.every(item => item.fetch_status === 'placeholder_pending')

  return (
    <section className="space-y-4">
      <div className="flex flex-col gap-2 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <h2 className="text-base font-semibold">{title}</h2>
          <p className="mt-1 text-sm text-muted-foreground">{subtitle}</p>
        </div>
        {hasItems && (
          <div className="text-xs text-muted-foreground">
            {items.length}개 후보
            {hiddenCount > 0 && !expanded ? ` · 상위 ${INITIAL_VISIBLE_COUNT}개 먼저 표시` : ''}
          </div>
        )}
      </div>

      {isPlaceholderOnly && (
        <div className="rounded-lg border border-amber-500/20 bg-amber-500/5 p-3 text-xs leading-relaxed text-amber-100">
          지금은 빠른 미리보기 후보가 먼저 보이고 있습니다. 백그라운드 계산이 끝나면 실제 분석 카드로 자동 교체됩니다.
        </div>
      )}

      {isLoading ? (
        <div className="flex h-28 flex-col items-center justify-center gap-2 rounded-lg border border-border bg-background/40 text-muted-foreground">
          <Loader2 size={18} className="animate-spin" />
          <span className="text-xs">후보를 불러오는 중입니다.</span>
        </div>
      ) : isError ? (
        <QueryError compact onRetry={onRetry} />
      ) : !hasItems ? (
        <div className="rounded-lg border border-dashed border-border bg-background/30 px-4 py-8 text-center text-sm text-muted-foreground">
          {emptyMessage ?? '조건에 맞는 후보가 아직 없습니다.'}
        </div>
      ) : (
        <>
          <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
            {visibleItems.map(item => (
              <DashboardCard key={`${item.timeframe}-${item.symbol.code}`} item={item} intradayPreset={intradayPreset} />
            ))}
          </div>

          {hiddenCount > 0 && (
            <button
              onClick={() => setExpanded(prev => !prev)}
              className="inline-flex items-center gap-2 rounded-lg border border-border bg-background/50 px-3 py-2 text-xs font-medium text-muted-foreground transition-colors hover:text-foreground"
            >
              {expanded ? '접기' : `${hiddenCount}개 더 보기`}
              <ChevronDown size={14} className={cn('transition-transform', expanded && 'rotate-180')} />
            </button>
          )}
        </>
      )}
    </section>
  )
}
