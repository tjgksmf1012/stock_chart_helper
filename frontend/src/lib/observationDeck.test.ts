import { describe, expect, it } from 'vitest'

import { buildObservationDeck } from './observationDeck'
import type { DashboardItem, DashboardResponse } from '@/types/api'

function makeItem(code: string, overrides: Partial<DashboardItem> = {}): DashboardItem {
  return {
    symbol: { code, name: `종목${code}` },
    timeframe: 'D',
    pattern_type: 'double_bottom',
    setup_stage: 'late_base',
    p_up: 0.6,
    trade_readiness_score: 0.7,
    action_priority_score: 0.5,
    ...overrides,
  } as unknown as DashboardItem
}

function wrap(items: DashboardItem[]): DashboardResponse {
  return { items } as unknown as DashboardResponse
}

describe('buildObservationDeck', () => {
  it('여러 섹션을 합치되 같은 종목은 한 번만 남긴다 (먼저 온 섹션 우선)', () => {
    const deck = buildObservationDeck({
      armed: wrap([makeItem('005930')]),
      long: wrap([makeItem('005930', { p_up: 0.99 }), makeItem('000660')]),
      forming: wrap([makeItem('000660'), makeItem('035420')]),
    })
    expect(deck.items.map(i => i.symbol.code)).toEqual(['005930', '000660', '035420'])
    // armed 섹션의 005930이 이겨야 한다 (p_up 0.6 쪽)
    expect(deck.items[0].p_up).toBe(0.6)
  })

  it('임박(armed) 카운트와 고유 종목 수를 요약한다', () => {
    const deck = buildObservationDeck({
      armed: wrap([makeItem('A'), makeItem('B')]),
      long: wrap([makeItem('B'), makeItem('C')]),
    })
    expect(deck.uniqueCount).toBe(3)
    expect(deck.armedCount).toBe(2)
  })

  it('빈 입력은 빈 덱', () => {
    const deck = buildObservationDeck({})
    expect(deck.items).toEqual([])
    expect(deck.uniqueCount).toBe(0)
    expect(deck.armedCount).toBe(0)
  })

  it('undefined 섹션은 건너뛴다', () => {
    const deck = buildObservationDeck({ armed: undefined, long: wrap([makeItem('A')]) })
    expect(deck.uniqueCount).toBe(1)
  })
})
