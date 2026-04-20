import { Loader2 } from 'lucide-react'

import type { DashboardResponse } from '@/types/api'
import { QueryError } from '@/components/ui/QueryError'
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
  const hasItems = Boolean(data && data.items.length > 0)
  const isPlaceholderOnly = hasItems && data!.items.every(item => item.fetch_status === 'placeholder_pending')

  return (
    <div className="space-y-3">
      <div>
        <h2 className="text-sm font-semibold">{title}</h2>
        <p className="text-xs text-muted-foreground">{subtitle}</p>
      </div>

      {isPlaceholderOnly && (
        <div className="rounded-lg border border-amber-500/20 bg-amber-500/5 p-3 text-xs text-amber-100">
          빠른 예열 후보를 먼저 보여주고 있습니다. 현재 카드의 확률, 준비도, 패턴 정보는 임시값일 수 있으며
          백그라운드 스캔이 끝나면 실제 분석 결과로 자동 교체됩니다.
        </div>
      )}

      {isLoading ? (
        <div className="flex h-24 flex-col items-center justify-center gap-2 text-muted-foreground">
          <Loader2 size={18} className="animate-spin" />
          <span className="text-xs">후보를 불러오는 중입니다.</span>
        </div>
      ) : isError ? (
        <QueryError compact onRetry={onRetry} />
      ) : !data || data.items.length === 0 ? (
        <p className="py-4 text-center text-xs text-muted-foreground">{emptyMessage ?? '조건에 맞는 종목이 아직 없습니다.'}</p>
      ) : (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {data.items.map(item => (
            <DashboardCard key={`${item.timeframe}-${item.symbol.code}`} item={item} intradayPreset={intradayPreset} />
          ))}
        </div>
      )}
    </div>
  )
}
