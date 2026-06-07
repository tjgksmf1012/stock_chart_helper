import { TrendingDown, TrendingUp, Minus } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Card } from '@/components/ui/Card'
import type { MoneyFlowData } from '@/types/api'

interface MoneyFlowCardProps {
  data: MoneyFlowData
}

function FlowRow({
  label,
  value3d,
  value10d,
}: {
  label: string
  value3d: number
  value10d: number
}) {
  const isUp3d = value3d > 0
  const isUp10d = value10d > 0
  const color3d = value3d === 0 ? 'text-muted-foreground' : isUp3d ? 'text-emerald-400' : 'text-rose-400'
  const color10d = value10d === 0 ? 'text-muted-foreground' : isUp10d ? 'text-emerald-400/70' : 'text-rose-400/70'
  return (
    <div className="flex items-center gap-3">
      <span className="w-14 shrink-0 text-xs text-muted-foreground">{label}</span>
      <div className="flex items-center gap-1">
        {value3d === 0 ? (
          <Minus size={11} className="text-muted-foreground" />
        ) : isUp3d ? (
          <TrendingUp size={11} className="text-emerald-400" />
        ) : (
          <TrendingDown size={11} className="text-rose-400" />
        )}
        <span className={cn('text-xs font-bold tabular-nums', color3d)}>
          {value3d > 0 ? '+' : ''}{value3d.toFixed(0)}억
        </span>
        <span className="text-xs text-muted-foreground">3일</span>
      </div>
      <div className="flex items-center gap-1">
        <span className={cn('text-xs tabular-nums', color10d)}>
          {value10d > 0 ? '+' : ''}{value10d.toFixed(0)}억
        </span>
        <span className="text-xs text-muted-foreground">10일</span>
      </div>
    </div>
  )
}

function MiniSparkline({ daily }: { daily: MoneyFlowData['daily'] }) {
  if (!daily.length) return null
  const values = daily.slice(-15).map(d => d.foreign)
  const maxAbs = Math.max(...values.map(Math.abs), 1)
  return (
    <div className="flex h-8 items-end gap-0.5">
      {values.map((v, i) => (
        <div
          key={i}
          className={cn(
            'flex-1 min-w-0 rounded-sm',
            v >= 0 ? 'bg-emerald-400/50' : 'bg-rose-400/50',
          )}
          style={{ height: `${Math.max(12, (Math.abs(v) / maxAbs) * 100)}%` }}
        />
      ))}
    </div>
  )
}

const ALIGN_CFG = {
  aligned:  { label: '✅ 수급 정렬',     color: 'text-emerald-400', bg: 'border-emerald-400/20 bg-emerald-400/6' },
  diverged: { label: '⚠️ 수급 역방향',   color: 'text-rose-400',    bg: 'border-rose-400/20 bg-rose-400/6' },
  mixed:    { label: '↕ 외인/기관 혼조', color: 'text-amber-400',   bg: 'border-amber-400/20 bg-amber-400/6' },
  neutral:  { label: '— 수급 중립',      color: 'text-muted-foreground', bg: 'border-border bg-background/40' },
} as const

export function MoneyFlowCard({ data }: MoneyFlowCardProps) {
  const align = data.alignment as keyof typeof ALIGN_CFG
  const cfg = ALIGN_CFG[align] ?? ALIGN_CFG.neutral

  return (
    <Card className="space-y-3">
      <div className="flex items-center justify-between">
        <span className="text-sm font-semibold">외국인 / 기관 수급</span>
        <span className={cn('rounded border px-2 py-0.5 text-xs font-semibold', cfg.bg, cfg.color)}>
          {cfg.label}
        </span>
      </div>

      <div className="space-y-2">
        <FlowRow
          label="외국인"
          value3d={data.foreign_net_3d}
          value10d={data.foreign_net_10d}
        />
        <FlowRow
          label="기관"
          value3d={data.institution_net_3d}
          value10d={data.institution_net_10d}
        />
      </div>

      {data.daily.length > 0 && (
        <div className="space-y-1">
          <p className="text-xs text-muted-foreground">외국인 순매수 추이 (최근 15거래일)</p>
          <MiniSparkline daily={data.daily} />
          <div className="flex justify-between text-xs text-muted-foreground">
            <span>{(data.daily[data.daily.length - Math.min(15, data.daily.length)] ?? data.daily[0])?.date.slice(5) ?? ''}</span>
            <span>{data.daily[data.daily.length - 1]?.date.slice(5) ?? ''}</span>
          </div>
        </div>
      )}

      {data.alignment_note && (
        <p className="rounded border border-border bg-muted/20 p-2 text-xs leading-relaxed text-muted-foreground">
          {data.alignment_note}
        </p>
      )}
    </Card>
  )
}
