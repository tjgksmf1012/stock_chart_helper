import { describe, it, expect } from 'vitest'

import type { AnalysisResult, PatternInfo } from '@/types/api'
import { buildChartSummary } from './chartSummary'

function mkPattern(over: Partial<PatternInfo> = {}): PatternInfo {
  return {
    pattern_type: 'double_bottom',
    state: 'confirmed',
    grade: 'B',
    variant: null,
    lifecycle_score: 0.6,
    lifecycle_label: '확인 완료',
    lifecycle_note: '',
    textbook_similarity: 0.7,
    geometry_fit: 0.6,
    leg_balance_fit: 0.6,
    reversal_energy_fit: 0.6,
    variant_fit: 0.6,
    volume_context_fit: 0.6,
    volatility_context_fit: 0.6,
    breakout_quality_fit: 0.6,
    retest_quality_fit: 0.6,
    candlestick_confirmation_fit: 0.6,
    candlestick_label: null,
    candlestick_note: null,
    neckline: 26350,
    invalidation_level: 22572,
    target_level: 30282,
    key_points: [],
    is_provisional: false,
    start_dt: '2026-03-01',
    ...over,
  } as PatternInfo
}

function mkAnalysis(over: Partial<AnalysisResult> = {}): AnalysisResult {
  return {
    symbol: { code: '003490', name: '대한항공', market: 'KOSPI', sector: null, market_cap: null, is_in_universe: true },
    timeframe: '1d',
    timeframe_label: '일봉',
    p_up: 0.59,
    p_down: 0.41,
    target_distance_pct: 0.19,
    no_signal_flag: false,
    action_plan: 'watch',
    action_plan_label: '관찰 후보',
    trend_direction: 'up',
    patterns: [mkPattern()],
    ...over,
  } as AnalysisResult
}

describe('buildChartSummary', () => {
  it('returns a no-signal summary when there is no active pattern', () => {
    const s = buildChartSummary(mkAnalysis({ no_signal_flag: true, patterns: [] }))
    expect(s.tone).toBe('neutral')
    expect(s.text).toContain('뚜렷한')
  })

  it('names the pattern, state, direction and probability', () => {
    const s = buildChartSummary(mkAnalysis())
    expect(s.text).toContain('이중 바닥 (W)')
    expect(s.text).toContain('확인 완료')
    expect(s.text).toContain('59%')
  })

  it('includes the target price when headroom remains', () => {
    const s = buildChartSummary(mkAnalysis())
    // 30,282 formatted with thousands separator
    expect(s.text).toContain('30,282')
  })

  it('omits the target when target distance is negligible', () => {
    const s = buildChartSummary(
      mkAnalysis({ target_distance_pct: 0.0, patterns: [mkPattern({ target_level: 30282 })] }),
    )
    expect(s.text).not.toContain('30,282')
  })

  it('is bullish-toned when p_up dominates', () => {
    expect(buildChartSummary(mkAnalysis({ p_up: 0.62, p_down: 0.38 })).tone).toBe('bullish')
  })

  it('is bearish-toned when p_down dominates', () => {
    const s = buildChartSummary(
      mkAnalysis({ p_up: 0.34, p_down: 0.66, patterns: [mkPattern({ pattern_type: 'double_top' })] }),
    )
    expect(s.tone).toBe('bearish')
    expect(s.text).toContain('이중 천장 (M)')
  })

  it('falls back to the raw pattern_type when name is unknown', () => {
    const s = buildChartSummary(mkAnalysis({ patterns: [mkPattern({ pattern_type: 'mystery_x' })] }))
    expect(s.text).toContain('mystery_x')
  })
})
