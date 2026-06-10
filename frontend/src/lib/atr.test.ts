import { describe, it, expect } from 'vitest'

import type { OHLCVBar } from '@/types/api'
import { calcATR, calcAtrStop, calcPosition } from './atr'

function flatBars(n: number): OHLCVBar[] {
  // every bar: TR = max(110-100, |110-105|, |100-105|) = 10
  return Array.from({ length: n }, (_, i) => ({
    date: `2024-01-${String(i + 1).padStart(2, '0')}`,
    open: 105,
    high: 110,
    low: 100,
    close: 105,
    volume: 1000,
    amount: null,
  }))
}

describe('calcATR', () => {
  it('averages the true range over the period', () => {
    expect(calcATR(flatBars(15))).toBe(10)
  })

  it('returns 0 when there are too few bars', () => {
    expect(calcATR(flatBars(10))).toBe(0)
  })
})

describe('calcAtrStop', () => {
  it('places a bullish stop below price', () => {
    const stop = calcAtrStop(10_000, 200, 2, true)
    expect(stop).not.toBeNull()
    expect(stop!.price).toBe(9_600)
    expect(stop!.distancePct).toBeCloseTo(4)
    expect(stop!.label).toBe('ATR×2')
  })

  it('places a bearish stop above price', () => {
    expect(calcAtrStop(10_000, 200, 2, false)!.price).toBe(10_400)
  })

  it('returns null without price or atr', () => {
    expect(calcAtrStop(0, 200, 2, true)).toBeNull()
    expect(calcAtrStop(10_000, 0, 2, true)).toBeNull()
  })
})

describe('calcPosition', () => {
  it('sizes shares so a stop-out loses roughly the risk budget', () => {
    const p = calcPosition(10_000_000, 0.01, 10_000, 9_500, 11_000)
    expect(p).not.toBeNull()
    expect(p!.maxLossKrw).toBe(100_000) // 1% of 10M
    expect(p!.shares).toBe(200) // floor(100_000 / 500)
    expect(p!.positionValue).toBe(2_000_000)
    expect(p!.positionPct).toBeCloseTo(20)
    expect(p!.rewardRisk).toBeCloseTo(2) // (11000-10000)/500
    expect(p!.rewardRiskOk).toBe(true)
  })

  it('reports rewardRisk 0 when no target is given', () => {
    expect(calcPosition(10_000_000, 0.01, 10_000, 9_500)!.rewardRisk).toBe(0)
  })

  it('returns null on degenerate input', () => {
    expect(calcPosition(0, 0.01, 10_000, 9_500)).toBeNull() // no account
    expect(calcPosition(10_000_000, 0.01, 10_000, 10_000)).toBeNull() // zero stop distance
  })

  it('caps shares at what the account can actually buy when the stop is tight', () => {
    // stop distance 10원 → uncapped risk-sizing would be 10,000 shares = 1억원,
    // 10x the account. Must cap at floor(10M / 10,000) = 1,000 shares (100%).
    const p = calcPosition(10_000_000, 0.01, 10_000, 9_990, 11_000)
    expect(p).not.toBeNull()
    expect(p!.shares).toBe(1_000)
    expect(p!.positionValue).toBeLessThanOrEqual(10_000_000)
    expect(p!.positionPct).toBeCloseTo(100)
    expect(p!.cashCapped).toBe(true)
  })

  it('does not flag cashCapped on normal sizing', () => {
    expect(calcPosition(10_000_000, 0.01, 10_000, 9_500, 11_000)!.cashCapped).toBe(false)
  })

  it('returns null when even one share is unaffordable', () => {
    expect(calcPosition(5_000, 0.01, 10_000, 9_990)).toBeNull()
  })
})
