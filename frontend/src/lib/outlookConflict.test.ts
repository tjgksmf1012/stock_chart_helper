import { describe, expect, it } from 'vitest'

import { detectOutlookConflict } from './outlookConflict'
import type { OutlookHorizon } from '@/types/api'

function horizon(days: number, q50: number): OutlookHorizon {
  return {
    horizon_days: days,
    label: `${days}일`,
    q10: q50 - 0.05,
    q25: q50 - 0.02,
    q50,
    q75: q50 + 0.02,
    q90: q50 + 0.05,
    coverage: { coverage: 0.8, hits: 80, n: 100, nominal: 0.8 },
  }
}

describe('detectOutlookConflict', () => {
  it('패턴 확률 높음 + 1개월 중앙값 음수 = 충돌 (한샘 사례)', () => {
    const result = detectOutlookConflict(0.649, [horizon(1, 0.001), horizon(20, -0.011)])
    expect(result.conflict).toBe(true)
    expect(result.medianPct).toBeCloseTo(-0.011)
  })

  it('확률 높아도 분포가 위를 가리키면 충돌 아님', () => {
    expect(detectOutlookConflict(0.7, [horizon(20, 0.02)]).conflict).toBe(false)
  })

  it('확률이 문턱(58%) 미만이면 충돌 아님', () => {
    expect(detectOutlookConflict(0.55, [horizon(20, -0.05)]).conflict).toBe(false)
  })

  it('1개월 구간이 없으면 1주(5일)로 대체 판정', () => {
    expect(detectOutlookConflict(0.65, [horizon(5, -0.02)]).conflict).toBe(true)
  })

  it('판정할 구간이 없거나 pUp이 null이면 충돌 아님', () => {
    expect(detectOutlookConflict(0.65, [horizon(60, -0.1)]).conflict).toBe(false)
    expect(detectOutlookConflict(null, [horizon(20, -0.05)]).conflict).toBe(false)
    expect(detectOutlookConflict(0.65, []).conflict).toBe(false)
  })
})
