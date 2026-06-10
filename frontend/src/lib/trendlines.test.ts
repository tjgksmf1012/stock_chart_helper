import { describe, it, expect } from 'vitest'

import type { OHLCVBar } from '@/types/api'
import { computeTrendlines } from './trendlines'

function dateAt(i: number): string {
  const d = new Date(Date.UTC(2024, 0, 1))
  d.setUTCDate(d.getUTCDate() + i)
  return d.toISOString().slice(0, 10)
}

function mkBar(i: number, high: number, low: number): OHLCVBar {
  const mid = (high + low) / 2
  return {
    date: dateAt(i),
    open: mid,
    high,
    low,
    close: mid,
    volume: 1000,
    amount: null,
  }
}

/**
 * Bars whose lows ride an ascending line, touching it exactly at pivotIndices.
 * Non-pivot lows sit 5 above the line — far enough that ±5-bar strict-min
 * pivot detection works for slope 0.5 (5 > 0.5 * 5), and far enough to not
 * count as line touches. Highs are 10 above lows (monotone → no swing highs).
 */
function ascendingSupportBars(n: number, pivotIndices: number[], base = 100, slope = 0.5): OHLCVBar[] {
  const line = (i: number) => base + slope * i
  return Array.from({ length: n }, (_, i) => {
    const low = pivotIndices.includes(i) ? line(i) : line(i) + 5
    return mkBar(i, low + 10, low)
  })
}

/** Mirror: highs ride a descending line; non-pivot highs sit 5 below it. */
function descendingResistanceBars(n: number, pivotIndices: number[], base = 200, slope = -0.5): OHLCVBar[] {
  const line = (i: number) => base + slope * i
  return Array.from({ length: n }, (_, i) => {
    const high = pivotIndices.includes(i) ? line(i) : line(i) - 5
    return mkBar(i, high, high - 10)
  })
}

describe('computeTrendlines', () => {
  it('returns empty for too few bars', () => {
    expect(computeTrendlines(ascendingSupportBars(8, []))).toEqual([])
  })

  it('detects an ascending support trendline through 3 swing lows', () => {
    const bars = ascendingSupportBars(80, [15, 40, 65])
    const lines = computeTrendlines(bars)
    const support = lines.find(line => line.kind === 'support')
    expect(support).toBeDefined()
    expect(support!.touches).toBeGreaterThanOrEqual(3)
    expect(support!.slopePerBar).toBeCloseTo(0.5, 1)
    expect(support!.startPrice).toBeCloseTo(100 + 0.5 * support!.startIndex, 0)
  })

  it('detects a descending resistance trendline through 3 swing highs', () => {
    const bars = descendingResistanceBars(80, [15, 40, 65])
    const lines = computeTrendlines(bars)
    const resistance = lines.find(line => line.kind === 'resistance')
    expect(resistance).toBeDefined()
    expect(resistance!.touches).toBeGreaterThanOrEqual(3)
    expect(resistance!.slopePerBar).toBeCloseTo(-0.5, 1)
  })

  it('ignores weak 2-touch lines', () => {
    const bars = ascendingSupportBars(80, [15, 55])
    const lines = computeTrendlines(bars)
    expect(lines.find(line => line.kind === 'support')).toBeUndefined()
  })

  it('rejects a resistance line that price pierces above', () => {
    const bars = descendingResistanceBars(80, [15, 40, 65])
    // 앵커들 사이에서 라인을 크게 뚫는 스파이크 — 유효한 저항선이 아님
    const lineAt55 = 200 - 0.5 * 55
    bars[55] = mkBar(55, lineAt55 + 30, lineAt55 + 20)
    const lines = computeTrendlines(bars)
    expect(lines.find(line => line.kind === 'resistance')).toBeUndefined()
  })

  it('rejects a support line that price breaks below', () => {
    const bars = ascendingSupportBars(80, [15, 40, 65])
    const lineAt55 = 100 + 0.5 * 55
    bars[55] = mkBar(55, lineAt55 - 20, lineAt55 - 30)
    const lines = computeTrendlines(bars)
    expect(lines.find(line => line.kind === 'support')).toBeUndefined()
  })

  it('respects the minSpanBars option', () => {
    const bars = ascendingSupportBars(80, [15, 25, 35])
    expect(computeTrendlines(bars, { minSpanBars: 30 }).find(line => line.kind === 'support')).toBeUndefined()
    expect(computeTrendlines(bars, { minSpanBars: 10 }).find(line => line.kind === 'support')).toBeDefined()
  })

  it('returns at most one line per side', () => {
    const bars = ascendingSupportBars(120, [10, 35, 60, 85, 105])
    const lines = computeTrendlines(bars)
    expect(lines.filter(line => line.kind === 'support').length).toBe(1)
    expect(lines.filter(line => line.kind === 'resistance').length).toBe(0)
  })

  it('drops lines that drifted too far from the current price', () => {
    // 초반 급등 구간의 가파른 저항선(기울기 +3) 이후 가격이 횡보하면,
    // 라인은 계속 위로 멀어져 마지막 봉 시점에 현재가 대비 ±25%를 벗어남 → 제외
    const line = (i: number) => 100 + 3 * i
    const bars = Array.from({ length: 120 }, (_, i) => {
      if (i <= 30) {
        const high = [5, 15, 25].includes(i) ? line(i) : line(i) - 20
        return mkBar(i, high, high - 10)
      }
      return mkBar(i, 180, 170)
    })
    const lines = computeTrendlines(bars)
    expect(lines.find(line => line.kind === 'resistance')).toBeUndefined()
  })
})
