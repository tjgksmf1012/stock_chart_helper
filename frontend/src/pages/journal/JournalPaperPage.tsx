import { useQuery } from '@tanstack/react-query'
import { ClipboardCheck } from 'lucide-react'

import { Card } from '@/components/ui/Card'
import { QueryError } from '@/components/ui/QueryError'
import { labApi } from '@/lib/api'
import { cn } from '@/lib/utils'
import type { LabPaperTradeSummaryItem } from '@/types/api'

import { DRIFT_CFG } from './JournalStrategiesPage'

/** 기록 > 실측 (종이매매) — 신호가 실제로 백테스트만큼 벌고 있는지 전략별로 추적한다. */
export default function JournalPaperPage() {
  const paperQ = useQuery({ queryKey: ['lab-paper-summary'], queryFn: labApi.paperTradesSummary, staleTime: 120_000 })
  const strategies = paperQ.data?.strategies ?? []

  return (
    <div className="space-y-6">
      <div>
        <div className="flex items-center gap-2 text-xl font-bold">
          <ClipboardCheck size={20} className="text-primary" />
          실측 (종이매매)
        </div>
        <p className="mt-1 max-w-3xl text-sm leading-relaxed text-muted-foreground">
          신호가 나올 때마다 자동으로 종이매매로 기록하고, 백테스트와 같은 규칙으로 청산해 실측 성적을 만듭니다.
          실측이 백테스트 신뢰구간을 밑돌면 전략이 시장에서 이탈했다는 경고입니다.
        </p>
      </div>

      {paperQ.isLoading && <Card className="text-sm text-muted-foreground">실측 성적을 불러오는 중...</Card>}
      {paperQ.isError && <QueryError message="실측 성적을 불러오지 못했습니다." onRetry={() => paperQ.refetch()} />}

      {!paperQ.isLoading && !paperQ.isError && strategies.length === 0 && (
        <Card className="text-sm text-muted-foreground">
          아직 기록된 종이매매가 없습니다. 오늘 탭에 신호가 나타나면 자동으로 여기에 쌓이기 시작합니다.
        </Card>
      )}

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        {strategies.map(item => (
          <PaperStrategyCard key={item.strategy_id} item={item} />
        ))}
      </div>
    </div>
  )
}

function PaperStrategyCard({ item }: { item: LabPaperTradeSummaryItem }) {
  const driftCfg = DRIFT_CFG[item.drift]

  return (
    <Card className="space-y-3">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="text-sm font-semibold text-foreground">{item.label}</div>
          <div className="mt-0.5 font-mono text-[11px] text-muted-foreground">{item.strategy_id}</div>
        </div>
        {driftCfg && <span className={cn('rounded border px-2 py-1 text-[11px] font-semibold', driftCfg.cls)}>{driftCfg.label}</span>}
      </div>

      <div className="grid grid-cols-3 gap-3 text-center">
        <PaperMetric label="청산된 실측" value={`${item.realized_n}건`} />
        <PaperMetric
          label="거래당 실측"
          value={item.realized_n > 0 && item.realized_ev_pct != null ? signedPct(item.realized_ev_pct) : '-'}
        />
        <PaperMetric label="진행중" value={`${item.open_count}건`} />
      </div>

      {item.drift === 'drifting' && (
        <p className="rounded-lg border border-red-400/20 bg-red-400/5 p-2.5 text-[11px] leading-relaxed text-red-300/90">
          실측 기대값이 백테스트 신뢰구간 하한({signedPct(item.backtest_ci_low ?? 0)})을 밑돕니다 — 이 전략의 신호는 관찰
          등급으로 낮춰 보는 편이 안전합니다.
        </p>
      )}
      {item.drift === 'insufficient' && (
        <p className="text-[11px] leading-relaxed text-muted-foreground">
          청산 표본이 20건 미만이라 아직 판정하지 않습니다. 표본이 쌓이면 자동으로 백테스트와 비교합니다.
        </p>
      )}
      {item.drift === 'ok' && item.backtest_ci_low != null && (
        <p className="text-[11px] leading-relaxed text-muted-foreground">
          실측이 백테스트 신뢰구간 하한({signedPct(item.backtest_ci_low)}) 위에 있습니다 — 검증 성적이 유지되고 있습니다.
        </p>
      )}
    </Card>
  )
}

function PaperMetric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-border bg-background/50 p-2.5">
      <div className="text-[11px] text-muted-foreground">{label}</div>
      <div className="mt-0.5 text-sm font-semibold tabular-nums text-foreground">{value}</div>
    </div>
  )
}

function signedPct(value: number): string {
  return `${value > 0 ? '+' : ''}${(value * 100).toFixed(2)}%`
}
