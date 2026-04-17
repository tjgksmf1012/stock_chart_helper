import { AlertCircle, ShieldAlert, Target, TrendingDown, TrendingUp } from 'lucide-react'

import type { AnalysisResult, PatternInfo } from '@/types/api'
import { Badge } from '@/components/ui/Badge'
import { Card, CardHeader, CardTitle } from '@/components/ui/Card'
import { ProbBar } from '@/components/ui/ProbBar'
import { StatRow } from '@/components/ui/StatRow'
import { cn, fmtPct, fmtPrice, getPatternBias, PATTERN_NAMES, STATE_COLORS, STATE_LABELS } from '@/lib/utils'

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
          {analysis.is_provisional && <Badge variant="warning" className="ml-auto">잠정</Badge>}
        </div>
        <p className="text-xs text-muted-foreground">{analysis.no_signal_reason}</p>
        <p className="text-xs text-muted-foreground">{analysis.reason_summary}</p>
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
            {analysis.timeframe_label && <Badge variant="muted">{analysis.timeframe_label}</Badge>}
            {analysis.is_provisional && <Badge variant="warning" className="ml-auto">잠정</Badge>}
          </CardTitle>
        </CardHeader>
        <div className="space-y-3">
          <ProbBar p_up={analysis.p_up} p_down={analysis.p_down} size="md" />
          {analysis.source_note && (
            <p className="text-xs leading-relaxed text-muted-foreground">{analysis.source_note}</p>
          )}
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
            <div className="flex items-center gap-2">
              <Badge variant={badgeVariant(bestPattern)}>
                {PATTERN_NAMES[bestPattern.pattern_type] ?? bestPattern.pattern_type}
              </Badge>
              <span className={cn('rounded px-1.5 py-0.5 text-xs', STATE_COLORS[bestPattern.state])}>
                {STATE_LABELS[bestPattern.state]}
              </span>
            </div>
            <p className="mt-2 text-xs leading-relaxed text-muted-foreground">
              {patternActionText(bestPattern, analysis)}
            </p>
          </div>
          <div className="space-y-2">
            {bestPattern.target_level && (
              <StatRow label="우선 목표가" value={<span className="text-green-400">{fmtPrice(bestPattern.target_level)}</span>} />
            )}
            {bestPattern.invalidation_level && (
              <StatRow label="리스크 기준" value={<span className="text-red-400">{fmtPrice(bestPattern.invalidation_level)}</span>} />
            )}
          </div>
        </Card>
      )}

      <Card>
        <CardHeader>
          <CardTitle>점수 상세</CardTitle>
        </CardHeader>
        <div className="space-y-2">
          <StatRow label="교과서 유사도" value={fmtPct(analysis.textbook_similarity)} />
          <StatRow label="패턴 확인 점수" value={fmtPct(analysis.pattern_confirmation_score)} />
          <StatRow label="완성 임박도" value={fmtPct(analysis.completion_proximity)} />
          <StatRow label="신호 신선도" value={fmtPct(analysis.recency_score)} />
          <StatRow label="데이터 품질" value={fmtPct(analysis.data_quality)} />
          <StatRow label="신뢰도" value={fmtPct(analysis.confidence)} />
          <StatRow label="진입 적합도" value={fmtPct(analysis.entry_score)} />
          <StatRow label="유사 패턴 표본 수" value={`${analysis.sample_size}건`} />
          {analysis.bars_since_signal !== null && (
            <StatRow label="신호 이후 바 수" value={`${analysis.bars_since_signal}개`} />
          )}
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
                  <span className={cn('rounded px-1.5 py-0.5 text-xs', STATE_COLORS[pattern.state])}>
                    {STATE_LABELS[pattern.state]}
                  </span>
                  <span className="text-xs text-muted-foreground">유사도 {fmtPct(pattern.textbook_similarity)}</span>
                </div>
                <StatRow label="완성 임박도" value={fmtPct(pattern.completion_proximity)} />
                <StatRow label="신호 신선도" value={fmtPct(pattern.recency_score)} />
                {pattern.neckline && <StatRow label="목선" value={fmtPrice(pattern.neckline)} />}
                {pattern.invalidation_level && (
                  <StatRow
                    label="무효화 기준"
                    value={<span className="text-red-400">{fmtPrice(pattern.invalidation_level)}</span>}
                  />
                )}
                {pattern.target_level && (
                  <StatRow
                    label="목표가"
                    value={<span className="text-green-400">{fmtPrice(pattern.target_level)}</span>}
                  />
                )}
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
          이 화면은 패턴 기반 해석 보조 도구입니다. 확률이 높아도 추세 강도, 거래대금, 장세에 따라 결과가 달라질 수 있으니
          목선과 무효화 기준을 함께 보면서 보수적으로 해석하는 편이 안전합니다.
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

  if (pattern.state === 'forming') {
    return bias === 'bullish'
      ? '아직 구조가 완전히 닫히지 않았습니다. 목선 돌파와 거래량 반응이 실제로 따라오는지 확인하는 구간입니다.'
      : '아직 구조가 완전히 닫히지 않았습니다. 지지 이탈이나 추세 약화가 실제로 따라오는지 확인하는 구간입니다.'
  }

  if (pattern.state === 'armed') {
    return bias === 'bullish'
      ? '확인 직전 구간입니다. 추격보다는 돌파가 유지되는지, 눌림에서도 살아남는지 확인하는 접근이 안전합니다.'
      : '이탈 직전 구간입니다. 급한 진입보다 지지 붕괴와 반등 실패가 함께 나오는지 확인하는 접근이 좋습니다.'
  }

  if (analysis.p_up >= 0.6) {
    return '이미 확인된 패턴으로 해석되고 있습니다. 다만 목표가보다 먼저 무효화 기준을 지키는지가 더 중요합니다.'
  }

  return '패턴은 감지됐지만 아직 확신 구간은 아닙니다. 확률, 유사도, 무효화 기준을 함께 보며 보수적으로 접근하는 편이 좋습니다.'
}
