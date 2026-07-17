import type { DashboardItem, DashboardResponse } from '@/types/api'

import { dashboardPriorityScore } from './dashboardSnapshot'

/**
 * Pure data-shaping for candidate lists: merges raw scan sections and builds
 * the watchlist alert deck. No React here, so it can be unit-tested directly.
 * (3-3-3 포커스/운용 루틴 덱은 3탭 재편에서 제거 — git 이력에 있음.)
 */

export interface WatchlistDeck {
  triggerClose: DashboardItem[]
  riskClose: DashboardItem[]
}

export function dedupeDashboardItems(sections: Array<DashboardResponse | undefined>) {
  const seen = new Set<string>()
  const items: DashboardItem[] = []

  for (const section of sections) {
    for (const item of section?.items ?? []) {
      const key = `${item.timeframe}-${item.symbol.code}`
      if (seen.has(key)) continue
      seen.add(key)
      items.push(item)
    }
  }

  return items
}

export function buildWatchlistDeck(items: DashboardItem[], isWatched: (code: string) => boolean): WatchlistDeck {
  const watchedItems = items.filter(item => isWatched(item.symbol.code))
  const triggerClose = [...watchedItems]
    .filter(item => !item.no_signal_flag && ['ready_now', 'watch'].includes(item.action_plan))
    .sort(
      (left, right) =>
        dashboardPriorityScore(right, 'steady', true) - dashboardPriorityScore(left, 'steady', true),
    )
    .slice(0, 4)

  const riskClose = [...watchedItems]
    .filter(item => item.no_signal_flag || item.action_plan === 'recheck' || item.risk_flags.length > 0)
    .sort((left, right) => afterMarketPriority(right) - afterMarketPriority(left))
    .slice(0, 4)

  return { triggerClose, riskClose }
}

function afterMarketPriority(item: DashboardItem) {
  return (
    (item.no_signal_flag ? 0.35 : 0) +
    (item.action_plan === 'recheck' ? 0.25 : 0) +
    Math.min(item.risk_flags.length * 0.08, 0.24) +
    (item.freshness_score < 0.35 ? 0.16 : 0) +
    (1 - (item.data_quality ?? 0)) * 0.08
  )
}
