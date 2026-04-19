import { useMemo, useState, type ReactNode } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Activity, BarChart2, Clock3, RefreshCw, ShieldCheck, Target } from 'lucide-react'

import { Card } from '@/components/ui/Card'
import { Badge } from '@/components/ui/Badge'
import { patternsApi } from '@/lib/api'
import { fmtPct, PATTERN_NAMES } from '@/lib/utils'
import type { PatternStatsEntry } from '@/types/api'

type ReportTimeframe = '1mo' | '1wk' | '1d'

const TIMEFRAME_FILTERS: Array<{ value: ReportTimeframe; label: string }> = [
  { value: '1mo', label: '월봉' },
  { value: '1wk', label: '주봉' },
  { value: '1d', label: '일봉' },
]

export default function PatternPerformancePage() {
  const [timeframe, setTimeframe] = useState<ReportTimeframe>('1d')
  const queryClient = useQueryClient()
  const { data, isLoading } = useQuery({
    queryKey: ['patterns', 'stats'],
    queryFn: patternsApi.stats,
    staleTime: 60_000,
  })
  const refreshMutation = useMutation({
    mutationFn: patternsApi.refreshStats,
    onSuccess: () => {
      window.setTimeout(() => {
        queryClient.invalidateQueries({ queryKey: ['patterns', 'stats'] })
      }, 1500)
    },
  })

  const filtered = useMemo(
    () =>
      (data?.items ?? [])
        .filter(item => item.timeframe === timeframe)
        .sort((a, b) => {
          if (b.historical_edge_score !== a.historical_edge_score) return b.historical_edge_score - a.historical_edge_score
          if (b.win_rate !== a.win_rate) return b.win_rate - a.win_rate
          return b.sample_size - a.sample_size
        }),
    [data, timeframe],
  )

  const summary = useMemo(() => {
    if (!filtered.length) return null
    const avgEdge = filtered.reduce((sum, item) => sum + item.historical_edge_score, 0) / filtered.length
    const avgWinRate = filtered.reduce((sum, item) => sum + item.win_rate, 0) / filtered.length
    const totalSamples = filtered.reduce((sum, item) => sum + item.sample_size, 0)
    return { avgEdge, avgWinRate, totalSamples }
  }, [filtered])

  return (
    <div className="space-y-5">
      <div className="flex items-center gap-3">
        <BarChart2 size={18} className="text-primary" />
        <div>
          <h1 className="text-xl font-bold">패턴 성과 리포트</h1>
          <p className="text-xs text-muted-foreground">
            패턴별 백테스트 승률, 표본 수, 평균 MFE/MAE, 평균 결과 바 수를 타임프레임별로 읽는 화면입니다.
          </p>
        </div>
      </div>

      <Card className="space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex flex-wrap gap-2">
            {TIMEFRAME_FILTERS.map(option => (
              <button
                key={option.value}
                onClick={() => setTimeframe(option.value)}
                className={`rounded-md px-3 py-1.5 text-xs transition-colors ${
                  timeframe === option.value
                    ? 'bg-primary text-primary-foreground'
                    : 'border border-border bg-card text-muted-foreground hover:text-foreground'
                }`}
              >
                {option.label}
              </button>
            ))}
          </div>
          <button
            onClick={() => refreshMutation.mutate()}
            disabled={refreshMutation.isPending}
            className="inline-flex items-center gap-1.5 rounded-md border border-border bg-background/60 px-3 py-1.5 text-xs text-muted-foreground transition-colors hover:text-foreground disabled:cursor-not-allowed disabled:opacity-60"
          >
            <RefreshCw size={13} className={refreshMutation.isPending ? 'animate-spin' : ''} />
            {refreshMutation.isPending ? '재계산 요청 중' : '백테스트 재계산'}
          </button>
        </div>

        {refreshMutation.isSuccess && (
          <div className="rounded-lg border border-primary/20 bg-primary/5 px-3 py-2 text-xs text-muted-foreground">
            백테스트 재계산을 백그라운드로 시작했습니다. 잠시 후 리포트가 새 통계로 갱신됩니다.
          </div>
        )}

        {summary && (
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
            <SummaryCell icon={<ShieldCheck size={14} className="text-primary" />} label="평균 edge" value={fmtPct(summary.avgEdge, 0)} />
            <SummaryCell icon={<Target size={14} className="text-primary" />} label="평균 승률" value={fmtPct(summary.avgWinRate, 0)} />
            <SummaryCell icon={<Activity size={14} className="text-primary" />} label="총 표본 수" value={`${summary.totalSamples}건`} />
          </div>
        )}
      </Card>

      {isLoading ? (
        <div className="py-10 text-center text-muted-foreground">리포트를 불러오는 중..</div>
      ) : (
        <div className="grid grid-cols-1 gap-3 xl:grid-cols-2">
          {filtered.map((item, index) => (
            <PatternStatCard key={`${item.timeframe}-${item.pattern_type}`} item={item} rank={index + 1} />
          ))}
        </div>
      )}
    </div>
  )
}

function SummaryCell({ icon, label, value }: { icon: ReactNode; label: string; value: string }) {
  return (
    <div className="rounded-lg border border-border bg-background/60 p-3">
      <div className="flex items-center gap-2 text-xs text-muted-foreground">
        {icon}
        {label}
      </div>
      <div className="mt-1 text-base font-semibold">{value}</div>
    </div>
  )
}

function PatternStatCard({ item, rank }: { item: PatternStatsEntry; rank: number }) {
  const badgeVariant =
    item.historical_edge_score >= 0.65 ? 'bullish' : item.historical_edge_score >= 0.45 ? 'muted' : 'warning'

  return (
    <Card className="space-y-3">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-mono text-xs text-muted-foreground">#{rank}</span>
            <span className="text-sm font-semibold">{PATTERN_NAMES[item.pattern_type] ?? item.pattern_type}</span>
            <Badge variant={badgeVariant}>edge {fmtPct(item.historical_edge_score, 0)}</Badge>
            <Badge variant="muted">{item.timeframe_label}</Badge>
          </div>
          <div className="mt-1 text-xs text-muted-foreground">
            승률 {fmtPct(item.win_rate, 0)} / 표본 {item.sample_size}건 / 적중 {item.wins}건
          </div>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-2 text-xs text-muted-foreground">
        <span>평균 MFE {fmtPct(item.avg_mfe_pct)}</span>
        <span className="text-right">평균 MAE {fmtPct(item.avg_mae_pct)}</span>
        <span className="flex items-center gap-1">
          <Clock3 size={12} />
          평균 결과 바 수 {item.avg_bars_to_outcome.toFixed(1)}
        </span>
        <span className="text-right">wins/total {item.wins}/{item.total}</span>
      </div>
    </Card>
  )
}
