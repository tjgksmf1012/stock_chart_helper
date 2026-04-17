import { AlertCircle, TrendingDown, TrendingUp } from 'lucide-react'

import type { AnalysisResult } from '@/types/api'
import { Badge } from '@/components/ui/Badge'
import { Card, CardHeader, CardTitle } from '@/components/ui/Card'
import { ProbBar } from '@/components/ui/ProbBar'
import { StatRow } from '@/components/ui/StatRow'
import { cn, fmtPct, fmtPrice, PATTERN_NAMES, STATE_COLORS, STATE_LABELS } from '@/lib/utils'

interface AnalysisPanelProps {
  analysis: AnalysisResult
}

export function AnalysisPanel({ analysis }: AnalysisPanelProps) {
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
            {analysis.is_provisional && <Badge variant="warning" className="ml-auto">잠정</Badge>}
          </CardTitle>
        </CardHeader>
        <div className="space-y-3">
          <ProbBar p_up={analysis.p_up} p_down={analysis.p_down} size="md" />
          <p className="text-xs leading-relaxed text-muted-foreground">{analysis.reason_summary}</p>
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
          <StatRow label="유사 패턴 표본 수" value={`${analysis.sample_size}건`} />
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
    </div>
  )
}
