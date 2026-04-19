import { Activity, AlertCircle, Database, ShieldAlert, Target, TrendingDown, TrendingUp } from 'lucide-react'

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
  INTRADAY_SESSION_LABELS,
  getPatternBias,
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

  if (analysis.no_signal_flag) {
    return (
      <Card className="space-y-3">
        <div className="flex items-center gap-2 text-yellow-400">
          <AlertCircle size={16} />
          <span className="text-sm font-semibold">No Signal</span>
          <Badge variant="muted" className="ml-auto">
            {analysis.timeframe_label}
          </Badge>
        </div>
        <p className="text-xs text-muted-foreground">{analysis.no_signal_reason}</p>
        <p className="text-xs text-muted-foreground">{analysis.reason_summary}</p>
        <ActionPlanCard analysis={analysis} />
        <div className="rounded-lg border border-border bg-background/60 p-3 text-xs text-muted-foreground">
          <div>데이터 품질 {fmtPct(analysis.data_quality, 0)}</div>
          <div className="mt-1">데이터 상태 {analysis.fetch_status_label}</div>
          <div className="mt-1">{analysis.source_note}</div>
          {analysis.fetch_message && <div className="mt-1">{analysis.fetch_message}</div>}
        </div>
      </Card>
    )
  }

  return (
    <div className="space-y-3">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            {analysis.p_up >= 0.55 ? (
              <TrendingUp size={14} className="text-green-400" />
            ) : analysis.p_down >= 0.55 ? (
              <TrendingDown size={14} className="text-red-400" />
            ) : null}
            확률 분석
            {analysis.is_provisional && (
              <Badge variant="warning" className="ml-auto">
                잠정
              </Badge>
            )}
          </CardTitle>
        </CardHeader>
        <div className="space-y-3">
          <ProbBar p_up={analysis.p_up} p_down={analysis.p_down} size="md" />
          <p className="text-xs leading-relaxed text-muted-foreground">{analysis.reason_summary}</p>
        </div>
      </Card>

      <ActionPlanCard analysis={analysis} />

      {bestPattern && (
        <Card className="space-y-3">
          <div className="flex items-center gap-2 text-sm font-semibold">
            <Target size={15} className="text-primary" />
            전략 힌트
          </div>
          <div className="rounded-lg border border-border bg-background/60 p-3">
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant={badgeVariant(bestPattern)}>
                {PATTERN_NAMES[bestPattern.pattern_type] ?? bestPattern.pattern_type}
              </Badge>
              {bestPattern.variant && (
                <Badge variant="muted">
                  {PATTERN_VARIANT_NAMES[bestPattern.variant] ?? bestPattern.variant}
                </Badge>
              )}
              <span className={cn('rounded px-1.5 py-0.5 text-xs', STATE_COLORS[bestPattern.state])}>
                {STATE_LABELS[bestPattern.state]}
              </span>
              <Badge variant="muted">
                {CANDLE_CONFIRMATION_LABELS[bestPattern.candlestick_label ?? 'neutral'] ??
                  bestPattern.candlestick_label ??
                  '중립 캔들'}
              </Badge>
            </div>
            <p className="mt-2 text-xs leading-relaxed text-muted-foreground">
              {patternActionText(bestPattern, analysis)}
            </p>
            {bestPattern.candlestick_note && (
              <p className="mt-2 text-xs leading-relaxed text-sky-200">{bestPattern.candlestick_note}</p>
            )}
          </div>
          <div className="space-y-2">
            {bestPattern.target_level && (
              <StatRow label="우선 목표가" value={<span className="text-green-400">{fmtPrice(bestPattern.target_level)}</span>} />
            )}
            {bestPattern.invalidation_level && (
              <StatRow label="리스크 기준" value={<span className="text-red-400">{fmtPrice(bestPattern.invalidation_level)}</span>} />
            )}
            {bestPattern.target_hit_at && <StatRow label="목표가 첫 도달" value={fmtDateTime(bestPattern.target_hit_at)} />}
            {bestPattern.invalidated_at && <StatRow label="무효화 시점" value={fmtDateTime(bestPattern.invalidated_at)} />}
          </div>
        </Card>
      )}

      <Card>
        <CardHeader>
          <CardTitle>예상 시나리오</CardTitle>
        </CardHeader>
        <div className="rounded-lg border border-border bg-background/60 p-3">
          <div className="text-sm font-semibold">{analysis.projection_label}</div>
          <p className="mt-2 text-xs leading-relaxed text-muted-foreground">{analysis.projection_summary}</p>
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
          <StatRow label="기대 손익비" value={analysis.reward_risk_ratio.toFixed(2)} />
          <StatRow label="목표까지 여유" value={fmtPct(analysis.target_distance_pct)} />
          <StatRow label="손절까지 거리" value={fmtPct(analysis.stop_distance_pct)} />
          <StatRow label="헤드룸 점수" value={fmtPct(analysis.headroom_score)} />
          <StatRow label="평균 MFE" value={fmtPct(analysis.avg_mfe_pct)} />
          <StatRow label="평균 MAE" value={fmtPct(analysis.avg_mae_pct)} />
          <StatRow label="평균 결과 바 수" value={analysis.avg_bars_to_outcome.toFixed(1)} />
          <StatRow label="백테스트 edge" value={fmtPct(analysis.historical_edge_score)} />
          <StatRow label="추세 정렬 점수" value={fmtPct(analysis.trend_alignment_score)} />
          <StatRow label="와이코프 점수" value={fmtPct(analysis.wyckoff_score)} />
          {bestPattern && <StatRow label="Adam/Eve 적합도" value={fmtPct(bestPattern.variant_fit)} />}
          {bestPattern && <StatRow label="레그 균형" value={fmtPct(bestPattern.leg_balance_fit)} />}
          {bestPattern && <StatRow label="반전 에너지" value={fmtPct(bestPattern.reversal_energy_fit)} />}
          {bestPattern && <StatRow label="돌파 품질" value={fmtPct(bestPattern.breakout_quality_fit)} />}
          {bestPattern && <StatRow label="Retest 품질" value={fmtPct(bestPattern.retest_quality_fit)} />}
          {bestPattern && <StatRow label="캔들 확인 점수" value={fmtPct(bestPattern.candlestick_confirmation_fit)} />}
          {bestPattern && <StatRow label="거래량 맥락" value={fmtPct(bestPattern.volume_context_fit)} />}
          {bestPattern && <StatRow label="변동성 수축" value={fmtPct(bestPattern.volatility_context_fit)} />}
          <StatRow label="완성 임박도" value={fmtPct(analysis.completion_proximity)} />
          <StatRow label="신호 신선도" value={fmtPct(analysis.recency_score)} />
          <StatRow label="유사 패턴 표본 수" value={`${analysis.sample_size.toLocaleString('ko-KR')}건`} />
          <StatRow label="보정 승률" value={fmtPct(analysis.empirical_win_rate)} />
          <StatRow label="표본 신뢰도" value={fmtPct(analysis.sample_reliability)} />
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
          <StatRow label="타임프레임" value={analysis.timeframe_label} />
          <StatRow label="데이터 출처" value={analysis.data_source} />
          <StatRow label="데이터 상태" value={analysis.fetch_status_label} />
          <StatRow label="데이터 품질" value={fmtPct(analysis.data_quality, 0)} />
          <StatRow label="평균 거래대금" value={fmtTurnoverBillion(analysis.avg_turnover_billion)} />
          <StatRow label="유동성 점수" value={fmtPct(analysis.liquidity_score)} />
          <StatRow label="추세 방향" value={trendDirectionLabel(analysis.trend_direction)} />
          <StatRow label="와이코프 국면" value={WYCKOFF_LABELS[analysis.wyckoff_phase] ?? analysis.wyckoff_phase} />
          <StatRow
            label="장중 시간대"
            value={INTRADAY_SESSION_LABELS[analysis.intraday_session_phase] ?? analysis.intraday_session_phase}
          />
          <StatRow label="장중 문맥 점수" value={fmtPct(analysis.intraday_session_score)} />
          <StatRow label="통계 기준" value={analysis.stats_timeframe} />
          <StatRow label="사용 가능 바 수" value={`${analysis.available_bars.toLocaleString('ko-KR')}개`} />
          {analysis.bars_since_signal !== null && (
            <StatRow label="신호 이후 경과 바 수" value={`${analysis.bars_since_signal.toLocaleString('ko-KR')}개`} />
          )}
          <p className="pt-1 text-xs leading-relaxed text-muted-foreground">{analysis.source_note}</p>
          {analysis.wyckoff_note && <p className="text-xs text-sky-200">{analysis.wyckoff_note}</p>}
          {analysis.intraday_session_note && <p className="text-xs text-violet-200">{analysis.intraday_session_note}</p>}
          {analysis.trend_warning && <p className="text-xs text-amber-300">{analysis.trend_warning}</p>}
          {analysis.fetch_message && <p className="text-xs text-muted-foreground">{analysis.fetch_message}</p>}
        </div>
      </Card>

      {analysis.patterns.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>감지된 패턴</CardTitle>
          </CardHeader>
          <div className="space-y-3">
            {analysis.patterns.map((pattern, index) => (
              <div key={`${pattern.pattern_type}-${index}`} className="space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-medium">
                    {PATTERN_NAMES[pattern.pattern_type] ?? pattern.pattern_type}
                  </span>
                  <Badge variant="muted">{pattern.grade}급</Badge>
                </div>
                <div className="flex flex-wrap gap-2">
                  <span className={cn('rounded px-1.5 py-0.5 text-xs', STATE_COLORS[pattern.state])}>
                    {STATE_LABELS[pattern.state]}
                  </span>
                  {pattern.variant && (
                    <Badge variant="muted">
                      {PATTERN_VARIANT_NAMES[pattern.variant] ?? pattern.variant}
                    </Badge>
                  )}
                  <span className="text-xs text-muted-foreground">유사도 {fmtPct(pattern.textbook_similarity)}</span>
                </div>
                <div className="grid grid-cols-2 gap-2 text-xs text-muted-foreground">
                  <span>Adam/Eve 적합도 {fmtPct(pattern.variant_fit)}</span>
                  <span className="text-right">레그 균형 {fmtPct(pattern.leg_balance_fit)}</span>
                </div>
                <div className="grid grid-cols-2 gap-2 text-xs text-muted-foreground">
                  <span>반전 에너지 {fmtPct(pattern.reversal_energy_fit)}</span>
                  <span className="text-right">돌파 품질 {fmtPct(pattern.breakout_quality_fit)}</span>
                </div>
                <div className="grid grid-cols-2 gap-2 text-xs text-muted-foreground">
                  <span>Retest 품질 {fmtPct(pattern.retest_quality_fit)}</span>
                  <span className="text-right">캔들 확인 {fmtPct(pattern.candlestick_confirmation_fit)}</span>
                </div>
                <div className="grid grid-cols-1 gap-2 text-xs text-muted-foreground">
                  <span>
                    {CANDLE_CONFIRMATION_LABELS[pattern.candlestick_label ?? 'neutral'] ??
                      pattern.candlestick_label ??
                      '중립 캔들'}
                  </span>
                  {pattern.candlestick_note && <span>{pattern.candlestick_note}</span>}
                </div>
                <div className="grid grid-cols-2 gap-2 text-xs text-muted-foreground">
                  <span>거래량 맥락 {fmtPct(pattern.volume_context_fit)}</span>
                  <span className="text-right">변동성 수축 {fmtPct(pattern.volatility_context_fit)}</span>
                </div>
                {pattern.neckline && <StatRow label="목선" value={fmtPrice(pattern.neckline)} />}
                {pattern.invalidation_level && (
                  <StatRow label="무효화 기준" value={<span className="text-red-400">{fmtPrice(pattern.invalidation_level)}</span>} />
                )}
                {pattern.target_level && (
                  <StatRow label="목표가" value={<span className="text-green-400">{fmtPrice(pattern.target_level)}</span>} />
                )}
                {pattern.target_hit_at && <StatRow label="목표가 도달" value={fmtDateTime(pattern.target_hit_at)} />}
                {pattern.invalidated_at && <StatRow label="무효화" value={fmtDateTime(pattern.invalidated_at)} />}
              </div>
            ))}
          </div>
        </Card>
      )}

      <Card className="space-y-3">
        <div className="flex items-center gap-2 text-sm font-semibold">
          <ShieldAlert size={15} className="text-orange-400" />
          해석 주의
        </div>
        <p className="text-xs leading-relaxed text-muted-foreground">
          이 화면은 패턴 기반 보조 해석 도구입니다. 미래 경로 오버레이는 확정 예측이 아니라 현재 구조를 기준으로 만든 기본
          시나리오입니다. 이미 목표가를 한 번 도달한 패턴은 새로운 매수 신호가 아니라 기존 패턴 종료로 해석하는 것이 더 안전합니다.
        </p>
      </Card>
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
      <div className="space-y-2">
        <StatRow label="행동 우선순위" value={fmtPct(analysis.action_priority_score)} />
        <StatRow label="기준 타임프레임" value={analysis.timeframe_label} />
      </div>
    </Card>
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

function trendDirectionLabel(direction: string): string {
  if (direction === 'up') return '상승'
  if (direction === 'down') return '하락'
  return '횡보'
}

function patternActionText(pattern: PatternInfo, analysis: AnalysisResult): string {
  const bias = getPatternBias(pattern.pattern_type)
  const variantText = pattern.variant ? `${PATTERN_VARIANT_NAMES[pattern.variant] ?? pattern.variant} 타입으로 ` : ''

  if (pattern.state === 'played_out') {
    return `${variantText}기존 패턴 목표가가 이미 한 번 이상 도달된 상태로 보는 편이 맞습니다. 지금은 같은 패턴을 다시 추격하기보다 새로운 재축적 또는 이어지는 추세 패턴을 확인하는 쪽이 더 안전합니다.`
  }

  if (pattern.state === 'invalidated') {
    return `${variantText}기존 패턴은 무효화된 쪽으로 해석하는 편이 맞습니다. 손절 기준 이후 구조가 복원되는지부터 다시 확인하는 것이 좋습니다.`
  }

  if (pattern.state === 'forming') {
    return bias === 'bullish'
      ? `${variantText}아직 패턴을 만드는 중입니다. 레그 균형, 반전 에너지, 최근 확인 캔들, 목선 부근 거래량 확장을 먼저 보고 판단하는 편이 좋습니다.`
      : `${variantText}아직 패턴을 만드는 중입니다. 지지 이탈이나 반등 실패가 실제로 나오는지 조금 더 확인하는 편이 안전합니다.`
  }

  if (pattern.state === 'armed') {
    return bias === 'bullish'
      ? `${variantText}완성 직전 구간입니다. 급한 추격보다 목선 돌파와 Retest 유지, 확인 캔들 질을 함께 보는 편이 더 좋습니다.`
      : `${variantText}이탈 직전 구간입니다. 지지 붕괴가 실제로 확인되는지와 반등 캔들의 질을 함께 보는 편이 좋습니다.`
  }

  if (analysis.p_up >= 0.6) {
    return `${variantText}이미 확인된 패턴으로 해석됩니다. 다만 현재 자리에서 목표까지 여유, 손절 대비 기대수익, 최근 확인 캔들 강도를 같이 봐야 합니다.`
  }

  return `${variantText}패턴은 감지됐지만 확신 구간은 아닙니다. 교과서 유사도보다 현재 자리, 추세 정렬, 데이터 품질, 확인 캔들을 함께 보는 편이 더 안전합니다.`
}
