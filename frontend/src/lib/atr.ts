import type { OHLCVBar } from '@/types/api'

/**
 * Calculate Average True Range (ATR) for given bars.
 * True Range = max(High-Low, |High-PrevClose|, |Low-PrevClose|)
 * ATR = simple moving average of last `period` TR values.
 */
export function calcATR(bars: OHLCVBar[], period = 14): number {
  if (bars.length < period + 1) return 0

  const trueRanges: number[] = []
  for (let i = 1; i < bars.length; i++) {
    const curr = bars[i]
    const prev = bars[i - 1]
    const tr = Math.max(
      curr.high - curr.low,
      Math.abs(curr.high - prev.close),
      Math.abs(curr.low - prev.close),
    )
    trueRanges.push(tr)
  }

  const recent = trueRanges.slice(-period)
  return recent.reduce((sum, v) => sum + v, 0) / recent.length
}

export interface StopInfo {
  price: number
  distancePct: number
  label: string
}

/** ATR 기반 손절가 계산 */
export function calcAtrStop(
  currentPrice: number,
  atr: number,
  multiplier: number,
  bullish: boolean,
): StopInfo | null {
  if (!currentPrice || !atr) return null
  const price = bullish
    ? currentPrice - atr * multiplier
    : currentPrice + atr * multiplier
  const distancePct = (Math.abs(currentPrice - price) / currentPrice) * 100
  return { price: Math.round(price), distancePct, label: `ATR×${multiplier}` }
}

export interface PositionCalc {
  maxLossKrw: number       // 최대 손실 금액 (원)
  stopPrice: number        // 사용 손절가
  stopDistancePct: number  // 손절 거리 %
  shares: number           // 매수 수량
  positionValue: number    // 투자 금액 (원)
  positionPct: number      // 계좌 대비 비중 %
  rewardRisk: number       // R:R 비율 (0=목표가 없음)
  rewardRiskOk: boolean    // 1:2 이상 여부
  cashCapped: boolean      // 현금 한도로 수량이 잘렸는지 (실제 리스크 < 설정 리스크)
}

/** 포지션 크기 계산 */
export function calcPosition(
  accountSize: number,
  riskPct: number,
  currentPrice: number,
  stopPrice: number,
  targetPrice?: number | null,
): PositionCalc | null {
  if (!accountSize || !currentPrice || !stopPrice) return null
  const stopDistance = Math.abs(currentPrice - stopPrice)
  if (stopDistance <= 0) return null

  const maxLossKrw = accountSize * riskPct
  let shares = Math.floor(maxLossKrw / stopDistance)
  if (shares <= 0) return null

  // 손절이 타이트하면 리스크 기준 수량이 계좌로 살 수 있는 양을 넘을 수 있음 — 현금 한도로 캡
  const maxAffordable = Math.floor(accountSize / currentPrice)
  const cashCapped = shares > maxAffordable
  if (cashCapped) shares = maxAffordable
  if (shares <= 0) return null

  const positionValue = shares * currentPrice
  const positionPct = (positionValue / accountSize) * 100
  const stopDistancePct = (stopDistance / currentPrice) * 100

  let rewardRisk = 0
  if (targetPrice && targetPrice !== currentPrice) {
    const reward = Math.abs(targetPrice - currentPrice)
    rewardRisk = reward / stopDistance
  }

  return {
    maxLossKrw,
    stopPrice,
    stopDistancePct,
    shares,
    positionValue,
    positionPct,
    rewardRisk,
    rewardRiskOk: rewardRisk >= 2.0,
    cashCapped,
  }
}
