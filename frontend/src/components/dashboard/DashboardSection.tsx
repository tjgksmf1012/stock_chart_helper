import { Loader2 } from 'lucide-react'

import type { DashboardResponse } from '@/types/api'
import { DashboardCard } from './DashboardCard'

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
        <div className="flex h-24 items-center justify-center text-muted-foreground">
          <Loader2 size={18} className="animate-spin" />
        </div>
      ) : !data || data.items.length === 0 ? (
        <p className="py-4 text-center text-xs text-muted-foreground">조건에 맞는 종목이 없습니다.</p>
      ) : (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {data.items.map(item => <DashboardCard key={item.symbol.code} item={item} />)}
        </div>
      )}
    </div>
  )
}
