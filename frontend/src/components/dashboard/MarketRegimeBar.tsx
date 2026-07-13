import { TrendingDown, TrendingUp } from 'lucide-react'
import { cn } from '@/lib/utils'
import type { IndexRegime, MarketRegimeResponse } from '@/types/api'

interface MarketRegimeBarProps {
  data: MarketRegimeResponse
}

const REGIME_CFG = {
  bull:       { label: '상승 추세', color: 'text-emerald-400', bg: 'bg-emerald-400/10 border-emerald-400/25' },
  correction: { label: '조정 구간', color: 'text-amber-400',   bg: 'bg-amber-400/10 border-amber-400/25' },
  bear:       { label: '하락 추세', color: 'text-rose-400',    bg: 'bg-rose-400/10 border-rose-400/25' },
  sideways:   { label: '횡보',     color: 'text-slate-400',   bg: 'bg-slate-400/10 border-slate-400/25' },
  unknown:    { label: '확인 중',  color: 'text-muted-foreground', bg: 'bg-muted/10 border-border' },
} as const

/** 현재가 대비 이평선 이격(%) — ma가 없으면 null */
function maDistancePct(current: number, ma: number | null): number | null {
  if (!ma || current <= 0) return null
  return ((current - ma) / ma) * 100
}

function formatSignedPct(value: number): string {
  return `${value > 0 ? '+' : ''}${value.toFixed(1)}%`
}

// 체제 판정 규칙(backend market_regime_service._classify_regime)과 같은 기준의 이평선을
// 보여준다 — 판정에 쓰이지 않는 120일선만 보여주면 라벨과 숫자가 모순돼 보인다.
const REGIME_RULE_NOTE =
  '판정 기준: 종가가 20일선 위 + 20일선이 60일선 위 = 상승 추세 · 종가가 60일선 아래 = 하락 추세 · 그 사이 = 조정 구간'

function IndexChip({ name, regime }: { name: string; regime: IndexRegime }) {
  const cfg = REGIME_CFG[regime.regime] ?? REGIME_CFG.unknown
  const isUp = regime.change_pct >= 0
  const dist20 = maDistancePct(regime.current, regime.ma20)
  const dist60 = maDistancePct(regime.current, regime.ma60)
  return (
    <div className={cn('flex items-center gap-2 rounded-lg border px-3 py-1.5', cfg.bg)} title={REGIME_RULE_NOTE}>
      <span className="text-xs font-semibold text-muted-foreground">{name}</span>
      {regime.current > 0 && (
        <span className="font-mono text-sm font-semibold tabular-nums">
          {regime.current.toLocaleString()}
        </span>
      )}
      {regime.change_pct !== 0 && (
        <span className={cn('flex items-center gap-0.5 text-xs font-medium', isUp ? 'text-emerald-400' : 'text-rose-400')}>
          {isUp ? <TrendingUp size={10} /> : <TrendingDown size={10} />}
          {isUp ? '+' : ''}{regime.change_pct.toFixed(2)}%
        </span>
      )}
      <span className={cn('rounded px-1.5 py-0.5 text-xs font-semibold', cfg.color)}>
        {cfg.label}
      </span>
      {(dist20 !== null || dist60 !== null) && (
        <span className="hidden text-xs text-muted-foreground lg:inline">
          {dist20 !== null && <>20일선 {formatSignedPct(dist20)}</>}
          {dist20 !== null && dist60 !== null && ' · '}
          {dist60 !== null && <>60일선 {formatSignedPct(dist60)}</>}
        </span>
      )}
    </div>
  )
}

export function MarketRegimeBar({ data }: MarketRegimeBarProps) {
  const overallCfg = REGIME_CFG[data.overall_regime] ?? REGIME_CFG.unknown
  return (
    <div className="flex flex-wrap items-center gap-2 rounded-lg border border-border bg-card/60 px-3 py-2">
      <div className="flex items-center gap-1.5">
        <span className="text-xs font-medium text-muted-foreground">시장 체제</span>
        <span className={cn('text-xs font-bold', overallCfg.color)}>{overallCfg.label}</span>
      </div>
      <div className="h-3 w-px bg-border" />
      <div className="flex flex-wrap gap-2">
        <IndexChip name="KOSPI" regime={data.kospi} />
        <IndexChip name="KOSDAQ" regime={data.kosdaq} />
      </div>
    </div>
  )
}

/** 시장 체제에 따라 경고 메시지를 반환 (null=경고 없음) */
export function getRegimeWarning(overall: MarketRegimeResponse['overall_regime']): string | null {
  if (overall === 'bear') return '⚠️ 시장 하락 추세 — 매수 신호 신뢰도 저하, 손절 기준 엄격 적용'
  if (overall === 'correction') return '⚠️ 시장 조정 구간 — 포지션 크기 축소 및 트리거 확인 철저'
  return null
}
