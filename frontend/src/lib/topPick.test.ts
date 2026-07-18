import { describe, expect, it } from 'vitest'

import { pickTopSignal } from './topPick'
import type { LabEligibleStrategy, LabSignal } from '@/types/api'

function sig(strategy: string, code: string, day: string, verdict: string): LabSignal {
  return {
    strategy_id: strategy,
    strategy_label: `라벨-${strategy}`,
    code,
    signal_date: day,
    reference_price: 100,
    stop_price: 90,
    target_price: null,
    max_holding_days: 21,
    verdict,
  } as unknown as LabSignal
}

function elig(strategy: string, verdict: string, ev: number | null): LabEligibleStrategy {
  return { strategy_id: strategy, label: `라벨-${strategy}`, verdict, ev_pct: ev } as LabEligibleStrategy
}

const ELIGIBLE = [elig('tsmom', 'pass', 0.06), elig('high52', 'pass', 0.05), elig('xs', 'watch', 0.01)]

describe('pickTopSignal', () => {
  it('pass 신호 중 전략 EV가 가장 높은 것을 고른다', () => {
    const top = pickTopSignal(
      [sig('high52', 'A', '2026-07-18', 'pass'), sig('tsmom', 'B', '2026-07-18', 'pass')],
      ELIGIBLE,
    )
    expect(top?.code).toBe('B') // tsmom EV 0.06 > high52 0.05
  })

  it('같은 전략이면 최신 신호일 우선, 동일하면 코드 오름차순 (결정적)', () => {
    const top = pickTopSignal(
      [sig('tsmom', 'OLD', '2026-07-15', 'pass'), sig('tsmom', 'B', '2026-07-18', 'pass'), sig('tsmom', 'A', '2026-07-18', 'pass')],
      ELIGIBLE,
    )
    expect(top?.code).toBe('A')
  })

  it('watch 신호는 최우선으로 지목하지 않는다', () => {
    expect(pickTopSignal([sig('xs', 'C', '2026-07-18', 'watch')], ELIGIBLE)).toBeNull()
  })

  it('신호가 없으면 null', () => {
    expect(pickTopSignal([], ELIGIBLE)).toBeNull()
  })
})
