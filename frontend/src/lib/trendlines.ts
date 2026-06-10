import type { OHLCVBar } from '@/types/api'

import { findSwingPoints, type SwingPoint } from './supportResistance'

/**
 * TrendSpider-style automatic diagonal trendline detection.
 *
 * For each side (support = swing lows, resistance = swing highs):
 * 1. Try every pivot pair as line anchors (minSpanBars apart).
 * 2. Count touches: pivots lying within touchTolerancePct of the line.
 * 3. Reject lines that price meaningfully pierces anywhere from the first
 *    anchor to the last bar (violationTolerancePct).
 * 4. Reject lines whose value at the last bar drifted more than maxDriftPct
 *    away from the current close (no longer actionable).
 * 5. Keep the best line per side: most touches, then widest span.
 *
 * Requires >= 3 touches — 2-touch lines are noise.
 * Bars must be sorted by date ascending.
 */

export interface Trendline {
  kind: 'support' | 'resistance'
  startIndex: number
  startPrice: number
  /** index of the last bar (line is meant to extend to/past it) */
  endIndex: number
  /** line value at endIndex */
  endPrice: number
  slopePerBar: number
  touches: number
}

export interface TrendlineOptions {
  /** pivot confirmation half-width (passed to findSwingPoints) */
  window?: number
  /** only consider pivots within the last N bars */
  lookback?: number
  /** minimum bar distance between the two line anchors */
  minSpanBars?: number
  /** how close (fraction of price) a pivot must be to the line to count as a touch */
  touchTolerancePct?: number
  /** how far (fraction of price) a bar may pierce the line before it invalidates */
  violationTolerancePct?: number
  /** max distance (fraction of close) between line value at the last bar and the close */
  maxDriftPct?: number
  /** minimum touches for a valid line */
  minTouches?: number
}

export function computeTrendlines(bars: OHLCVBar[], options: TrendlineOptions = {}): Trendline[] {
  const {
    window = 5,
    lookback = 250,
    minSpanBars = 10,
    touchTolerancePct = 0.01,
    violationTolerancePct = 0.005,
    maxDriftPct = 0.25,
    minTouches = 3,
  } = options

  if (bars.length === 0) return []
  const points = findSwingPoints(bars, window, lookback)
  if (points.length === 0) return []

  const lastIndex = bars.length - 1
  const lastClose = bars[lastIndex].close
  const highs = points.filter(point => point.type === 'high')
  const lows = points.filter(point => point.type === 'low')

  const result: Trendline[] = []
  const resistance = bestLine('resistance', highs)
  const support = bestLine('support', lows)
  if (resistance) result.push(resistance)
  if (support) result.push(support)
  return result

  function bestLine(kind: Trendline['kind'], pivots: SwingPoint[]): Trendline | null {
    let best: Trendline | null = null
    let bestSpan = 0

    for (let a = 0; a < pivots.length - 1; a += 1) {
      for (let b = a + 1; b < pivots.length; b += 1) {
        const p1 = pivots[a]
        const p2 = pivots[b]
        const span = p2.index - p1.index
        if (span < minSpanBars) continue

        const slope = (p2.price - p1.price) / span
        const lineAt = (index: number) => p1.price + slope * (index - p1.index)

        // 현재가에서 너무 멀어진 라인은 더 이상 실전 기준선이 아님
        const valueAtLast = lineAt(lastIndex)
        if (Math.abs(valueAtLast - lastClose) > lastClose * maxDriftPct) continue

        // 첫 앵커부터 마지막 봉까지 라인을 의미 있게 뚫으면 무효
        let violated = false
        for (let k = p1.index; k <= lastIndex; k += 1) {
          const limit = lineAt(k)
          if (kind === 'resistance') {
            if (bars[k].high > limit * (1 + violationTolerancePct)) {
              violated = true
              break
            }
          } else if (bars[k].low < limit * (1 - violationTolerancePct)) {
            violated = true
            break
          }
        }
        if (violated) continue

        let touches = 0
        for (const pivot of pivots) {
          if (Math.abs(pivot.price - lineAt(pivot.index)) <= lineAt(pivot.index) * touchTolerancePct) {
            touches += 1
          }
        }
        if (touches < minTouches) continue

        if (!best || touches > best.touches || (touches === best.touches && span > bestSpan)) {
          best = {
            kind,
            startIndex: p1.index,
            startPrice: p1.price,
            endIndex: lastIndex,
            endPrice: valueAtLast,
            slopePerBar: slope,
            touches,
          }
          bestSpan = span
        }
      }
    }

    return best
  }
}
