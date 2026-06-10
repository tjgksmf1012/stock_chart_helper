import { describe, it, expect } from 'vitest'

import type { OHLCVBar } from '@/types/api'
import { computeSupportResistance, findSwingPoints } from './supportResistance'

function dateAt(i: number): string {
  const d = new Date(Date.UTC(2024, 0, 1))
  d.setUTCDate(d.getUTCDate() + i)
  return d.toISOString().slice(0, 10)
}

function flatBars(n: number, price = 100): OHLCVBar[] {
  return Array.from({ length: n }, (_, i) => ({
    date: dateAt(i),
    open: price,
    high: price + 1,
    low: price - 1,
    close: price,
    volume: 1000,
    amount: null,
  }))
}

function withSwingHigh(bars: OHLCVBar[], index: number, high: number): OHLCVBar[] {
  const out = bars.map(bar => ({ ...bar }))
  out[index].high = high
  return out
}

function withSwingLow(bars: OHLCVBar[], index: number, low: number): OHLCVBar[] {
  const out = bars.map(bar => ({ ...bar }))
  out[index].low = low
  return out
}

describe('findSwingPoints', () => {
  it('returns empty for too few bars', () => {
    expect(findSwingPoints(flatBars(8))).toEqual([])
  })

  it('returns empty for flat bars (no strict extrema)', () => {
    expect(findSwingPoints(flatBars(60))).toEqual([])
  })

  it('detects a swing high spike', () => {
    const bars = withSwingHigh(flatBars(60), 20, 120)
    const points = findSwingPoints(bars)
    expect(points).toHaveLength(1)
    expect(points[0]).toMatchObject({ index: 20, price: 120, type: 'high' })
  })

  it('detects a swing low spike', () => {
    const bars = withSwingLow(flatBars(60), 30, 80)
    const points = findSwingPoints(bars)
    expect(points).toHaveLength(1)
    expect(points[0]).toMatchObject({ index: 30, price: 80, type: 'low' })
  })

  it('ignores pivots in the unconfirmed tail (last `window` bars)', () => {
    const bars = withSwingHigh(flatBars(60), 57, 120)
    expect(findSwingPoints(bars)).toEqual([])
  })

  it('ignores pivots older than the lookback', () => {
    let bars = flatBars(400)
    bars = withSwingHigh(bars, 50, 120) // older than 400-250=150 → excluded
    bars = withSwingHigh(bars, 300, 130) // recent → included
    const points = findSwingPoints(bars, 5, 250)
    expect(points).toHaveLength(1)
    expect(points[0].index).toBe(300)
  })
})

describe('computeSupportResistance', () => {
  it('returns empty for empty input', () => {
    expect(computeSupportResistance([])).toEqual([])
  })

  it('clusters nearby swing highs into one resistance level', () => {
    let bars = flatBars(60)
    bars = withSwingHigh(bars, 15, 120)
    bars = withSwingHigh(bars, 35, 121) // 0.83% apart → same cluster
    const levels = computeSupportResistance(bars)
    const resistance = levels.filter(level => level.kind === 'resistance')
    expect(resistance).toHaveLength(1)
    expect(resistance[0].touches).toBe(2)
    expect(resistance[0].price).toBeCloseTo(120.5, 1)
  })

  it('clusters nearby swing lows into one support level', () => {
    let bars = flatBars(60)
    bars = withSwingLow(bars, 20, 80)
    bars = withSwingLow(bars, 40, 80.5)
    const levels = computeSupportResistance(bars)
    const support = levels.filter(level => level.kind === 'support')
    expect(support).toHaveLength(1)
    expect(support[0].touches).toBe(2)
    expect(support[0].price).toBeCloseTo(80.25, 1)
  })

  it('keeps far-apart levels separate, nearest to price first', () => {
    let bars = flatBars(80)
    bars = withSwingHigh(bars, 15, 120)
    bars = withSwingHigh(bars, 45, 140) // 17% apart → separate clusters
    const levels = computeSupportResistance(bars)
    const resistance = levels.filter(level => level.kind === 'resistance')
    expect(resistance).toHaveLength(2)
    // same touch count → nearer level (120) ranks first
    expect(resistance[0].price).toBeCloseTo(120, 1)
    expect(resistance[1].price).toBeCloseTo(140, 1)
  })

  it('ranks multi-touch levels above single-touch levels', () => {
    let bars = flatBars(100)
    bars = withSwingHigh(bars, 10, 110) // single touch, nearest
    bars = withSwingHigh(bars, 40, 130)
    bars = withSwingHigh(bars, 70, 130.5) // 2 touches, farther
    const levels = computeSupportResistance(bars)
    const resistance = levels.filter(level => level.kind === 'resistance')
    expect(resistance[0].price).toBeCloseTo(130.25, 1)
    expect(resistance[0].touches).toBe(2)
  })

  it('caps each side at maxPerSide', () => {
    let bars = flatBars(120)
    bars = withSwingHigh(bars, 10, 110)
    bars = withSwingHigh(bars, 35, 125)
    bars = withSwingHigh(bars, 60, 145)
    bars = withSwingHigh(bars, 85, 170)
    const levels = computeSupportResistance(bars, { maxPerSide: 3 })
    const resistance = levels.filter(level => level.kind === 'resistance')
    expect(resistance).toHaveLength(3)
    // the farthest single-touch level (170) is dropped
    expect(resistance.every(level => level.price < 160)).toBe(true)
  })

  it('classifies levels relative to the last close', () => {
    let bars = flatBars(60)
    bars = withSwingHigh(bars, 20, 120)
    bars = withSwingLow(bars, 30, 85)
    const levels = computeSupportResistance(bars)
    expect(levels.find(level => level.price > 100)?.kind).toBe('resistance')
    expect(levels.find(level => level.price < 100)?.kind).toBe('support')
  })
})
