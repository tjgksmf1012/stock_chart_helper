import { AlertCircle, Database, ShieldAlert, Target, TrendingDown, TrendingUp } from 'lucide-react'

import type { AnalysisResult, PatternInfo } from '@/types/api'
import { Badge } from '@/components/ui/Badge'
import { Card, CardHeader, CardTitle } from '@/components/ui/Card'
import { ProbBar } from '@/components/ui/ProbBar'
import { StatRow } from '@/components/ui/StatRow'
import {
  cn,
  fmtPct,
  fmtPrice,
  fmtTurnoverBillion,
  getPatternBias,
  PATTERN_NAMES,
  STATE_COLORS,
  STATE_LABELS,
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
              <span className={cn('rounded px-1.5 py-0.5 text-xs', STATE_COLORS[bestPattern.state])}>
                {STATE_LABELS[bestPattern.state]}
              </span>
            </div>
            <p className="mt-2 text-xs leading-relaxed text-muted-foreground">{patternActionText(bestPattern, analysis)}</p>
          </div>
          <div className="space-y-2">
            {bestPattern.target_level && (
              <StatRow label="우선 목표가" value={<span className="text-green-400">{fmtPrice(bestPattern.target_level)}</span>} />
            )}
            {bestPattern.invalidation_level && (
              <StatRow label="리스크 기준" value={<span className="text-red-400">{fmtPrice(bestPattern.invalidation_level)}</span>} />
            )}
            {bestPattern.target_hit_at && <StatRow label="목표가 도달 시점" value={bestPattern.target_hit_at} />}
            {bestPattern.invalidated_at && <StatRow label="무효화 시점" value={bestPattern.invalidated_at} />}
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
          <StatRow label="목표까지 남은 여지" value={fmtPct(analysis.target_distance_pct)} />
          <StatRow label="손절까지 거리" value={fmtPct(analysis.stop_distance_pct)} />
          <StatRow label="자리 점수" value={fmtPct(analysis.headroom_score)} />
          {bestPattern && <StatRow label="돌파 품질" value={fmtPct(bestPattern.breakout_quality_fit)} />}
          {bestPattern && <StatRow label="retest 품질" value={fmtPct(bestPattern.retest_quality_fit)} />}
          <StatRow label="완성 임박도" value={fmtPct(analysis.completion_proximity)} />
          <StatRow label="신호 신선도" value={fmtPct(analysis.recency_score)} />
          <StatRow label="유사 패턴 표본 수" value={`${analysis.sample_size}건`} />
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
          <StatRow label="통계 기준" value={analysis.stats_timeframe} />
          <StatRow label="사용 가능 바 수" value={`${analysis.available_bars}개`} />
          {analysis.bars_since_signal !== null && <StatRow label="신호 발생 후 경과 바" value={`${analysis.bars_since_signal}개`} />}
          <p className="pt-1 text-xs leading-relaxed text-muted-foreground">{analysis.source_note}</p>
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
              <div key={`${pattern.pattern_type}-${index}`} className="space-y-1.5">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-medium">{PATTERN_NAMES[pattern.pattern_type] ?? pattern.pattern_type}</span>
                  <Badge variant="muted">{pattern.grade}급</Badge>
                </div>
                <div className="flex gap-2">
                  <span className={cn('rounded px-1.5 py-0.5 text-xs', STATE_COLORS[pattern.state])}>{STATE_LABELS[pattern.state]}</span>
                  <span className="text-xs text-muted-foreground">유사도 {fmtPct(pattern.textbook_similarity)}</span>
                </div>
                <div className="grid grid-cols-2 gap-2 text-xs text-muted-foreground">
                  <span>돌파 품질 {fmtPct(pattern.breakout_quality_fit)}</span>
                  <span className="text-right">retest 품질 {fmtPct(pattern.retest_quality_fit)}</span>
                </div>
                {pattern.neckline && <StatRow label="목선" value={fmtPrice(pattern.neckline)} />}
                {pattern.invalidation_level && (
                  <StatRow label="무효화 기준" value={<span className="text-red-400">{fmtPrice(pattern.invalidation_level)}</span>} />
                )}
                {pattern.target_level && <StatRow label="목표가" value={<span className="text-green-400">{fmtPrice(pattern.target_level)}</span>} />}
                {pattern.target_hit_at && <StatRow label="목표가 도달" value={pattern.target_hit_at} />}
                {pattern.invalidated_at && <StatRow label="무효화" value={pattern.invalidated_at} />}
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
          이 화면은 패턴 기반 해석 보조 도구입니다. 미래 경로 오버레이는 확정 예측이 아니라 현재 구조를 기준으로 만든 기본 시나리오입니다.
          목표가를 이미 찍은 패턴은 새로운 매수 신호가 아니라 기존 패턴 종료로 봐야 하고, 새 진입은 별도 재축적 패턴으로 다시 판단하는 편이 좋습니다.
        </p>
      </Card>
    </div>
  )
}

function badgeVariant(pattern: PatternInfo): 'bullish' | 'bearish' | 'neutral' {
  return getPatternBias(pattern.pattern_type)
}

function patternActionText(pattern: PatternInfo, analysis: AnalysisResult): string {
  const bias = getPatternBias(pattern.pattern_type)

  if (pattern.state === 'played_out') {
    return '기존 패턴 목표가가 이미 도달된 상태로 보는 편이 맞습니다. 지금은 같은 패턴의 재매수보다 재축적 또는 새 패턴 형성을 다시 확인하는 편이 좋습니다.'
  }

  if (pattern.state === 'invalidated') {
    return '기존 패턴은 이미 무효화된 쪽으로 해석하는 편이 안전합니다. 손절 이후 재진입은 새로운 구조가 생길 때 다시 보는 편이 좋습니다.'
  }

  if (pattern.state === 'forming') {
    return bias === 'bullish'
      ? '아직 패턴이 완성되기 전 단계입니다. 목선 돌파와 거래대금 반응이 실제로 붙는지 먼저 확인하는 편이 좋습니다.'
      : '아직 패턴이 완성되기 전 단계입니다. 지지 이탈이나 반등 실패가 실제로 확정되는지 조금 더 지켜보는 편이 좋습니다.'
  }

  if (pattern.state === 'armed') {
    return bias === 'bullish'
      ? '완성 직전 구간입니다. 성급한 추격보다 돌파가 유지되는지, 눌림을 버티는지 확인한 뒤 대응하는 편이 안정적입니다.'
      : '이탈 직전 구간입니다. 급한 진입보다 지지 붕괴와 반등 실패가 같이 나오는지 확인하는 편이 좋습니다.'
  }

  if (analysis.p_up >= 0.6) {
    return '이미 확인된 패턴으로 해석하고 있습니다. 다만 목표가보다 먼저 무효화 기준을 지키는지가 더 중요합니다.'
  }

  return '패턴은 감지됐지만 확신 구간은 아닙니다. 확률, 유사도, 무효화 기준을 함께 보고 보수적으로 접근하는 편이 좋습니다.'
}
