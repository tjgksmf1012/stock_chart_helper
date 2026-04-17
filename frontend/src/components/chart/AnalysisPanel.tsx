import type { AnalysisResult } from '@/types/api'
import { Card, CardHeader, CardTitle } from '@/components/ui/Card'
import { Badge } from '@/components/ui/Badge'
import { ProbBar } from '@/components/ui/ProbBar'
import { StatRow } from '@/components/ui/StatRow'
import { fmtPct, PATTERN_NAMES, STATE_LABELS, STATE_COLORS, fmtPrice } from '@/lib/utils'
import { cn } from '@/lib/utils'
import { AlertCircle, TrendingUp, TrendingDown } from 'lucide-react'

interface AnalysisPanelProps {
  analysis: AnalysisResult
}

export function AnalysisPanel({ analysis }: AnalysisPanelProps) {
  const best = analysis.patterns[0]

  if (analysis.no_signal_flag) {
    return (
      <Card className="space-y-3">
        <div className="flex items-center gap-2 text-yellow-400">
          <AlertCircle size={16} />
          <span className="text-sm font-semibold">No Signal</span>
          {analysis.is_provisional && (
            <Badge variant="warning" className="ml-auto">잠정</Badge>
          )}
        </div>
        <p className="text-xs text-muted-foreground">{analysis.no_signal_reason}</p>
        <p className="text-xs text-muted-foreground">{analysis.reason_summary}</p>
      </Card>
    )
  }

  return (
    <div className="space-y-3">
      {/* Probability */}
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
          <p className="text-xs text-muted-foreground leading-relaxed">{analysis.reason_summary}</p>
        </div>
      </Card>

      {/* Scores */}
      <Card>
        <CardHeader><CardTitle>점수 상세</CardTitle></CardHeader>
        <div className="space-y-2">
          <StatRow label="교과서 유사도" value={fmtPct(analysis.textbook_similarity)} />
          <StatRow label="패턴 확인 점수" value={fmtPct(analysis.pattern_confirmation_score)} />
          <StatRow label="신뢰도" value={fmtPct(analysis.confidence)} />
          <StatRow label="진입 적합도" value={fmtPct(analysis.entry_score)} />
          <StatRow label="유사 사례 수" value={`${analysis.sample_size}건`} />
        </div>
      </Card>

      {/* Detected patterns */}
      {analysis.patterns.length > 0 && (
        <Card>
          <CardHeader><CardTitle>감지된 패턴</CardTitle></CardHeader>
          <div className="space-y-3">
            {analysis.patterns.map((p, i) => (
              <div key={i} className="space-y-1.5">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-medium">{PATTERN_NAMES[p.pattern_type] ?? p.pattern_type}</span>
                  <Badge variant="muted">{p.grade}급</Badge>
                </div>
                <div className="flex gap-2">
                  <span className={cn('text-xs px-1.5 py-0.5 rounded', STATE_COLORS[p.state])}>
                    {STATE_LABELS[p.state]}
                  </span>
                  <span className="text-xs text-muted-foreground">유사도 {fmtPct(p.textbook_similarity)}</span>
                </div>
                {p.neckline && (
                  <StatRow label="목선" value={fmtPrice(p.neckline)} />
                )}
                {p.invalidation_level && (
                  <StatRow label="무효화 기준" value={
                    <span className="text-red-400">{fmtPrice(p.invalidation_level)}</span>
                  } />
                )}
                {p.target_level && (
                  <StatRow label="목표가" value={
                    <span className="text-green-400">{fmtPrice(p.target_level)}</span>
                  } />
                )}
              </div>
            ))}
          </div>
        </Card>
      )}
    </div>
  )
}
