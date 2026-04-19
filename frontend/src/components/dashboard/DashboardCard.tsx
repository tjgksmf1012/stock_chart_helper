import type { MouseEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { AlertTriangle, Layers3, Star } from 'lucide-react'

import type { DashboardItem } from '@/types/api'
import { Badge } from '@/components/ui/Badge'
import { Card } from '@/components/ui/Card'
import { ProbBar } from '@/components/ui/ProbBar'
import { cn, fmtPct, fmtTurnoverBillion, INTRADAY_SESSION_LABELS, PATTERN_NAMES, STATE_COLORS, STATE_LABELS, WYCKOFF_LABELS } from '@/lib/utils'
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

  const presetNote = isIntraday ? presetActionNote(item, intradayPreset) : ''

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
          <div className="flex items-center gap-1.5">
            <span className="font-mono text-xs text-muted-foreground">#{item.rank}</span>
            <span className="truncate text-sm font-semibold">{item.symbol.name}</span>
            <span className="font-mono text-xs text-muted-foreground">{item.symbol.code}</span>
          </div>

          <div className="mt-1 flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
            <span>{item.symbol.market}</span>
            <span>·</span>
            <span>{item.timeframe_label}</span>
            <Badge variant={actionPlanVariant(item.action_plan)}>{item.action_plan_label}</Badge>
            <Badge variant={readinessVariant(item.trade_readiness_score ?? 0)}>
              준비도 {fmtPct(item.trade_readiness_score ?? 0, 0)}
            </Badge>
            <Badge
              variant={
                (item.entry_window_score ?? 0) >= 0.7
                  ? 'bullish'
                  : (item.entry_window_score ?? 0) >= 0.5
                    ? 'neutral'
                    : 'muted'
              }
            >
              진입 {fmtPct(item.entry_window_score ?? 0, 0)}
            </Badge>
            <Badge variant={(item.active_setup_score ?? 0) >= 0.56 ? 'neutral' : 'muted'}>
              활성 {fmtPct(item.active_setup_score ?? 0, 0)}
            </Badge>
            <Badge variant={item.data_quality >= 0.8 ? 'bullish' : item.data_quality >= 0.6 ? 'muted' : 'warning'}>
              품질 {fmtPct(item.data_quality, 0)}
            </Badge>
            <Badge variant={item.confluence_score >= 0.7 ? 'bullish' : item.confluence_score >= 0.5 ? 'muted' : 'warning'}>
              합의 {fmtPct(item.confluence_score, 0)}
            </Badge>
            <Badge variant={item.formation_quality >= 0.7 ? 'bullish' : item.formation_quality >= 0.5 ? 'muted' : 'warning'}>
              형성 {fmtPct(item.formation_quality, 0)}
            </Badge>
            <Badge
              variant={item.sample_reliability >= 0.65 ? 'bullish' : item.sample_reliability >= 0.45 ? 'muted' : 'warning'}
            >
              표본 {fmtPct(item.sample_reliability, 0)}
            </Badge>
            <Badge
              variant={item.historical_edge_score >= 0.65 ? 'bullish' : item.historical_edge_score >= 0.45 ? 'muted' : 'warning'}
            >
              edge {fmtPct(item.historical_edge_score, 0)}
            </Badge>
            <Badge
              variant={item.reward_risk_ratio >= 1.8 ? 'bullish' : item.reward_risk_ratio >= 1.2 ? 'muted' : 'warning'}
            >
              손익비 {item.reward_risk_ratio.toFixed(1)}
            </Badge>
            <Badge
              variant={
                item.wyckoff_phase === 'accumulation' || item.wyckoff_phase === 'markup'
                  ? 'bullish'
                  : item.wyckoff_phase === 'distribution' || item.wyckoff_phase === 'markdown'
                    ? 'warning'
                    : 'muted'
              }
            >
              {WYCKOFF_LABELS[item.wyckoff_phase] ?? item.wyckoff_phase}
            </Badge>
            <Badge
              variant={
                item.intraday_session_score >= 0.72 ? 'bullish' : item.intraday_session_score <= 0.44 ? 'warning' : 'muted'
              }
            >
              {INTRADAY_SESSION_LABELS[item.intraday_session_phase] ?? item.intraday_session_phase}
            </Badge>
            {item.live_intraday_candidate && (
              <Badge variant="bullish">live {fmtPct(item.live_intraday_priority_score, 0)}</Badge>
            )}
            {isIntraday && !item.live_intraday_candidate && (
              <Badge variant={modeVariant(item.intraday_collection_mode)}>
                {intradayModeLabel(item.intraday_collection_mode)}
              </Badge>
            )}
          </div>

          {item.pattern_type ? (
            <div className="mt-2 flex flex-wrap items-center gap-1.5">
              <span className="text-xs text-muted-foreground">{PATTERN_NAMES[item.pattern_type] ?? item.pattern_type}</span>
              {item.state && (
                <span className={cn('rounded px-1 py-0.5 text-xs', STATE_COLORS[item.state])}>{STATE_LABELS[item.state]}</span>
              )}
              <Badge variant="muted">{setupStageLabel(item.setup_stage)}</Badge>
            </div>
          ) : (
            <div className="mt-2 text-xs text-muted-foreground">뚜렷한 패턴 없음</div>
          )}
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
            title={watched ? '관심 종목 제거' : '관심 종목 추가'}
          >
            <Star size={14} className={watched ? 'fill-yellow-400' : ''} />
          </button>
        </div>
      </div>

      <ProbBar p_up={item.p_up} p_down={item.p_down} />

      {item.action_plan_summary && (
        <div className="rounded-lg border border-primary/20 bg-primary/5 p-2.5 text-xs leading-relaxed text-muted-foreground">
          <div className="mb-1 flex items-center justify-between gap-2">
            <span className="font-medium text-primary">실전 행동</span>
            <span>{fmtPct(item.action_priority_score ?? 0, 0)}</span>
          </div>
          {item.action_plan_summary}
        </div>
      )}

      {item.trade_readiness_summary && (
        <div className="rounded-lg border border-emerald-400/20 bg-emerald-400/5 p-2.5 text-xs leading-relaxed text-muted-foreground">
          <div className="mb-1 flex items-center justify-between gap-2">
            <span className="font-medium text-emerald-300">거래 준비도 · {item.trade_readiness_label}</span>
            <span>{fmtPct(item.trade_readiness_score ?? 0, 0)}</span>
          </div>
          {item.trade_readiness_summary}
        </div>
      )}

      {item.entry_window_summary && (
        <div className="rounded-lg border border-sky-400/20 bg-sky-400/5 p-2.5 text-xs leading-relaxed text-muted-foreground">
          <div className="mb-1 flex items-center justify-between gap-2">
            <span className="font-medium text-sky-200">진입 구간 · {item.entry_window_label}</span>
            <span>{fmtPct(item.entry_window_score ?? 0, 0)}</span>
          </div>
          {item.entry_window_summary}
        </div>
      )}

      {item.active_setup_summary && (
        <div className="rounded-lg border border-cyan-400/20 bg-cyan-400/5 p-2.5 text-xs leading-relaxed text-muted-foreground">
          <div className="mb-1 flex items-center justify-between gap-2">
            <span className="font-medium text-cyan-200">{item.active_setup_label}</span>
            <span>
              활성 {item.active_pattern_count ?? 0} / 종료 {item.completed_pattern_count ?? 0}
            </span>
          </div>
          {item.active_setup_summary}
        </div>
      )}

      {(item.next_trigger || item.risk_flags?.length > 0) && (
        <div className="rounded-lg border border-orange-400/15 bg-orange-400/5 p-2.5 text-xs leading-relaxed text-muted-foreground">
          {item.next_trigger && (
            <div>
              <span className="font-medium text-orange-200">다음 트리거:</span> {item.next_trigger}
            </div>
          )}
          {item.risk_flags?.length > 0 && (
            <div className="mt-1 flex flex-wrap gap-1">
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
        <span className="text-right">신선도 {fmtPct(item.recency_score)}</span>
        <span>레그 균형 {fmtPct(item.leg_balance_fit)}</span>
        <span className="text-right">반전 에너지 {fmtPct(item.reversal_energy_fit)}</span>
        <span>돌파 품질 {fmtPct(item.breakout_quality_fit)}</span>
        <span className="text-right">Retest 품질 {fmtPct(item.retest_quality_fit)}</span>
        <span>평균 MFE {fmtPct(item.avg_mfe_pct)}</span>
        <span className="text-right">평균 MAE {fmtPct(item.avg_mae_pct)}</span>
        <span>거래대금 {fmtTurnoverBillion(item.avg_turnover_billion)}</span>
        <span className="text-right">표본 {item.sample_size}건</span>
        <span>목표 여지 {fmtPct(item.target_distance_pct)}</span>
        <span className="text-right">손절 거리 {fmtPct(item.stop_distance_pct)}</span>
      </div>

      <div className="rounded-lg border border-border bg-background/60 p-2.5">
        <div className="flex items-center gap-1.5 text-[11px] font-medium text-muted-foreground">
          <Layers3 size={12} />
          멀티 타임프레임 정렬
        </div>
        <p className="mt-1 text-xs text-muted-foreground">{item.confluence_summary}</p>
        <p className="mt-1 text-xs leading-relaxed text-foreground/90">{item.scenario_text}</p>
      </div>

      {item.wyckoff_note && (
        <div className="rounded-lg border border-sky-500/20 bg-sky-500/5 p-2.5 text-xs text-sky-100">
          {item.wyckoff_note}
        </div>
      )}

      {item.intraday_session_note && (
        <div className="rounded-lg border border-violet-500/20 bg-violet-500/5 p-2.5 text-xs text-violet-100">
          {item.intraday_session_note}
        </div>
      )}

      {item.live_intraday_candidate && item.live_intraday_reason && (
        <div className="rounded-lg border border-emerald-500/20 bg-emerald-500/5 p-2.5 text-xs text-emerald-100">
          {item.live_intraday_reason}
        </div>
      )}

      {isIntraday && !item.live_intraday_candidate && item.non_live_intraday_reason && (
        <div className="rounded-lg border border-slate-500/20 bg-slate-500/5 p-2.5 text-xs text-slate-200">
          {item.non_live_intraday_reason}
        </div>
      )}

      {(item.fetch_message || item.no_signal_flag) && (
        <div className="rounded-lg border border-border bg-background/60 p-2.5">
          <div className="flex items-center gap-1.5 text-[11px] font-medium text-muted-foreground">
            <AlertTriangle size={12} />
            데이터 메모
          </div>
          <p className="mt-1 text-xs text-muted-foreground">{item.fetch_message || item.source_note}</p>
        </div>
      )}

      {item.trend_warning && (
        <div className="rounded-lg border border-amber-500/20 bg-amber-500/5 p-2.5 text-xs text-amber-200">
          {item.trend_warning}
        </div>
      )}

      {presetNote && (
        <div className="rounded-lg border border-cyan-500/20 bg-cyan-500/5 p-2.5 text-xs text-cyan-100">
          {presetNote}
        </div>
      )}

      <p className="line-clamp-2 text-xs leading-relaxed text-muted-foreground">{item.reason_summary}</p>

      {item.no_signal_flag && <Badge variant="warning">No Signal</Badge>}
    </Card>
  )
}

function setupStageLabel(stage: string): string {
  switch (stage) {
    case 'confirmed':
      return '완료 신호'
    case 'trigger_ready':
      return '트리거 직전'
    case 'breakout_watch':
      return '돌파 감시'
    case 'late_base':
      return '후반 베이스'
    case 'early_trigger_watch':
      return '초기 트리거'
    case 'base_building':
      return '베이스 형성'
    default:
      return '중립'
  }
}

function intradayModeLabel(mode: string): string {
  switch (mode) {
    case 'stored':
      return 'stored'
    case 'public':
      return 'public'
    case 'mixed':
      return 'mixed'
    case 'cooldown':
      return 'cooldown'
    case 'live':
      return 'live'
    default:
      return 'budget'
  }
}

function modeVariant(mode: string): 'bullish' | 'warning' | 'muted' {
  switch (mode) {
    case 'live':
      return 'bullish'
    case 'cooldown':
      return 'warning'
    default:
      return 'muted'
  }
}

function actionPlanVariant(plan: string): 'bullish' | 'warning' | 'muted' | 'neutral' {
  if (plan === 'ready_now') return 'bullish'
  if (plan === 'watch') return 'neutral'
  if (plan === 'recheck') return 'warning'
  return 'muted'
}

function readinessVariant(score: number): 'bullish' | 'warning' | 'muted' | 'neutral' {
  if (score >= 0.72) return 'bullish'
  if (score >= 0.58) return 'neutral'
  if (score >= 0.44) return 'warning'
  return 'muted'
}

function presetActionNote(item: DashboardItem, preset?: string): string {
  switch (preset) {
    case 'ready-now':
      return item.live_intraday_candidate
        ? '지금은 live 분봉으로 확인 중인 즉시 대응 후보입니다. 무효화 기준과 돌파 지속 여부를 먼저 보세요.'
        : '즉시 대응 프리셋에 들어왔지만 live 추적까지는 아닙니다. 진입 전 한 번 더 확인하는 편이 좋습니다.'
    case 'watch':
      return '아직 완성 신호보다 형성 과정에 가깝습니다. 돌파 확인이나 상위 타임프레임 정렬이 붙는지 지켜보세요.'
    case 'recheck':
      return '저장 분봉이나 공개 소스 중심 후보입니다. 장중 변동이 크면 한 번 더 새로고침해서 상태를 확인하는 편이 좋습니다.'
    case 'cooling':
      return item.no_signal_flag
        ? '지금은 관망 쪽에 더 가깝습니다. 품질 회복이나 새 트리거가 생길 때까지 기다리는 편이 낫습니다.'
        : '냉각 구간 후보입니다. KIS 쿨다운 해제나 세팅 회복 뒤 다시 보는 흐름이 좋습니다.'
    default:
      return ''
  }
}
