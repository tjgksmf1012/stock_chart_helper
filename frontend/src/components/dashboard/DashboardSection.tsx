import type { DashboardResponse } from '@/types/api'
import { DashboardCard } from './DashboardCard'
import { Loader2 } from 'lucide-react'

interface DashboardSectionProps {
  title: string
  subtitle: string
  data: DashboardResponse | undefined
  isLoading: boolean
}

export function DashboardSection({ title, subtitle, data, isLoading }: DashboardSectionProps) {
  return (
    <div className="space-y-3">
      <div>
        <h2 className="text-sm font-semibold">{title}</h2>
        <p className="text-xs text-muted-foreground">{subtitle}</p>
      </div>

      {isLoading ? (
        <div className="flex items-center justify-center h-24 text-muted-foreground">
          <Loader2 size={18} className="animate-spin" />
        </div>
      ) : !data || data.items.length === 0 ? (
        <p className="text-xs text-muted-foreground py-4 text-center">해당 종목 없음</p>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-3">
          {data.items.map(item => <DashboardCard key={item.symbol.code} item={item} />)}
        </div>
      )}
    </div>
  )
}
