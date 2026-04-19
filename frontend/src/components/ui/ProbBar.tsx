import { fmtPct } from '@/lib/utils'

interface ProbBarProps {
  p_up: number
  p_down: number
  size?: 'sm' | 'md'
}

export function ProbBar({ p_up, p_down, size = 'sm' }: ProbBarProps) {
  const h = size === 'sm' ? 'h-1.5' : 'h-2.5'

  return (
    <div className="space-y-1">
      <div className={`flex w-full overflow-hidden rounded-full bg-muted ${h}`}>
        <div className="bg-green-500 transition-all" style={{ width: `${p_up * 100}%` }} />
        <div className="bg-red-500 transition-all" style={{ width: `${p_down * 100}%` }} />
      </div>
      <div className="flex justify-between text-xs text-muted-foreground">
        <span className="text-green-400">상승 {fmtPct(p_up)}</span>
        <span className="text-red-400">하락 {fmtPct(p_down)}</span>
      </div>
    </div>
  )
}
