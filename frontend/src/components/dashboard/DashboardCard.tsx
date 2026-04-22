import { useState, type MouseEvent, type ReactNode } from 'react'
import { useNavigate } from 'react-router-dom'
import { useMutation } from '@tanstack/react-query'
import { Bookmark, ChevronDown, Star } from 'lucide-react'

import type { DashboardItem, OutcomeIntent } from '@/types/api'
import { outcomesApi } from '@/lib/api'
import { Badge } from '@/components/ui/Badge'
import { Card } from '@/components/ui/Card'
import { ProbBar } from '@/components/ui/ProbBar'
import {
  cn,
  fmtPct,
  fmtTurnoverBillion,
  getPatternBias,
  INTRADAY_COLLECTION_MODE_LABELS,
  PATTERN_NAMES,
  SETUP_STAGE_LABELS,
  STATE_COLORS,
  STATE_LABELS,
} from '@/lib/utils'
import { useAppStore } from '@/store/app'

interface DashboardCardProps {
  item: DashboardItem
  intradayPreset?: string
}

export function DashboardCard({ item }: DashboardCardProps) {
  const nav = useNavigate()
  const { addToWatchlist, removeFromWatchlist, isWatched, setTimeframe } = useAppStore()
  const watched = isWatched(item.symbol.code)
  const [detailsOpen, setDetailsOpen] = useState(false)
  const [savedId, setSavedId] = useState<number | null>(null)
  const [selectedIntent, setSelectedIntent] = useState<OutcomeIntent>('breakout_wait')

  const saveMutation = useMutation({
    mutationFn: () =>
      outcomesApi.record({
        symbol_code: item.symbol.code,
        symbol_name: item.symbol.name,
        pattern_type: item.pattern_type ?? 'no_pattern',
        timeframe: item.timeframe,
        signal_date: new Date().toISOString().slice(0, 10),
        entry_price: 0,
        target_price: null,
        stop_price: null,
        intent: selectedIntent,
        outcome: 'pending',
        notes: `intent:${selectedIntent}`,
        p_up_at_signal: item.p_up,
        composite_score_at_signal: item.trade_readiness_score ?? 0,
        textbook_similarity_at_signal: item.textbook_similarity,
        trade_readiness_at_signal: item.trade_readiness_score ?? 0,
      }),
    onSuccess: result => setSavedId(result.id),
  })

  const toggleWatch = (event: MouseEvent) => {
    event.stopPropagation()
    if (watched) {
      removeFromWatchlist(item.symbol.code)
    } else {
      addToWatchlist({ code: item.symbol.code, name: item.symbol.name, market: item.symbol.market })
    }
  }

  const openChart = () => {
    setTimeframe(item.timeframe)
    nav(`/chart/${item.symbol.code}`)
  }

  return (
    <Card className="space-y-4 cursor-pointer" onClick={openChart}>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 space-y-2">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-mono text-xs text-muted-foreground">#{item.rank}</span>
            <h3 className="text-base font-semibold">{item.symbol.name}</h3>
            <span className="font-mono text-xs text-muted-foreground">{item.symbol.code}</span>
            {watched && <Badge variant="warning">관심종목</Badge>}
            <Badge variant="muted">{item.timeframe_label}</Badge>
            <Badge variant={actionPlanVariant(item.action_plan)}>{item.action_plan_label}</Badge>
          </div>

          <div className="flex flex-wrap items-center gap-1.5">
            {item.pattern_type ? (
              <Badge variant={getPatternBias(item.pattern_type)}>{PATTERN_NAMES[item.pattern_type] ?? item.pattern_type}</Badge>
            ) : (
              <Badge variant="muted">No Signal</Badge>
            )}
            {item.state && (
              <span className={cn('rounded px-1.5 py-0.5 text-xs', STATE_COLORS[item.state] ?? 'bg-white/5 text-slate-300')}>
                {STATE_LABELS[item.state] ?? item.state}
              </span>
            )}
            <Badge variant="muted">{SETUP_STAGE_LABELS[item.setup_stage] ?? item.setup_stage}</Badge>
            {item.fetch_status === 'placeholder_pending' && <Badge variant="warning">임시 후보</Badge>}
            {item.live_intraday_candidate && <Badge variant="bullish">Live 우선</Badge>}
          </div>
        </div>

        <div className="flex items-center gap-1">
          <IconButton
            onClick={toggleWatch}
            title={watched ? '관심종목 해제' : '관심종목 추가'}
            active={watched}
            activeTone="text-yellow-400"
          >
            <Star size={14} className={watched ? 'fill-yellow-400' : ''} />
          </IconButton>
          <IconButton
            onClick={event => {
              event.stopPropagation()
              if (savedId != null || saveMutation.isPending) return
              saveMutation.mutate()
            }}
            title={savedId != null ? '저장됨' : '신호 저장'}
            active={savedId != null}
            activeTone="text-primary"
          >
            <Bookmark size={14} className={savedId != null ? 'fill-current' : ''} />
          </IconButton>
        </div>
      </div>

      <ProbBar p_up={item.p_up} p_down={item.p_down} />

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <KeyMetric label="준비도" value={fmtPct(item.trade_readiness_score ?? 0, 0)} tone={scoreTone(item.trade_readiness_score ?? 0)} />
        <KeyMetric label="진입 구간" value={fmtPct(item.entry_window_score ?? 0, 0)} tone={scoreTone(item.entry_window_score ?? 0)} />
        <KeyMetric label="신선도" value={fmtPct(item.freshness_score ?? 0, 0)} tone={scoreTone(item.freshness_score ?? 0)} />
        <KeyMetric label="데이터 품질" value={fmtPct(item.data_quality, 0)} tone={scoreTone(item.data_quality)} />
      </div>

      <div className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_200px]">
        <SummaryPane title="실전 판단" accent="primary" text={item.action_plan_summary || item.reason_summary} />
        <div className="rounded-lg border border-border bg-background/55 p-3">
          <div className="text-xs text-muted-foreground">다음 확인</div>
          <div className="mt-2 text-sm font-medium leading-relaxed">{item.next_trigger || '트리거 대기'}</div>
          <div className="mt-3 text-xs text-muted-foreground">
            신뢰도 {fmtPct(item.confidence, 0)} · 손익비 {item.reward_risk_ratio.toFixed(2)}
          </div>
        </div>
      </div>

      {(item.risk_flags?.length > 0 || item.fetch_message) && (
        <div className="rounded-lg border border-orange-400/15 bg-orange-400/5 p-3 text-xs leading-relaxed text-orange-100">
          <span className="font-medium text-orange-200">주의:</span>{' '}
          {item.risk_flags?.[0] || item.fetch_message || '데이터 메모를 확인해 주세요.'}
        </div>
      )}

      <button
        type="button"
        onClick={event => {
          event.stopPropagation()
          setDetailsOpen(prev => !prev)
        }}
        className="inline-flex items-center gap-2 text-xs font-medium text-muted-foreground transition-colors hover:text-foreground"
      >
        상세 정보 {detailsOpen ? '접기' : '보기'}
        <ChevronDown size={14} className={cn('transition-transform', detailsOpen && 'rotate-180')} />
      </button>

      {detailsOpen && (
        <div className="space-y-3 rounded-lg border border-border bg-background/45 p-4" onClick={event => event.stopPropagation()}>
          <div className="grid grid-cols-2 gap-3 text-xs text-muted-foreground sm:grid-cols-3">
            <DetailRow label="교과서 유사도" value={fmtPct(item.textbook_similarity, 0)} />
            <DetailRow label="표본 신뢰도" value={fmtPct(item.sample_reliability, 0)} />
            <DetailRow label="Edge" value={fmtPct(item.historical_edge_score, 0)} />
            <DetailRow label="거래대금" value={fmtTurnoverBillion(item.avg_turnover_billion)} />
            <DetailRow label="수집 모드" value={INTRADAY_COLLECTION_MODE_LABELS[item.intraday_collection_mode] ?? item.intraday_collection_mode} />
            <DetailRow label="평균 MFE/MAE" value={`${fmtPct(item.avg_mfe_pct, 0)} / ${fmtPct(item.avg_mae_pct, 0)}`} />
          </div>

          <div className="rounded-lg border border-border bg-background/55 p-3">
            <div className="text-xs font-medium text-foreground">신호 저장 분류</div>
            <div className="mt-2 flex flex-wrap gap-2">
              {OUTCOME_INTENT_OPTIONS.map(option => (
                <button
                  key={option.value}
                  type="button"
                  onClick={event => {
                    event.stopPropagation()
                    setSelectedIntent(option.value)
                  }}
                  disabled={savedId != null || saveMutation.isPending}
                  className={cn(
                    'rounded-md border px-2.5 py-1.5 text-[11px] transition-colors disabled:cursor-not-allowed disabled:opacity-50',
                    selectedIntent === option.value
                      ? 'border-primary/30 bg-primary/15 text-primary'
                      : 'border-border bg-card/65 text-muted-foreground hover:text-foreground',
                  )}
                >
                  {option.label}
                </button>
              ))}
            </div>
            <p className="mt-2 text-[11px] leading-relaxed text-muted-foreground">
              {OUTCOME_INTENT_DESCRIPTIONS[selectedIntent]}
            </p>
          </div>

          {item.trade_readiness_summary && <SummaryPane title={item.trade_readiness_label} accent="emerald" text={item.trade_readiness_summary} />}
          {item.entry_window_summary && <SummaryPane title={item.entry_window_label} accent="sky" text={item.entry_window_summary} />}
          {item.freshness_summary && <SummaryPane title={item.freshness_label} accent="violet" text={item.freshness_summary} />}

          <div className="rounded-lg border border-border bg-background/55 p-3">
            <div className="text-xs font-medium text-foreground">멀티 타임프레임 맥락</div>
            <p className="mt-2 text-xs leading-relaxed text-muted-foreground">{item.confluence_summary}</p>
            <p className="mt-2 text-xs leading-relaxed text-foreground/90">{item.scenario_text}</p>
          </div>
        </div>
      )}
    </Card>
  )
}

function IconButton({
  children,
  onClick,
  title,
  active,
  activeTone,
}: {
  children: ReactNode
  onClick: (event: MouseEvent<HTMLButtonElement>) => void
  title: string
  active: boolean
  activeTone: string
}) {
  return (
    <button
      onClick={onClick}
      title={title}
      className={cn(
        'rounded-lg p-2 text-muted-foreground transition-colors hover:bg-background/70',
        active && `bg-background/70 ${activeTone}`,
      )}
    >
      {children}
    </button>
  )
}

function KeyMetric({ label, value, tone }: { label: string; value: string; tone: string }) {
  return (
    <div className="rounded-lg border border-border bg-background/55 p-3">
      <div className="text-[11px] text-muted-foreground">{label}</div>
      <div className={cn('mt-1 text-sm font-semibold', tone)}>{value}</div>
    </div>
  )
}

function SummaryPane({
  title,
  text,
  accent,
}: {
  title: string
  text: string
  accent: 'primary' | 'emerald' | 'sky' | 'violet'
}) {
  const accentClass = {
    primary: 'border-primary/20 bg-primary/6',
    emerald: 'border-emerald-400/20 bg-emerald-400/6',
    sky: 'border-sky-400/20 bg-sky-400/6',
    violet: 'border-violet-400/20 bg-violet-400/6',
  }[accent]

  return (
    <div className={cn('rounded-lg border p-3', accentClass)}>
      <div className="text-xs font-medium text-foreground">{title}</div>
      <p className="mt-2 text-xs leading-relaxed text-muted-foreground">{text}</p>
    </div>
  )
}

function DetailRow({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-[11px] text-muted-foreground">{label}</div>
      <div className="mt-1 text-sm font-medium text-foreground">{value}</div>
    </div>
  )
}

function actionPlanVariant(plan: string): 'bullish' | 'warning' | 'muted' | 'neutral' {
  if (plan === 'ready_now') return 'bullish'
  if (plan === 'watch') return 'neutral'
  if (plan === 'recheck') return 'warning'
  return 'muted'
}

function scoreTone(score: number) {
  if (score >= 0.72) return 'text-emerald-300'
  if (score >= 0.56) return 'text-sky-200'
  if (score >= 0.4) return 'text-amber-200'
  return 'text-muted-foreground'
}

const OUTCOME_INTENT_OPTIONS: Array<{ value: OutcomeIntent; label: string }> = [
  { value: 'observe', label: '관망' },
  { value: 'breakout_wait', label: '돌파 대기' },
  { value: 'pullback_candidate', label: '눌림 매수 후보' },
  { value: 'invalidation_watch', label: '무효화 감시' },
]

const OUTCOME_INTENT_DESCRIPTIONS: Record<OutcomeIntent, string> = {
  observe: '아직 진입보다 구조 관찰이 더 중요한 후보입니다.',
  breakout_wait: '트리거 돌파와 거래 반응이 확인될 때 대응할 후보입니다.',
  pullback_candidate: '돌파 뒤 눌림이나 지지 확인을 기다리는 후보입니다.',
  invalidation_watch: '신규 진입보다 무효화 여부를 먼저 체크해야 하는 후보입니다.',
}
