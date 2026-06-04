import { useQuery } from '@tanstack/react-query'
import { Activity, CheckCircle2, TriangleAlert } from 'lucide-react'

import { Card } from '@/components/ui/Card'
import { QueryError } from '@/components/ui/QueryError'
import { outcomesApi } from '@/lib/api'
import { cn, fmtPct } from '@/lib/utils'

/**
 * Reliability of the shown probabilities: for each predicted-probability bin we
 * compare the model's predicted win rate against the *realized* win rate from
 * resolved signals. This is the feedback loop that proves whether "상승 확률 65%"
 * actually means 65%.
 */
export function CalibrationPanel({ timeframe }: { timeframe?: string }) {
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['outcomes', 'calibration', timeframe ?? 'all'],
    queryFn: () => outcomesApi.calibration(timeframe),
    staleTime: 60_000,
  })

  return (
    <Card className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <div className="text-sm font-semibold">확률 신뢰도 · 캘리브레이션</div>
          <p className="text-xs text-muted-foreground">
            실제로 결과가 확정된 신호에서, 예측 확률 구간별로 모델이 말한 승률과 실제 승률이 얼마나 일치하는지 비교합니다.
          </p>
        </div>
      </div>

      {isLoading ? (
        <div className="py-8 text-center text-xs text-muted-foreground">신뢰도 리포트를 불러오는 중입니다...</div>
      ) : isError || !data ? (
        <QueryError message="캘리브레이션 리포트를 불러오지 못했습니다." onRetry={() => refetch()} />
      ) : (
        <CalibrationBody data={data} />
      )}
    </Card>
  )
}

function CalibrationBody({ data }: { data: import('@/types/api').CalibrationReport }) {
  const reliability = data.reliability
  const isGood = reliability.startsWith('양호')
  const isWarn = reliability.includes('과신') || reliability.includes('과소')
  const isInsufficient = reliability.includes('표본 부족')

  const tone = isGood
    ? 'border-emerald-400/30 bg-emerald-400/5 text-emerald-300'
    : isWarn
      ? 'border-amber-400/30 bg-amber-400/5 text-amber-300'
      : isInsufficient
        ? 'border-border bg-muted/30 text-muted-foreground'
        : 'border-sky-400/30 bg-sky-400/5 text-sky-300'
  const Icon = isGood ? CheckCircle2 : isWarn ? TriangleAlert : Activity
  const gapSign = data.mean_gap >= 0 ? '+' : ''

  return (
    <div className="space-y-4">
      <div className={cn('flex flex-wrap items-center gap-2 rounded-lg border px-3 py-2 text-sm', tone)}>
        <Icon size={16} />
        <span className="font-semibold">{reliability}</span>
        {!isInsufficient && (
          <span className="text-xs text-muted-foreground">
            예측−실제 편차 {gapSign}
            {fmtPct(data.mean_gap, 1)}
          </span>
        )}
      </div>

      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        <Metric label="채점된 신호" value={`${data.scored_total.toLocaleString('ko-KR')}건`} />
        <Metric label="평균 예측" value={fmtPct(data.mean_predicted, 0)} />
        <Metric label="실제 승률" value={fmtPct(data.base_rate, 0)} />
        <Metric label="Brier / ECE" value={`${data.brier_score.toFixed(3)} / ${fmtPct(data.ece, 0)}`} />
      </div>

      {data.bins.length === 0 ? (
        <div className="rounded-lg border border-border bg-background/60 px-3 py-4 text-xs leading-relaxed text-muted-foreground">
          아직 결과가 확정된 신호가 충분하지 않습니다. 신호를 저장하고 익절·손절이 평가되면 이 표가 채워지며, 그때부터 확률의 실제
          정확도를 추적할 수 있습니다.
        </div>
      ) : (
        <div className="space-y-1.5">
          <div className="flex items-center gap-2 text-[11px] text-muted-foreground">
            <div className="w-[88px] shrink-0">예측 확률 구간</div>
            <div className="flex-1">예측(회색) vs 실제(컬러)</div>
            <div className="w-12 shrink-0 text-right">표본</div>
          </div>
          {data.bins.map(bin => (
            <div key={`${bin.lower}-${bin.upper}`} className="flex items-center gap-2 text-xs">
              <div className="w-[88px] shrink-0 tabular-nums text-muted-foreground">
                {fmtPct(bin.lower, 0)}–{fmtPct(bin.upper, 0)}
              </div>
              <div className="flex-1 space-y-0.5">
                <BarRow label="예측" value={bin.predicted} barClass="bg-slate-400/70" />
                <BarRow label="실제" value={bin.observed} barClass="bg-primary" />
              </div>
              <div className="w-12 shrink-0 text-right tabular-nums text-muted-foreground">{bin.count}건</div>
            </div>
          ))}
        </div>
      )}

      <p className="text-[11px] leading-relaxed text-muted-foreground">
        Brier는 확률 예측의 평균 제곱오차(낮을수록 좋음), ECE는 구간별 예측−실제 평균 괴리입니다. 표본이 적을수록 이 수치는 흔들릴 수
        있으니 충분한 신호가 쌓인 뒤 해석하세요.
      </p>
    </div>
  )
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-border bg-background/60 p-2.5">
      <div className="text-[11px] text-muted-foreground">{label}</div>
      <div className="mt-0.5 text-sm font-semibold tabular-nums">{value}</div>
    </div>
  )
}

function BarRow({ label, value, barClass }: { label: string; value: number; barClass: string }) {
  const pct = Math.max(0, Math.min(100, value * 100))
  return (
    <div className="flex items-center gap-1.5">
      <span className="w-7 shrink-0 text-right text-[10px] text-muted-foreground">{label}</span>
      <div className="h-2 flex-1 overflow-hidden rounded bg-muted/40">
        <div className={cn('h-2 rounded', barClass)} style={{ width: `${pct}%` }} />
      </div>
      <span className="w-9 shrink-0 text-right text-[11px] tabular-nums">{fmtPct(value, 0)}</span>
    </div>
  )
}
