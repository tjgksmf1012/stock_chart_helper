import { fmtPrice, PATTERN_NAMES } from './utils'
import type { AnalysisResult, PatternInfo } from '@/types/api'

/**
 * Investing.com-style one-line chart summary, synthesized purely from the
 * existing analysis result (no LLM / API cost). Renders as a headline banner
 * above the chart: "이중 바닥 (W) 확인 완료 · 상승 우위 59% · 목표 30,282원".
 */

export interface ChartSummary {
  text: string
  tone: 'bullish' | 'bearish' | 'neutral'
}

const STATE_LABELS: Record<PatternInfo['state'], string> = {
  forming: '형성 중',
  armed: '돌파 임박',
  confirmed: '확인 완료',
  invalidated: '무효',
  played_out: '목표 소진',
}

export function buildChartSummary(analysis: AnalysisResult): ChartSummary {
  const pattern = analysis.patterns.find(
    p => p.state !== 'played_out' && p.state !== 'invalidated',
  ) ?? analysis.patterns[0]

  if (analysis.no_signal_flag || !pattern) {
    return {
      tone: 'neutral',
      text: `${analysis.timeframe_label} 기준 뚜렷한 활성 패턴이 없습니다. 새 구조가 잡히면 여기에 요약됩니다.`,
    }
  }

  const pUpPct = Math.round(analysis.p_up * 100)
  const pDownPct = Math.round(analysis.p_down * 100)
  const bullish = analysis.p_up >= analysis.p_down
  const tone: ChartSummary['tone'] = pUpPct === pDownPct ? 'neutral' : bullish ? 'bullish' : 'bearish'

  const name = PATTERN_NAMES[pattern.pattern_type] ?? pattern.pattern_type
  const stateLabel = STATE_LABELS[pattern.state] ?? pattern.state
  const biasLabel = bullish ? `상승 우위 ${pUpPct}%` : `하락 우위 ${pDownPct}%`

  const parts = [`${name} ${stateLabel}`, biasLabel]

  // 목표가는 아직 여유가 남아 있을 때만 (소진된 목표는 의미 없음). fmtPrice가 '원' 포함.
  if (pattern.target_level && analysis.target_distance_pct >= 0.02) {
    parts.push(`목표 ${fmtPrice(pattern.target_level)}`)
  }

  // 손절 기준가가 있으면 함께 (리스크 인지)
  if (pattern.invalidation_level) {
    parts.push(`손절 ${fmtPrice(pattern.invalidation_level)}`)
  }

  return { tone, text: parts.join(' · ') }
}
