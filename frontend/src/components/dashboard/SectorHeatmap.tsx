import { useState } from 'react'
import { ChevronDown, ChevronUp } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Card } from '@/components/ui/Card'
import type { SectorEntry } from '@/types/api'

interface SectorHeatmapProps {
  sectors: SectorEntry[]
}

function SectorBar({ sector }: { sector: SectorEntry }) {
  const total = sector.bullish_count + sector.bearish_count
  const bullPct = total > 0 ? (sector.bullish_count / total) * 100 : 50
  const net = sector.net_score

  const netColor = net > 0
    ? 'text-emerald-400'
    : net < 0
      ? 'text-rose-400'
      : 'text-muted-foreground'

  return (
    <div className="flex items-center gap-3">
      <span className="w-20 shrink-0 truncate text-xs text-muted-foreground">{sector.sector_name}</span>
      <div className="relative h-1.5 flex-1 overflow-hidden rounded-full bg-muted/30">
        <div
          className="absolute left-0 top-0 h-full rounded-full bg-emerald-400/50 transition-all"
          style={{ width: `${bullPct}%` }}
        />
      </div>
      <span className={cn('w-10 shrink-0 text-right text-xs font-semibold tabular-nums', netColor)}>
        {net > 0 ? `+${net}` : net}
      </span>
      {sector.top_symbols.length > 0 && (
        <span className="hidden max-w-[120px] truncate text-xs text-muted-foreground sm:block">
          {sector.top_symbols.slice(0, 2).join(', ')}
        </span>
      )}
    </div>
  )
}

export function SectorHeatmap({ sectors }: SectorHeatmapProps) {
  const [open, setOpen] = useState(false)

  if (!sectors.length) return null

  const bullSectors = sectors.filter(s => s.net_score > 0).slice(0, 5)
  const bearSectors = sectors.filter(s => s.net_score < 0).slice(0, 5)

  return (
    <Card className="space-y-3">
      <button
        onClick={() => setOpen(v => !v)}
        className="flex w-full items-center justify-between text-left"
      >
        <div className="flex items-center gap-2">
          <span className="text-sm font-semibold">섹터 패턴 분포</span>
          {bullSectors.length > 0 && (
            <span className="rounded bg-emerald-400/15 px-1.5 py-0.5 text-xs font-medium text-emerald-400">
              매수 강세 {bullSectors.length}
            </span>
          )}
          {bearSectors.length > 0 && (
            <span className="rounded bg-rose-400/15 px-1.5 py-0.5 text-xs font-medium text-rose-400">
              매도 강세 {bearSectors.length}
            </span>
          )}
        </div>
        {open
          ? <ChevronUp size={14} className="shrink-0 text-muted-foreground" />
          : <ChevronDown size={14} className="shrink-0 text-muted-foreground" />
        }
      </button>

      {open && (
        <div className="space-y-2.5">
          <div className="flex items-center gap-3 text-xs text-muted-foreground">
            <span className="w-20">섹터</span>
            <span className="flex-1 text-center">매수↑ / 매도↓ 비율</span>
            <span className="w-10 text-right">순</span>
            <span className="hidden sm:block sm:w-[120px]">주요 종목</span>
          </div>
          <div className="space-y-2">
            {sectors.slice(0, 12).map(sector => (
              <SectorBar key={sector.sector_name} sector={sector} />
            ))}
          </div>
          <p className="text-xs text-muted-foreground">
            현재 스캔 결과 기준 집계. 순 = 매수 패턴 수 − 매도 패턴 수.
          </p>
        </div>
      )}
    </Card>
  )
}
