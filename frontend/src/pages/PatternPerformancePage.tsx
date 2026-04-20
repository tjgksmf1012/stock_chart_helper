import { useMemo, useState, type ReactNode } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Activity, BarChart2, Clock3, RefreshCw, ShieldCheck, ShieldAlert, Target } from 'lucide-react'

import { Badge } from '@/components/ui/Badge'
import { Card } from '@/components/ui/Card'
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
    const robustCount = filtered.filter(item => item.sample_size >= 30 && item.historical_edge_score >= 0.55).length
    const top = filtered[0]
    const caution = [...filtered]
      .filter(item => item.sample_size >= 15)
      .sort((a, b) => a.historical_edge_score - b.historical_edge_score)[0]
    return { avgEdge, avgWinRate, totalSamples, robustCount, top, caution }
  }, [filtered])

  return (
    <div className="space-y-5">
      <div className="flex items-center gap-3">
        <BarChart2 size={18} className="text-primary" />
        <div>
          <h1 className="text-xl font-bold">패턴 성과 리포트</h1>
          <p className="text-xs text-muted-foreground">
            패턴별 백테스트 우위, 표본 수, 평균 MFE·MAE, 결과 도달 바 수를 타임프레임별로 읽고 어느 패턴을 더 믿을지 판단합니다.
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
            {refreshMutation.isPending ? '통계 갱신 요청 중' : '백테스트 통계 새로고침'}
          </button>
        </div>

        {refreshMutation.isSuccess && (
          <div className="rounded-lg border border-primary/20 bg-primary/5 px-3 py-2 text-xs text-muted-foreground">
            백테스트 통계를 백그라운드에서 다시 계산하고 있습니다. 잠시 후 최신 수치로 바뀝니다.
          </div>
        )}

        {summary && (
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <SummaryCell icon={<ShieldCheck size={14} className="text-primary" />} label="평균 edge" value={fmtPct(summary.avgEdge, 0)} />
            <SummaryCell icon={<Target size={14} className="text-primary" />} label="평균 승률" value={fmtPct(summary.avgWinRate, 0)} />
            <SummaryCell icon={<Activity size={14} className="text-primary" />} label="총 표본 수" value={`${summary.totalSamples.toLocaleString('ko-KR')}건`} />
            <SummaryCell icon={<ShieldAlert size={14} className="text-primary" />} label="참고 강한 패턴 수" value={`${summary.robustCount}개`} />
          </div>
        )}
      </Card>

      {summary && (
        <div className="grid grid-cols-1 gap-3 xl:grid-cols-2">
          <InsightCard
            title="상대적으로 믿을 만한 패턴"
            accent="border-emerald-400/20 bg-emerald-400/5"
            item={summary.top}
            description={
              summary.top
                ? `${PATTERN_NAMES[summary.top.pattern_type] ?? summary.top.pattern_type}은 현재 ${timeframeLabel(timeframe)} 기준으로 edge와 승률이 모두 상위권입니다. 다만 현재 차트의 신선도와 진입 구간까지 함께 봐야 실제 매매 품질이 맞춰집니다.`
                : '아직 상위 패턴을 계산할 데이터가 부족합니다.'
            }
          />
          <InsightCard
            title="보수적으로 봐야 할 패턴"
            accent="border-amber-400/20 bg-amber-400/5"
            item={summary.caution}
            description={
              summary.caution
                ? `${PATTERN_NAMES[summary.caution.pattern_type] ?? summary.caution.pattern_type}은 표본이 어느 정도 있지만 상대적 edge가 낮은 편입니다. 차트가 좋아 보여도 추가 확인 신호 없이 바로 추격하는 건 보수적으로 보는 편이 안전합니다.`
                : '아직 경고 패턴을 분리할 만큼 표본이 충분하지 않습니다.'
            }
          />
        </div>
      )}

      <Card className="space-y-2 border-primary/20 bg-primary/5">
        <div className="text-sm font-semibold">읽는 법</div>
        <p className="text-xs leading-relaxed text-muted-foreground">
          edge와 승률은 패턴군 전체의 평균적인 우세를 보여주는 참고값입니다. 실전에서는 현재 차트의 신선도, 거래 준비도, 진입 구간,
          데이터 품질까지 함께 봐야 하고, 표본이 작거나 최근 시장 환경이 많이 바뀐 패턴은 숫자를 더 보수적으로 해석하는 편이 좋습니다.
        </p>
      </Card>

      {isLoading ? (
        <div className="py-10 text-center text-muted-foreground">리포트를 불러오는 중입니다...</div>
      ) : filtered.length === 0 ? (
        <Card className="py-10 text-center text-sm text-muted-foreground">선택한 타임프레임에는 아직 집계된 패턴 통계가 없습니다.</Card>
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

function InsightCard({
  title,
  accent,
  item,
  description,
}: {
  title: string
  accent: string
  item: PatternStatsEntry | undefined
  description: string
}) {
  return (
    <Card className={`space-y-3 ${accent}`}>
      <div className="text-sm font-semibold">{title}</div>
      {item ? (
        <>
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant={item.historical_edge_score >= 0.6 ? 'bullish' : item.historical_edge_score >= 0.45 ? 'neutral' : 'warning'}>
              edge {fmtPct(item.historical_edge_score, 0)}
            </Badge>
            <span className="text-sm font-semibold">{PATTERN_NAMES[item.pattern_type] ?? item.pattern_type}</span>
            <span className="text-xs text-muted-foreground">
              승률 {fmtPct(item.win_rate, 0)} · 표본 {item.sample_size.toLocaleString('ko-KR')}건
            </span>
          </div>
          <p className="text-xs leading-relaxed text-muted-foreground">{description}</p>
        </>
      ) : (
        <p className="text-xs leading-relaxed text-muted-foreground">{description}</p>
      )}
    </Card>
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
            승률 {fmtPct(item.win_rate, 0)} / 표본 {item.sample_size.toLocaleString('ko-KR')}건 / 성공 {item.wins}건
          </div>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-2 text-xs text-muted-foreground">
        <span>평균 MFE {fmtPct(item.avg_mfe_pct)}</span>
        <span className="text-right">평균 MAE {fmtPct(item.avg_mae_pct)}</span>
        <span className="flex items-center gap-1">
          <Clock3 size={12} />
          평균 결과 도달 {item.avg_bars_to_outcome.toFixed(1)}바
        </span>
        <span className="text-right">
          wins / total {item.wins}/{item.total}
        </span>
      </div>

      <div className="rounded-lg border border-border bg-background/60 p-2.5 text-xs leading-relaxed text-muted-foreground">
        {patternInterpretation(item)}
      </div>
    </Card>
  )
}

function patternInterpretation(item: PatternStatsEntry): string {
  const name = PATTERN_NAMES[item.pattern_type] ?? item.pattern_type
  if (item.sample_size < 15) {
    return `${name}은 아직 표본이 작아서 수치가 좋아 보여도 참고용으로만 보는 편이 안전합니다.`
  }
  if (item.historical_edge_score >= 0.65 && item.win_rate >= 0.55) {
    return `${name}은 통계상 상대적으로 강한 편입니다. 현재 차트에서도 신선도와 진입 구간이 받쳐주면 우선순위를 높여 볼 만합니다.`
  }
  if (item.historical_edge_score >= 0.5) {
    return `${name}은 중립 이상 패턴입니다. 숫자만 믿기보다 현재 거래대금과 위치를 함께 확인하면 해석이 더 안정적입니다.`
  }
  return `${name}은 상대적으로 edge가 약한 편입니다. 현재 차트가 좋아 보여도 추가 확인 신호 없이 바로 추격하는 것은 보수적으로 볼 필요가 있습니다.`
}

function timeframeLabel(timeframe: ReportTimeframe): string {
  if (timeframe === '1mo') return '월봉'
  if (timeframe === '1wk') return '주봉'
  return '일봉'
}
