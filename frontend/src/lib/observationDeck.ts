import type { DashboardItem, DashboardResponse } from '@/types/api'

/**
 * 대시보드의 여러 후보 섹션을 "관찰 후보" 단일 덱으로 합친다.
 * 같은 종목이 여러 섹션에 나오면 우선순위가 높은 섹션이 이긴다
 * (armed 완성 임박 → long 지금 볼 → live → forming → sim → short → nosig).
 */
export type ObservationSectionKey = 'armed' | 'long' | 'live' | 'forming' | 'sim' | 'short' | 'nosig'

export interface ObservationDeck {
  items: DashboardItem[]
  uniqueCount: number
  armedCount: number
}

const SECTION_ORDER: ObservationSectionKey[] = ['armed', 'long', 'live', 'forming', 'sim', 'short', 'nosig']

export function buildObservationDeck(
  sections: Partial<Record<ObservationSectionKey, DashboardResponse | undefined>>,
): ObservationDeck {
  const seen = new Set<string>()
  const items: DashboardItem[] = []
  let armedCount = 0

  for (const key of SECTION_ORDER) {
    for (const item of sections[key]?.items ?? []) {
      const code = item.symbol.code
      if (seen.has(code)) continue
      seen.add(code)
      items.push(item)
      if (key === 'armed') armedCount += 1
    }
  }
  return { items, uniqueCount: items.length, armedCount }
}
