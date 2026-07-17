import { useQuery } from '@tanstack/react-query'
import { CalendarRange } from 'lucide-react'

import { Card } from '@/components/ui/Card'
import { labApi } from '@/lib/api'
import { cn } from '@/lib/utils'
import type { OutlookHorizon } from '@/types/api'

/**
 * 확률적 전망 — "내일 몇% 오른다"는 점 예측 대신,
 * 과거 분포 기반 80% 구간과 "그 구간이 실제로 맞았는지"(실측 적중률)를 함께 보여준다.
 * 적중률이 80%에서 크게 벗어나면 지금 분포가 과거와 다르다는 경고다.
 */
export function OutlookCard({ symbol }: { symbol: string }) {
  const outlookQ = useQuery({
    queryKey: ['symbol-outlook', symbol],
    queryFn: () => labApi.outlook(symbol),
    staleTime: 600_000,
    retry: false,
    enabled: Boolean(symbol),
  })

  if (outlookQ.isLoading) {
    return <Card className="text-xs text-muted-foreground">확률 구간을 계산하는 중입니다...</Card>
  }
  if (outlookQ.isError || !outlookQ.data || outlookQ.data.horizons.length === 0) {
    return null // 이력 부족 종목은 카드 자체를 숨긴다 (빈 껍데기 노출 방지)
  }

  const { horizons, conditional_signal: conditional, note } = outlookQ.data

  return (
    <Card className="space-y-3">
      <div className="flex items-center gap-2 text-sm font-semibold">
        <CalendarRange size={15} className="text-primary" />
        확률적 전망 (구간)
      </div>

      <div className="overflow-x-auto">
        <table className="w-full min-w-[420px] text-xs">
          <thead>
            <tr className="border-b border-border/70 text-left text-muted-foreground">
              <th className="py-1.5 pr-3 font-medium">기간</th>
              <th className="py-1.5 pr-3 font-medium">80% 구간</th>
              <th className="py-1.5 pr-3 font-medium">중앙값</th>
              <th className="py-1.5 font-medium">실측 적중률</th>
            </tr>
          </thead>
          <tbody>
            {horizons.map(h => (
              <tr key={h.horizon_days} className="border-b border-border/40">
                <td className="py-1.5 pr-3 font-medium text-foreground">{h.label}</td>
                <td className="py-1.5 pr-3 font-mono">
                  <span className="text-red-300">{pct(h.q10)}</span>
                  <span className="mx-1 text-muted-foreground">~</span>
                  <span className="text-emerald-300">{pct(h.q90)}</span>
                </td>
                <td className={cn('py-1.5 pr-3 font-mono', h.q50 >= 0 ? 'text-emerald-300/90' : 'text-red-300/90')}>
                  {pct(h.q50)}
                </td>
                <td className="py-1.5">
                  <CoverageBadge coverage={h.coverage} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {conditional && (
        <div className="rounded-lg border border-emerald-400/20 bg-emerald-400/5 p-2.5 text-[11px] leading-relaxed">
          <span className="font-medium text-emerald-200">검증 전략 조건부</span>{' '}
          <span className="text-muted-foreground">
            — {conditional.strategy_label}의 신호({conditional.signal_date})가 활성입니다:{' '}
            {conditional.holding_days}일 보유 기대값 {pct(conditional.ev_pct)} (95% CI {pct(conditional.ci_95[0])} ~{' '}
            {pct(conditional.ci_95[1])}, 워크포워드 검증 기준)
          </span>
        </div>
      )}

      <p className="text-[11px] leading-relaxed text-muted-foreground/80">{note}</p>
    </Card>
  )
}

function CoverageBadge({ coverage }: { coverage: OutlookHorizon['coverage'] }) {
  if (!coverage) {
    return <span className="text-[10px] text-muted-foreground">검증 표본 부족</span>
  }
  const pctValue = Math.round(coverage.coverage * 100)
  // 명목 80%에서 ±10%p 이상 벗어나면 경고색 — 구간을 그대로 믿으면 안 된다는 신호
  const off = Math.abs(coverage.coverage - coverage.nominal) > 0.1
  return (
    <span
      className={cn(
        'rounded border px-1.5 py-0.5 text-[10px] font-semibold',
        off
          ? 'border-amber-400/30 bg-amber-400/10 text-amber-300'
          : 'border-emerald-400/25 bg-emerald-400/8 text-emerald-300/90',
      )}
      title={`과거 ${coverage.n}회 검증 중 ${coverage.hits}회 적중 (목표 ${Math.round(coverage.nominal * 100)}%)`}
    >
      {pctValue}%{off && ' ⚠'}
    </span>
  )
}

function pct(v: number): string {
  return `${v > 0 ? '+' : ''}${(v * 100).toFixed(1)}%`
}
