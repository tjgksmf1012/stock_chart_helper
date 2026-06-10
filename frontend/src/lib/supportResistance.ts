import type { OHLCVBar } from '@/types/api'

/**
 * TrendSpider-style automatic support/resistance detection.
 *
 * Pipeline: swing pivots (strict local extrema over ±window bars, recent
 * `lookback` bars only) → price clustering (tolerancePct) → rank by touch
 * count then proximity to the last close → top maxPerSide per side.
 *
 * Bars must be sorted by date ascending (CandleChart already does this).
 */

export interface SwingPoint {
  index: number
  price: number
  type: 'high' | 'low'
}

export interface SRLevel {
  price: number
  touches: number
  kind: 'support' | 'resistance'
}

export interface SROptions {
  /** pivot confirmation half-width — a pivot needs `window` bars on each side */
  window?: number
  /** cluster tolerance as a fraction of price (0.015 = 1.5%) */
  tolerancePct?: number
  /** max levels returned per side */
  maxPerSide?: number
  /** only consider pivots within the last N bars */
  lookback?: number
}

export function findSwingPoints(bars: OHLCVBar[], window = 5, lookback = 250): SwingPoint[] {
  const n = bars.length
  if (n < window * 2 + 1) return []

  const start = Math.max(window, n - lookback)
  const end = n - 1 - window
  const points: SwingPoint[] = []

  for (let i = start; i <= end; i += 1) {
    let isHigh = true
    let isLow = true
    for (let j = i - window; j <= i + window; j += 1) {
      if (j === i) continue
      if (bars[j].high >= bars[i].high) isHigh = false
      if (bars[j].low <= bars[i].low) isLow = false
      if (!isHigh && !isLow) break
    }
    if (isHigh) points.push({ index: i, price: bars[i].high, type: 'high' })
    if (isLow) points.push({ index: i, price: bars[i].low, type: 'low' })
  }

  return points
}

export function computeSupportResistance(bars: OHLCVBar[], options: SROptions = {}): SRLevel[] {
  const { window = 5, tolerancePct = 0.015, maxPerSide = 3, lookback = 250 } = options
  if (bars.length === 0) return []

  const points = findSwingPoints(bars, window, lookback)
  if (points.length === 0) return []

  const lastClose = bars[bars.length - 1].close

  // 가격 오름차순으로 정렬 후, 군집 평균에서 tolerance 이내면 같은 레벨로 묶는다
  const sorted = [...points].sort((left, right) => left.price - right.price)
  const clusters: { sum: number; count: number }[] = []
  for (const point of sorted) {
    const current = clusters[clusters.length - 1]
    const mean = current ? current.sum / current.count : 0
    if (current && Math.abs(point.price - mean) <= mean * tolerancePct) {
      current.sum += point.price
      current.count += 1
    } else {
      clusters.push({ sum: point.price, count: 1 })
    }
  }

  const levels: SRLevel[] = clusters.map(cluster => {
    const price = cluster.sum / cluster.count
    return {
      price,
      touches: cluster.count,
      kind: price > lastClose ? ('resistance' as const) : ('support' as const),
    }
  })

  const pick = (kind: SRLevel['kind']) =>
    levels
      .filter(level => level.kind === kind)
      .sort(
        (left, right) =>
          right.touches - left.touches ||
          Math.abs(left.price - lastClose) - Math.abs(right.price - lastClose),
      )
      .slice(0, maxPerSide)

  return [...pick('resistance'), ...pick('support')]
}
