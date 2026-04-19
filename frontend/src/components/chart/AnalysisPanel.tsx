import { Activity, AlertCircle, Database, Layers3, ShieldAlert, Target, TrendingDown, TrendingUp } from 'lucide-react'

import type { AnalysisResult, PatternInfo } from '@/types/api'
import { Badge } from '@/components/ui/Badge'
import { Card, CardHeader, CardTitle } from '@/components/ui/Card'
import { ProbBar } from '@/components/ui/ProbBar'
import { StatRow } from '@/components/ui/StatRow'
import {
  CANDLE_CONFIRMATION_LABELS,
  cn,
  fmtDateTime,
  fmtPct,
  fmtPrice,
  fmtTurnoverBillion,
  getPatternBias,
  INTRADAY_SESSION_LABELS,
  PATTERN_NAMES,
  PATTERN_VARIANT_NAMES,
  STATE_COLORS,
  STATE_LABELS,
  WYCKOFF_LABELS,
} from '@/lib/utils'

interface AnalysisPanelProps {
  analysis: AnalysisResult
}

export function AnalysisPanel({ analysis }: AnalysisPanelProps) {
  const bestPattern = analysis.patterns[0]

  return (
    <div className="space-y-3">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            {analysis.p_up >= 0.55 ? (
              <TrendingUp size={14} className="text-green-400" />
            ) : analysis.p_down >= 0.55 ? (
              <TrendingDown size={14} className="text-red-400" />
            ) : (
              <Activity size={14} className="text-primary" />
            )}
            확률 분석
            <Badge variant="muted" className="ml-auto">
              {analysis.timeframe_label}
            </Badge>
          </CardTitle>
        </CardHeader>
        {analysis.no_signal_flag ? (
          <div className="space-y-2 text-xs text-muted-foreground">
            <div className="flex items-center gap-2 text-yellow-300">
              <AlertCircle size={14} />
              <span className="font-medium">No Signal</span>
            </div>
            <p>{analysis.no_signal_reason}</p>
            <p>{analysis.reason_summary}</p>
          </div>
        ) : (
          <div className="space-y-3">
            <ProbBar p_up={analysis.p_up} p_down={analysis.p_down} size="md" />
            <p className="text-xs leading-relaxed text-muted-foreground">{analysis.reason_summary}</p>
          </div>
        )}
      </Card>

      <ActionPlanCard analysis={analysis} />
      <TradeReadinessCard analysis={analysis} />
      <EntryWindowCard analysis={analysis} />
      <FreshnessCard analysis={analysis} />
      <ReentryCard analysis={analysis} />
      <ActiveSetupCard analysis={analysis} />
      <DecisionSupportCard analysis={analysis} />

      {bestPattern && <BestPatternCard pattern={bestPattern} analysis={analysis} />}

      <Card>
        <CardHeader>
          <CardTitle>예상 시나리오</CardTitle>
        </CardHeader>
        <div className="space-y-2 text-xs text-muted-foreground">
          <div className="font-medium text-foreground">{analysis.projection_label || '중립 시나리오'}</div>
          <p>{analysis.projection_summary}</p>
        </div>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>점수 상세</CardTitle>
        </CardHeader>
        <div className="space-y-2">
          <StatRow label="교과서 유사도" value={fmtPct(analysis.textbook_similarity)} />
          <StatRow label="패턴 확인 점수" value={fmtPct(analysis.pattern_confirmation_score)} />
          <StatRow label="신뢰도" value={fmtPct(analysis.confidence)} />
          <StatRow label="진입 적합도" value={fmtPct(analysis.entry_score)} />
          <StatRow label="거래 준비도" value={fmtPct(analysis.trade_readiness_score ?? 0)} />
          <StatRow label="진입 구간" value={fmtPct(analysis.entry_window_score ?? 0)} />
          <StatRow label="패턴 신선도" value={fmtPct(analysis.freshness_score ?? 0)} />
          <StatRow label="재진입 구조" value={fmtPct(analysis.reentry_score ?? 0)} />
          <StatRow label="활성 셋업" value={fmtPct(analysis.active_setup_score ?? 0)} />
          <StatRow label="손익비" value={analysis.reward_risk_ratio.toFixed(2)} />
          <StatRow label="백테스트 edge" value={fmtPct(analysis.historical_edge_score)} />
          <StatRow label="표본 신뢰도" value={fmtPct(analysis.sample_reliability)} />
          <StatRow label="유사 패턴 표본" value={`${analysis.sample_size.toLocaleString('ko-KR')}건`} />
          <StatRow label="평균 MFE" value={fmtPct(analysis.avg_mfe_pct)} />
          <StatRow label="평균 MAE" value={fmtPct(analysis.avg_mae_pct)} />
        </div>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Database size={14} className="text-primary" />
            데이터 메모
          </CardTitle>
        </CardHeader>
        <div className="space-y-2">
          <StatRow label="데이터 출처" value={analysis.data_source} />
          <StatRow label="데이터 상태" value={analysis.fetch_status_label} />
          <StatRow label="데이터 품질" value={fmtPct(analysis.data_quality)} />
          <StatRow label="평균 거래대금" value={fmtTurnoverBillion(analysis.avg_turnover_billion)} />
          <StatRow label="유동성 점수" value={fmtPct(analysis.liquidity_score)} />
          <StatRow label="통계 기준" value={analysis.stats_timeframe} />
          <StatRow label="사용 바 수" value={`${analysis.available_bars.toLocaleString('ko-KR')}개`} />
          <StatRow label="와이코프" value={WYCKOFF_LABELS[analysis.wyckoff_phase] ?? analysis.wyckoff_phase} />
          <StatRow label="장중 세션" value={INTRADAY_SESSION_LABELS[analysis.intraday_session_phase] ?? analysis.intraday_session_phase} />
          <p className="pt-1 text-xs leading-relaxed text-muted-foreground">{analysis.source_note}</p>
          {analysis.fetch_message && <p className="text-xs text-muted-foreground">{analysis.fetch_message}</p>}
          {analysis.wyckoff_note && <p className="text-xs text-sky-200">{analysis.wyckoff_note}</p>}
          {analysis.intraday_session_note && <p className="text-xs text-violet-200">{analysis.intraday_session_note}</p>}
          {analysis.trend_warning && <p className="text-xs text-amber-300">{analysis.trend_warning}</p>}
        </div>
      </Card>

      {analysis.patterns.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>감지된 패턴</CardTitle>
          </CardHeader>
          <div className="space-y-3">
            {analysis.patterns.map((pattern, index) => (
              <PatternCard key={`${pattern.pattern_type}-${index}`} pattern={pattern} />
            ))}
          </div>
        </Card>
      )}

      <Card className="space-y-2">
        <div className="flex items-center gap-2 text-sm font-semibold">
          <ShieldAlert size={15} className="text-orange-400" />
          해석 주의
        </div>
        <p className="text-xs leading-relaxed text-muted-foreground">
          이 화면은 패턴 기반 보조 분석 도구입니다. 이미 목표가에 도달했거나 무효화된 패턴은 신선도와 거래 준비도에서 강하게 감점되며,
          실전 매수·매도 판단 전에는 추세, 거래대금, 리스크 기준을 함께 확인하는 것이 좋습니다.
        </p>
      </Card>
    </div>
  )
}

function BestPatternCard({ pattern, analysis }: { pattern: PatternInfo; analysis: AnalysisResult }) {
  return (
    <Card className="space-y-3">
      <div className="flex items-center gap-2 text-sm font-semibold">
        <Target size={15} className="text-primary" />
        전략 힌트
      </div>
      <div className="rounded-lg border border-border bg-background/60 p-3">
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant={badgeVariant(pattern)}>{PATTERN_NAMES[pattern.pattern_type] ?? pattern.pattern_type}</Badge>
          {pattern.variant && <Badge variant="muted">{PATTERN_VARIANT_NAMES[pattern.variant] ?? pattern.variant}</Badge>}
          <span className={cn('rounded px-1.5 py-0.5 text-xs', STATE_COLORS[pattern.state])}>{STATE_LABELS[pattern.state]}</span>
          <Badge variant={scoreVariant(pattern.lifecycle_score)}>{pattern.lifecycle_label}</Badge>
        </div>
        <p className="mt-2 text-xs leading-relaxed text-muted-foreground">{analysis.action_plan_summary}</p>
        {pattern.lifecycle_note && <p className="mt-2 text-xs text-violet-200">{pattern.lifecycle_note}</p>}
        {pattern.candlestick_note && <p className="mt-2 text-xs text-sky-200">{pattern.candlestick_note}</p>}
      </div>
      <div className="space-y-2">
        {pattern.neckline !== null && <StatRow label="목선" value={fmtPrice(pattern.neckline)} />}
        {pattern.target_level !== null && <StatRow label="목표가" value={<span className="text-green-400">{fmtPrice(pattern.target_level)}</span>} />}
        {pattern.invalidation_level !== null && <StatRow label="무효화 기준" value={<span className="text-red-400">{fmtPrice(pattern.invalidation_level)}</span>} />}
        {pattern.target_hit_at && <StatRow label="목표가 도달" value={fmtDateTime(pattern.target_hit_at)} />}
        {pattern.invalidated_at && <StatRow label="무효화 시점" value={fmtDateTime(pattern.invalidated_at)} />}
      </div>
    </Card>
  )
}

function PatternCard({ pattern }: { pattern: PatternInfo }) {
  return (
    <div className="space-y-2 rounded-lg border border-border bg-background/50 p-3">
      <div className="flex flex-wrap items-center gap-2">
        <Badge variant={badgeVariant(pattern)}>{PATTERN_NAMES[pattern.pattern_type] ?? pattern.pattern_type}</Badge>
        <Badge variant="muted">등급 {pattern.grade}</Badge>
        <span className={cn('rounded px-1.5 py-0.5 text-xs', STATE_COLORS[pattern.state])}>{STATE_LABELS[pattern.state]}</span>
        <Badge variant={scoreVariant(pattern.lifecycle_score)}>{pattern.lifecycle_label}</Badge>
      </div>
      <div className="grid grid-cols-2 gap-2 text-xs text-muted-foreground">
        <span>교과서 유사도 {fmtPct(pattern.textbook_similarity)}</span>
        <span className="text-right">변형 적합도 {fmtPct(pattern.variant_fit)}</span>
        <span>다리 균형 {fmtPct(pattern.leg_balance_fit)}</span>
        <span className="text-right">반전 에너지 {fmtPct(pattern.reversal_energy_fit)}</span>
        <span>돌파 품질 {fmtPct(pattern.breakout_quality_fit)}</span>
        <span className="text-right">리테스트 {fmtPct(pattern.retest_quality_fit)}</span>
      </div>
      <div className="text-xs text-muted-foreground">
        {CANDLE_CONFIRMATION_LABELS[pattern.candlestick_label ?? 'neutral'] ?? pattern.candlestick_label ?? '중립 캔들'}
      </div>
      {pattern.lifecycle_note && <p className="text-xs leading-relaxed text-muted-foreground">{pattern.lifecycle_note}</p>}
    </div>
  )
}

function ActionPlanCard({ analysis }: { analysis: AnalysisResult }) {
  return (
    <Card className="space-y-3 border-primary/20 bg-primary/5">
      <div className="flex items-center gap-2 text-sm font-semibold">
        <Activity size={15} className="text-primary" />
        실전 행동 가이드
        <Badge variant={actionPlanVariant(analysis.action_plan)} className="ml-auto">
          {analysis.action_plan_label}
        </Badge>
      </div>
      <p className="text-xs leading-relaxed text-muted-foreground">{analysis.action_plan_summary}</p>
      <StatRow label="행동 우선순위" value={fmtPct(analysis.action_priority_score)} />
    </Card>
  )
}

function TradeReadinessCard({ analysis }: { analysis: AnalysisResult }) {
  const score = analysis.trade_readiness_score ?? 0
  return (
    <Card className="space-y-3 border-emerald-400/20 bg-emerald-400/5">
      <div className="flex items-center gap-2 text-sm font-semibold">
        <Target size={15} className="text-emerald-300" />
        거래 준비도
        <Badge variant={scoreVariant(score)} className="ml-auto">
          {analysis.trade_readiness_label}
        </Badge>
      </div>
      <ProgressBar score={score} color="bg-emerald-400" />
      <p className="text-xs leading-relaxed text-muted-foreground">{analysis.trade_readiness_summary}</p>
      {analysis.score_factors?.length > 0 && (
        <div className="grid grid-cols-1 gap-2">
          {analysis.score_factors.map(factor => (
            <div key={factor.label} className="rounded-lg border border-border bg-background/60 p-2.5">
              <div className="mb-1 flex items-center justify-between gap-2 text-xs">
                <span className="font-medium text-foreground">{factor.label}</span>
                <span className="font-mono text-muted-foreground">{fmtPct(factor.score, 0)} / {Math.round(factor.weight * 100)}%</span>
              </div>
              <div className="h-1.5 overflow-hidden rounded-full bg-card">
                <div className="h-full rounded-full bg-primary/80" style={{ width: `${Math.round(factor.score * 100)}%` }} />
              </div>
              {factor.note && <p className="mt-1.5 text-[11px] leading-relaxed text-muted-foreground">{factor.note}</p>}
            </div>
          ))}
        </div>
      )}
    </Card>
  )
}

function EntryWindowCard({ analysis }: { analysis: AnalysisResult }) {
  const score = analysis.entry_window_score ?? 0
  return (
    <Card className="space-y-3 border-sky-400/20 bg-sky-400/5">
      <div className="flex items-center gap-2 text-sm font-semibold">
        <Target size={15} className="text-sky-300" />
        진입 구간
        <Badge variant={scoreVariant(score)} className="ml-auto">
          {analysis.entry_window_label}
        </Badge>
      </div>
      <ProgressBar score={score} color="bg-sky-300" />
      <p className="text-xs leading-relaxed text-muted-foreground">{analysis.entry_window_summary}</p>
    </Card>
  )
}

function FreshnessCard({ analysis }: { analysis: AnalysisResult }) {
  const score = analysis.freshness_score ?? 0
  return (
    <Card className="space-y-3 border-violet-400/20 bg-violet-400/5">
      <div className="flex items-center gap-2 text-sm font-semibold">
        <Layers3 size={15} className="text-violet-300" />
        패턴 신선도
        <Badge variant={scoreVariant(score)} className="ml-auto">
          {analysis.freshness_label}
        </Badge>
      </div>
      <ProgressBar score={score} color="bg-violet-300" />
      <p className="text-xs leading-relaxed text-muted-foreground">{analysis.freshness_summary}</p>
    </Card>
  )
}

function ReentryCard({ analysis }: { analysis: AnalysisResult }) {
  const score = analysis.reentry_score ?? 0
  return (
    <Card className="space-y-3 border-amber-400/20 bg-amber-400/5">
      <div className="flex items-center gap-2 text-sm font-semibold">
        <Target size={15} className="text-amber-300" />
        재진입 구조
        <Badge variant={scoreVariant(score)} className="ml-auto">
          {analysis.reentry_label}
        </Badge>
        </div>
        <ProgressBar score={score} color="bg-amber-300" />
        <p className="text-xs leading-relaxed text-muted-foreground">{analysis.reentry_summary}</p>
        {(analysis.reentry_case !== 'none' || analysis.reentry_profile_key !== 'none') && (
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
            {analysis.reentry_case_label && analysis.reentry_case !== 'none' && (
              <div className="rounded-lg border border-amber-400/15 bg-background/60 p-2 text-xs text-amber-100">
                <span className="font-medium">유형:</span> {analysis.reentry_case_label}
              </div>
            )}
            {analysis.reentry_profile_label && analysis.reentry_profile_key !== 'none' && (
              <div className="rounded-lg border border-amber-400/15 bg-background/60 p-2 text-xs text-amber-100">
                <span className="font-medium">해석 기준:</span> {analysis.reentry_profile_label}
              </div>
            )}
          </div>
        )}
        {analysis.reentry_profile_summary && analysis.reentry_profile_key !== 'none' && (
          <div className="rounded-lg border border-amber-400/15 bg-amber-400/5 p-2 text-xs leading-relaxed text-amber-100/90">
            <span className="font-medium text-amber-200">가중치 메모:</span> {analysis.reentry_profile_summary}
          </div>
        )}
        {analysis.reentry_trigger && (
          <div className="rounded-lg border border-border bg-background/60 p-2 text-xs text-muted-foreground">
            <span className="font-medium text-amber-200">확인 포인트:</span> {analysis.reentry_trigger}
          </div>
        )}
      {analysis.reentry_factors?.length > 0 && (
        <div className="grid grid-cols-1 gap-2">
          {analysis.reentry_factors.map(factor => (
            <div key={factor.label} className="rounded-lg border border-border bg-background/60 p-2.5">
              <div className="mb-1 flex items-center justify-between gap-2 text-xs">
                <span className="font-medium text-foreground">{factor.label}</span>
                <span className="font-mono text-muted-foreground">{fmtPct(factor.score, 0)} / {Math.round(factor.weight * 100)}%</span>
              </div>
              <div className="h-1.5 overflow-hidden rounded-full bg-card">
                <div className="h-full rounded-full bg-amber-300" style={{ width: `${Math.round(factor.score * 100)}%` }} />
              </div>
              {factor.note && <p className="mt-1.5 text-[11px] leading-relaxed text-muted-foreground">{factor.note}</p>}
            </div>
          ))}
        </div>
      )}
    </Card>
  )
}

function ActiveSetupCard({ analysis }: { analysis: AnalysisResult }) {
  const score = analysis.active_setup_score ?? 0
  return (
    <Card className="space-y-3 border-cyan-400/20 bg-cyan-400/5">
      <div className="flex items-center gap-2 text-sm font-semibold">
        <Activity size={15} className="text-cyan-300" />
        활성 셋업
        <Badge variant={scoreVariant(score)} className="ml-auto">
          {analysis.active_setup_label}
        </Badge>
      </div>
      <ProgressBar score={score} color="bg-cyan-300" />
      <p className="text-xs leading-relaxed text-muted-foreground">{analysis.active_setup_summary}</p>
      <div className="grid grid-cols-2 gap-2 text-xs text-muted-foreground">
        <span>활성 패턴 {analysis.active_pattern_count}개</span>
        <span className="text-right">종료/무효 {analysis.completed_pattern_count}개</span>
      </div>
    </Card>
  )
}

function DecisionSupportCard({ analysis }: { analysis: AnalysisResult }) {
  const flags = analysis.risk_flags ?? []
  const checklist = analysis.confirmation_checklist ?? []
  if (!flags.length && !checklist.length && !analysis.next_trigger) return null

  return (
    <Card className="space-y-3">
      <div className="flex items-center gap-2 text-sm font-semibold">
        <ShieldAlert size={15} className="text-orange-400" />
        실전 체크
      </div>
      {analysis.next_trigger && (
        <div className="rounded-lg border border-primary/20 bg-primary/5 p-2.5 text-xs leading-relaxed text-muted-foreground">
          <span className="font-medium text-primary">다음 트리거:</span> {analysis.next_trigger}
        </div>
      )}
      {flags.length > 0 && (
        <div className="space-y-1.5">
          {flags.map((flag, index) => (
            <div key={`${flag}-${index}`} className="rounded-md border border-orange-400/15 bg-orange-400/5 px-2.5 py-1.5 text-xs text-orange-100">
              {flag}
            </div>
          ))}
        </div>
      )}
      {checklist.length > 0 && (
        <ol className="space-y-1.5 text-xs text-muted-foreground">
          {checklist.map((item, index) => (
            <li key={`${item}-${index}`} className="rounded-md border border-border bg-background/60 px-2.5 py-1.5">
              {index + 1}. {item}
            </li>
          ))}
        </ol>
      )}
    </Card>
  )
}

function ProgressBar({ score, color }: { score: number; color: string }) {
  return (
    <div>
      <div className="mb-1 flex items-center justify-between text-xs text-muted-foreground">
        <span>점수</span>
        <span className="font-mono">{fmtPct(score, 0)}</span>
      </div>
      <div className="h-2 overflow-hidden rounded-full bg-background">
        <div className={cn('h-full rounded-full transition-all', color)} style={{ width: `${Math.round(score * 100)}%` }} />
      </div>
    </div>
  )
}

function badgeVariant(pattern: PatternInfo): 'bullish' | 'bearish' | 'neutral' {
  return getPatternBias(pattern.pattern_type)
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
