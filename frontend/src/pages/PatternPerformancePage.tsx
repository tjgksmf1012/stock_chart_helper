import { useMemo, useState, type ReactNode } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Activity, BarChart2, Clock3, Flag, Loader2, RefreshCw, ShieldCheck, ShieldAlert, Target } from 'lucide-react'

import { Badge } from '@/components/ui/Badge'
import { Card } from '@/components/ui/Card'
import { QueryError } from '@/components/ui/QueryError'
import { outcomesApi, patternsApi } from '@/lib/api'
import { fmtPct, PATTERN_NAMES } from '@/lib/utils'
import type { OutcomeRecord, OutcomeStatus, PatternStatsEntry } from '@/types/api'

type ReportTimeframe = '1mo' | '1wk' | '1d'

const TIMEFRAME_FILTERS: Array<{ value: ReportTimeframe; label: string }> = [
  { value: '1mo', label: '월봉' },
  { value: '1wk', label: '주봉' },
  { value: '1d', label: '일봉' },
]

export default function PatternPerformancePage() {
  const [timeframe, setTimeframe] = useState<ReportTimeframe>('1d')
  const [activeTab, setActiveTab] = useState<'stats' | 'records'>('stats')
  const queryClient = useQueryClient()

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['patterns', 'stats'],
    queryFn: patternsApi.stats,
    staleTime: 60_000,
  })

  const outcomesQ = useQuery({
    queryKey: ['outcomes'],
    queryFn: outcomesApi.list,
    staleTime: 30_000,
    enabled: activeTab === 'records',
  })

  const outcomeUpdateMutation = useMutation({
    mutationFn: ({ id, outcome }: { id: number; outcome: OutcomeStatus }) =>
      outcomesApi.update(id, { outcome }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['outcomes'] }),
  })

  const outcomeDeleteMutation = useMutation({
    mutationFn: (id: number) => outcomesApi.remove(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['outcomes'] }),
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
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-3">
          <BarChart2 size={18} className="text-primary" />
          <div>
            <h1 className="text-xl font-bold">패턴 성과 리포트</h1>
            <p className="text-xs text-muted-foreground">
              패턴별 백테스트 우위, 표본 수, 평균 MFE·MAE, 결과 도달 바 수를 타임프레임별로 읽고 어느 패턴을 더 믿을지 판단합니다.
            </p>
          </div>
        </div>
        <div className="flex gap-1 rounded-lg border border-border bg-card p-1">
          <button
            onClick={() => setActiveTab('stats')}
            className={`rounded-md px-3 py-1.5 text-xs transition-colors ${activeTab === 'stats' ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:text-foreground'}`}
          >
            백테스트 통계
          </button>
          <button
            onClick={() => setActiveTab('records')}
            className={`rounded-md px-3 py-1.5 text-xs transition-colors ${activeTab === 'records' ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:text-foreground'}`}
          >
            내 기록
          </button>
        </div>
      </div>

      {activeTab === 'stats' && (
        <>
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
                <SummaryCell icon={<ShieldCheck size={14} className="text-primary" />} label="평균 우위" value={fmtPct(summary.avgEdge, 0)} />
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
          ) : isError ? (
            <Card>
              <QueryError message="패턴 통계를 불러오지 못했습니다." onRetry={() => refetch()} />
            </Card>
          ) : filtered.length === 0 ? (
            <Card className="py-10 text-center text-sm text-muted-foreground">선택한 타임프레임에는 아직 집계된 패턴 통계가 없습니다.</Card>
          ) : (
            <div className="grid grid-cols-1 gap-3 xl:grid-cols-2">
              {filtered.map((item, index) => (
                <PatternStatCard key={`${item.timeframe}-${item.pattern_type}`} item={item} rank={index + 1} />
              ))}
            </div>
          )}
        </>
      )}

      {activeTab === 'records' && (
        <OutcomesTab
          records={outcomesQ.data ?? []}
          isLoading={outcomesQ.isLoading}
          isError={outcomesQ.isError}
          onRetry={() => outcomesQ.refetch()}
          onUpdateOutcome={(id, outcome) => outcomeUpdateMutation.mutate({ id, outcome })}
          onDelete={(id) => outcomeDeleteMutation.mutate(id)}
        />
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
          {item.wins}승 / 전체 {item.total}건
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

// ─── Outcomes tab ─────────────────────────────────────────────────────────────

const OUTCOME_LABELS: Record<string, string> = {
  pending: '대기 중',
  win: '성공',
  loss: '실패',
  stopped_out: '손절',
  cancelled: '취소',
}

const OUTCOME_BADGE_VARIANT: Record<string, 'bullish' | 'warning' | 'muted' | 'neutral' | 'bearish'> = {
  pending: 'muted',
  win: 'bullish',
  loss: 'bearish',
  stopped_out: 'warning',
  cancelled: 'muted',
}

function OutcomesTab({
  records,
  isLoading,
  isError,
  onRetry,
  onUpdateOutcome,
  onDelete,
}: {
  records: OutcomeRecord[]
  isLoading: boolean
  isError: boolean
  onRetry: () => void
  onUpdateOutcome: (id: number, outcome: OutcomeStatus) => void
  onDelete: (id: number) => void
}) {
  const completed = records.filter(r => r.outcome !== 'pending' && r.outcome !== 'cancelled')
  const wins = completed.filter(r => r.outcome === 'win')
  const pending = records.filter(r => r.outcome === 'pending')

  if (isLoading) {
    return (
      <Card className="flex items-center justify-center gap-2 py-8 text-sm text-muted-foreground">
        <Loader2 size={16} className="animate-spin" />
        기록을 불러오는 중입니다...
      </Card>
    )
  }

  if (isError) {
    return (
      <Card>
        <QueryError message="기록을 불러오지 못했습니다." onRetry={onRetry} />
      </Card>
    )
  }

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <SummaryCell icon={<Flag size={14} className="text-primary" />} label="전체 기록" value={`${records.length}건`} />
        <SummaryCell icon={<ShieldCheck size={14} className="text-emerald-300" />} label="성공" value={`${wins.length}건`} />
        <SummaryCell icon={<ShieldAlert size={14} className="text-amber-300" />} label="대기 중" value={`${pending.length}건`} />
        <SummaryCell
          icon={<Activity size={14} className="text-primary" />}
          label="승률"
          value={completed.length > 0 ? `${Math.round((wins.length / completed.length) * 100)}%` : '-'}
        />
      </div>

      {records.length === 0 ? (
        <Card className="py-10 text-center text-sm text-muted-foreground">
          아직 저장된 신호 기록이 없습니다. 차트 화면이나 대시보드 카드에서 신호를 저장해 보세요.
        </Card>
      ) : (
        <div className="space-y-2">
          {records.map(record => (
            <OutcomeRecordCard
              key={record.id}
              record={record}
              onUpdateOutcome={onUpdateOutcome}
              onDelete={onDelete}
            />
          ))}
        </div>
      )}
    </div>
  )
}

function OutcomeRecordCard({
  record,
  onUpdateOutcome,
  onDelete,
}: {
  record: OutcomeRecord
  onUpdateOutcome: (id: number, outcome: OutcomeStatus) => void
  onDelete: (id: number) => void
}) {
  const isFalsePositive = record.notes === 'user_false_positive'

  return (
    <Card className="space-y-2">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-sm font-semibold">{record.symbol_name}</span>
            <span className="font-mono text-xs text-muted-foreground">{record.symbol_code}</span>
            <Badge variant={OUTCOME_BADGE_VARIANT[record.outcome] ?? 'muted'}>
              {isFalsePositive ? '오탐 신고' : (OUTCOME_LABELS[record.outcome] ?? record.outcome)}
            </Badge>
            {record.pattern_type && (
              <Badge variant="muted">{record.pattern_type}</Badge>
            )}
            <Badge variant="muted">{record.timeframe}</Badge>
          </div>
          <div className="mt-0.5 flex flex-wrap gap-3 text-xs text-muted-foreground">
            <span>진입가 {record.entry_price.toLocaleString('ko-KR')}원</span>
            {record.target_price != null && <span>목표 {record.target_price.toLocaleString('ko-KR')}원</span>}
            {record.stop_price != null && <span>손절 {record.stop_price.toLocaleString('ko-KR')}원</span>}
            {record.p_up_at_signal != null && <span>당시 상승확률 {Math.round(record.p_up_at_signal * 100)}%</span>}
            <span>저장일 {record.signal_date}</span>
          </div>
        </div>

        <button
          onClick={() => record.id != null && onDelete(record.id)}
          className="shrink-0 rounded p-1 text-xs text-muted-foreground hover:text-red-400"
          title="기록 삭제"
        >
          ✕
        </button>
      </div>

      {record.outcome === 'pending' && !isFalsePositive && (
        <div className="flex flex-wrap gap-1.5">
          {(['win', 'loss', 'stopped_out', 'cancelled'] as OutcomeStatus[]).map(status => (
            <button
              key={status}
              onClick={() => record.id != null && onUpdateOutcome(record.id, status)}
              className={`rounded border px-2.5 py-1 text-xs transition-colors ${
                status === 'win'
                  ? 'border-emerald-400/30 text-emerald-300 hover:bg-emerald-400/10'
                  : status === 'loss'
                    ? 'border-red-400/30 text-red-300 hover:bg-red-400/10'
                    : status === 'stopped_out'
                      ? 'border-amber-400/30 text-amber-300 hover:bg-amber-400/10'
                      : 'border-border text-muted-foreground hover:text-foreground'
              }`}
            >
              {OUTCOME_LABELS[status]}
            </button>
          ))}
        </div>
      )}
    </Card>
  )
}
