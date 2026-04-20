import type { MouseEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { AlertTriangle, Layers3, Star } from 'lucide-react'

import type { DashboardItem } from '@/types/api'
import { Badge } from '@/components/ui/Badge'
import { Card } from '@/components/ui/Card'
import { ProbBar } from '@/components/ui/ProbBar'
import {
  cn,
  fmtPct,
  fmtTurnoverBillion,
  getPatternBias,
  INTRADAY_COLLECTION_MODE_LABELS,
  INTRADAY_SESSION_LABELS,
  PATTERN_NAMES,
  SETUP_STAGE_LABELS,
  STATE_COLORS,
  STATE_LABELS,
  WYCKOFF_LABELS,
} from '@/lib/utils'
import { useAppStore } from '@/store/app'

interface DashboardCardProps {
  item: DashboardItem
  intradayPreset?: string
}

export function DashboardCard({ item, intradayPreset }: DashboardCardProps) {
  const nav = useNavigate()
  const { addToWatchlist, removeFromWatchlist, isWatched, setTimeframe } = useAppStore()
  const watched = isWatched(item.symbol.code)
  const isIntraday = ['1m', '15m', '30m', '60m'].includes(item.timeframe)

  const toggleWatch = (event: MouseEvent) => {
    event.stopPropagation()
    if (watched) {
      removeFromWatchlist(item.symbol.code)
    } else {
      addToWatchlist({ code: item.symbol.code, name: item.symbol.name, market: item.symbol.market })
    }
  }

  return (
    <Card
      className="cursor-pointer space-y-3"
      onClick={() => {
        setTimeframe(item.timeframe)
        nav(`/chart/${item.symbol.code}`)
      }}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="font-mono text-xs text-muted-foreground">#{item.rank}</span>
            <span className="truncate text-sm font-semibold">{item.symbol.name}</span>
            <span className="font-mono text-xs text-muted-foreground">{item.symbol.code}</span>
            <span className="text-xs text-muted-foreground">{item.symbol.market}</span>
          </div>

          <div className="mt-2 flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
            <Badge variant="muted">{item.timeframe_label}</Badge>
            <Badge variant={actionPlanVariant(item.action_plan)}>{item.action_plan_label}</Badge>
            <Badge variant={scoreVariant(item.trade_readiness_score ?? 0)}>준비 {fmtPct(item.trade_readiness_score ?? 0, 0)}</Badge>
            <Badge variant={scoreVariant(item.entry_window_score ?? 0)}>진입 {fmtPct(item.entry_window_score ?? 0, 0)}</Badge>
            <Badge variant={scoreVariant(item.freshness_score ?? 0)}>신선 {fmtPct(item.freshness_score ?? 0, 0)}</Badge>
            <Badge variant={scoreVariant(item.reentry_score ?? 0)}>재진입 {fmtPct(item.reentry_score ?? 0, 0)}</Badge>
            <Badge variant={scoreVariant(item.active_setup_score ?? 0)}>활성 {fmtPct(item.active_setup_score ?? 0, 0)}</Badge>
            <Badge variant={item.data_quality >= 0.8 ? 'bullish' : item.data_quality >= 0.6 ? 'neutral' : 'warning'}>
              품질 {fmtPct(item.data_quality, 0)}
            </Badge>
            {item.fetch_status === 'placeholder_pending' && <Badge variant="warning">임시 후보</Badge>}
            {item.live_intraday_candidate && <Badge variant="bullish">live {fmtPct(item.live_intraday_priority_score, 0)}</Badge>}
            {isIntraday && !item.live_intraday_candidate && (
              <Badge variant="muted">{INTRADAY_COLLECTION_MODE_LABELS[item.intraday_collection_mode] ?? item.intraday_collection_mode}</Badge>
            )}
          </div>

          <div className="mt-2 flex flex-wrap items-center gap-1.5">
            {item.pattern_type ? <Badge variant={getPatternBias(item.pattern_type)}>{PATTERN_NAMES[item.pattern_type] ?? item.pattern_type}</Badge> : <Badge variant="muted">No Signal</Badge>}
            {item.state && <span className={cn('rounded px-1 py-0.5 text-xs', STATE_COLORS[item.state] ?? 'text-slate-300 bg-slate-500/10')}>{STATE_LABELS[item.state] ?? item.state}</span>}
            <Badge variant="muted">{SETUP_STAGE_LABELS[item.setup_stage] ?? item.setup_stage}</Badge>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <div className="text-right">
            <div className="text-xs text-muted-foreground">완성도</div>
            <div className="font-mono text-sm font-semibold text-primary">{fmtPct(item.completion_proximity, 0)}</div>
          </div>
          <button
            onClick={toggleWatch}
            className={cn(
              'rounded p-1.5 transition-colors',
              watched ? 'text-yellow-400 hover:text-yellow-300' : 'text-muted-foreground hover:text-yellow-400',
            )}
            title={watched ? '관심종목 해제' : '관심종목 추가'}
          >
            <Star size={14} className={watched ? 'fill-yellow-400' : ''} />
          </button>
        </div>
      </div>

      <ProbBar p_up={item.p_up} p_down={item.p_down} />

      {item.action_plan_summary && <SummaryBlock tone="primary" title="실전 판단" score={item.action_priority_score}>{item.action_plan_summary}</SummaryBlock>}
      {item.trade_readiness_summary && <SummaryBlock tone="emerald" title={item.trade_readiness_label} score={item.trade_readiness_score}>{item.trade_readiness_summary}</SummaryBlock>}
      {item.entry_window_summary && <SummaryBlock tone="sky" title={item.entry_window_label} score={item.entry_window_score}>{item.entry_window_summary}</SummaryBlock>}
      {item.freshness_summary && <SummaryBlock tone="violet" title={item.freshness_label} score={item.freshness_score}>{item.freshness_summary}</SummaryBlock>}
      {item.reentry_summary && (
        <SummaryBlock tone="amber" title={item.reentry_case_label || item.reentry_label} score={item.reentry_score}>
          <div className="space-y-1">
            <div>{item.reentry_summary}</div>
            {item.reentry_profile_label && item.reentry_profile_key !== 'none' && (
              <div className="text-[11px] text-amber-100/90">
                해석 기준: {item.reentry_profile_label}
                {item.reentry_profile_summary ? ` · ${item.reentry_profile_summary}` : ''}
              </div>
            )}
            {item.reentry_trigger && <div className="text-[11px] text-amber-100/90">확인 포인트: {item.reentry_trigger}</div>}
            {item.reentry_factors?.length > 0 && (
              <div className="grid grid-cols-2 gap-x-3 gap-y-1 text-[11px] text-amber-100/90">
                {item.reentry_factors.slice(0, 4).map(factor => (
                  <span key={factor.label}>
                    {factor.label} {fmtPct(factor.score ?? 0, 0)} · {Math.round((factor.weight ?? 0) * 100)}%
                  </span>
                ))}
              </div>
            )}
          </div>
        </SummaryBlock>
      )}
      {item.active_setup_summary && <SummaryBlock tone="cyan" title={item.active_setup_label}>{item.active_setup_summary}</SummaryBlock>}

      {(item.next_trigger || item.risk_flags?.length > 0) && (
        <div className="rounded-lg border border-orange-400/15 bg-orange-400/5 p-2.5 text-xs leading-relaxed text-muted-foreground">
          {item.next_trigger && (
            <div>
              <span className="font-medium text-orange-200">다음 트리거:</span> {item.next_trigger}
            </div>
          )}
          {item.risk_flags?.length > 0 && (
            <div className="mt-2 flex flex-wrap gap-1">
              {item.risk_flags.slice(0, 3).map((flag, index) => (
                <Badge key={`${flag}-${index}`} variant="warning">
                  {flag}
                </Badge>
              ))}
            </div>
          )}
        </div>
      )}

      <div className="grid grid-cols-2 gap-2 text-xs text-muted-foreground">
        <span>신뢰도 {fmtPct(item.confidence)}</span>
        <span className="text-right">교과서 {fmtPct(item.textbook_similarity)}</span>
        <span>표본 신뢰도 {fmtPct(item.sample_reliability)}</span>
        <span className="text-right">edge {fmtPct(item.historical_edge_score)}</span>
        <span>손익비 {item.reward_risk_ratio.toFixed(2)}</span>
        <span className="text-right">거래대금 {fmtTurnoverBillion(item.avg_turnover_billion)}</span>
      </div>

      <div className="rounded-lg border border-border bg-background/60 p-2.5">
        <div className="flex items-center gap-1.5 text-[11px] font-medium text-muted-foreground">
          <Layers3 size={12} />
          멀티 타임프레임 컨텍스트
        </div>
        <p className="mt-1 text-xs text-muted-foreground">{item.confluence_summary}</p>
        <p className="mt-1 text-xs leading-relaxed text-foreground/90">{item.scenario_text}</p>
      </div>

      <div className="grid grid-cols-2 gap-2 text-xs text-muted-foreground">
        <span>{WYCKOFF_LABELS[item.wyckoff_phase] ?? item.wyckoff_phase}</span>
        <span className="text-right">{INTRADAY_SESSION_LABELS[item.intraday_session_phase] ?? item.intraday_session_phase}</span>
      </div>

      {item.wyckoff_note && <div className="rounded-lg border border-sky-500/20 bg-sky-500/5 p-2.5 text-xs text-sky-100">{item.wyckoff_note}</div>}
      {item.intraday_session_note && <div className="rounded-lg border border-violet-500/20 bg-violet-500/5 p-2.5 text-xs text-violet-100">{item.intraday_session_note}</div>}
      {item.live_intraday_candidate && item.live_intraday_reason && <div className="rounded-lg border border-emerald-500/20 bg-emerald-500/5 p-2.5 text-xs text-emerald-100">{item.live_intraday_reason}</div>}
      {isIntraday && !item.live_intraday_candidate && item.non_live_intraday_reason && <div className="rounded-lg border border-slate-500/20 bg-slate-500/5 p-2.5 text-xs text-slate-200">{item.non_live_intraday_reason}</div>}
      {(item.fetch_message || item.no_signal_flag) && (
        <div className="rounded-lg border border-border bg-background/60 p-2.5">
          <div className="flex items-center gap-1.5 text-[11px] font-medium text-muted-foreground">
            <AlertTriangle size={12} />
            데이터 메모
          </div>
          <p className="mt-1 text-xs text-muted-foreground">{item.fetch_message || item.source_note}</p>
        </div>
      )}
      {item.trend_warning && <div className="rounded-lg border border-amber-500/20 bg-amber-500/5 p-2.5 text-xs text-amber-200">{item.trend_warning}</div>}
      {intradayPreset && <p className="text-xs text-muted-foreground">프리셋: {presetLabel(intradayPreset)}</p>}
      <p className="line-clamp-2 text-xs leading-relaxed text-muted-foreground">{item.reason_summary}</p>
    </Card>
  )
}

function SummaryBlock({
  tone,
  title,
  score,
  children,
}: {
  tone: 'primary' | 'emerald' | 'sky' | 'violet' | 'amber' | 'cyan'
  title: string
  score?: number
  children: React.ReactNode
}) {
  const tones = {
    primary: 'border-primary/20 bg-primary/5 text-primary',
    emerald: 'border-emerald-400/20 bg-emerald-400/5 text-emerald-300',
    sky: 'border-sky-400/20 bg-sky-400/5 text-sky-200',
    violet: 'border-violet-400/20 bg-violet-400/5 text-violet-200',
    amber: 'border-amber-400/20 bg-amber-400/5 text-amber-200',
    cyan: 'border-cyan-400/20 bg-cyan-400/5 text-cyan-200',
  }[tone]

  return (
    <div className={`rounded-lg border p-2.5 text-xs leading-relaxed text-muted-foreground ${tones}`}>
      <div className="mb-1 flex items-center justify-between gap-2">
        <span className="font-medium">{title}</span>
        {typeof score === 'number' ? <span>{fmtPct(score, 0)}</span> : null}
      </div>
      {children}
    </div>
  )
}

function actionPlanVariant(plan: string): 'bullish' | 'warning' | 'muted' | 'neutral' {
  if (plan === 'ready_now') return 'bullish'
  if (plan === 'watch') return 'neutral'
  if (plan === 'recheck') return 'warning'
  return 'muted'
}

function scoreVariant(score: number): 'bullish' | 'warning' | 'muted' | 'neutral' {
  if (score >= 0.72) return 'bullish'
  if (score >= 0.56) return 'neutral'
  if (score >= 0.4) return 'warning'
  return 'muted'
}

function presetLabel(value: string): string {
  switch (value) {
    case 'all':
      return '전체'
    case 'ready-now':
      return '지금 볼 종목'
    case 'watch':
      return '지켜볼 후보'
    case 'recheck':
      return '재확인 필요'
    case 'cooling':
      return '관망 / 정리'
    default:
      return value
  }
}
