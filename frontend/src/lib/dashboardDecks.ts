import type { DashboardItem, DashboardResponse } from '@/types/api'

import {
  type CandidateMovement,
  type CandidateSnapshot,
  candidateMovement,
  dashboardPriorityScore,
  dashboardSnapshotKey,
} from './dashboardSnapshot'

/**
 * Pure data-shaping for the dashboard: turns raw scan sections into the
 * focus / watchlist / routine "decks" the page renders. No React here, so it
 * can be unit-tested directly.
 */

export interface FocusCandidate {
  item: DashboardItem
  movement: CandidateMovement
  watched: boolean
  score: number
}

export interface WatchlistDeck {
  triggerClose: DashboardItem[]
  riskClose: DashboardItem[]
}

export interface RoutineDeck {
  premarket: DashboardItem[]
  intraday: DashboardItem[]
  afterMarket: DashboardItem[]
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

export function buildFocusDeck(items: DashboardItem[], snapshot: Record<string, CandidateSnapshot>, isWatched: (code: string) => boolean) {
  const candidates = items.map(item => {
    const previous = snapshot[dashboardSnapshotKey(item)]
    const movement = candidateMovement(item, previous)
    const watched = isWatched(item.symbol.code)

    return {
      item,
      movement,
      watched,
      score: dashboardPriorityScore(item, movement, watched),
    }
  })

  const sortByScore = (left: FocusCandidate, right: FocusCandidate) => right.score - left.score
  const priority = candidates
    .filter(candidate => !candidate.item.no_signal_flag && candidate.item.action_plan === 'ready_now')
    .sort(sortByScore)
    .slice(0, 3)
  const usedKeys = new Set(priority.map(candidate => dashboardSnapshotKey(candidate.item)))
  const recheck = candidates
    .filter(candidate => !usedKeys.has(dashboardSnapshotKey(candidate.item)) && !candidate.item.no_signal_flag && candidate.item.action_plan !== 'ready_now')
    .sort(sortByScore)
    .slice(0, 3)

  for (const candidate of recheck) usedKeys.add(dashboardSnapshotKey(candidate.item))

  const hold = candidates
    .filter(candidate => !usedKeys.has(dashboardSnapshotKey(candidate.item)) && (candidate.item.no_signal_flag || candidate.item.action_plan === 'recheck' || candidate.movement === 'weakening'))
    .sort(sortByScore)
    .slice(0, 3)

  return {
    priority,
    recheck,
    hold,
    movementCounts: {
      new: candidates.filter(candidate => candidate.movement === 'new').length,
      steady: candidates.filter(candidate => candidate.movement === 'steady').length,
      weakening: candidates.filter(candidate => candidate.movement === 'weakening').length,
    },
  }
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

export function buildRoutineDeck(focusDeck: ReturnType<typeof buildFocusDeck>, items: DashboardItem[], isWatched: (code: string) => boolean): RoutineDeck {
  const byScore = [...items].sort((left, right) => dashboardPriorityScore(right, 'steady', isWatched(right.symbol.code)) - dashboardPriorityScore(left, 'steady', isWatched(left.symbol.code)))
  const premarket = uniqueItems([...focusDeck.priority.map(candidate => candidate.item), ...focusDeck.recheck.map(candidate => candidate.item), ...byScore]).slice(0, 5)
  const intraday = uniqueItems([
    ...items.filter(item => item.live_intraday_candidate),
    ...focusDeck.priority.map(candidate => candidate.item),
    ...items.filter(item => !item.no_signal_flag && ['ready_now', 'watch'].includes(item.action_plan)),
    ...byScore,
  ]).slice(0, 5)
  const afterMarket = uniqueItems([
    ...focusDeck.hold.map(candidate => candidate.item),
    ...items.filter(item => item.no_signal_flag || item.action_plan === 'recheck' || item.risk_flags.length > 0),
    ...items.filter(item => item.freshness_score < 0.35),
  ])
    .sort((left, right) => afterMarketPriority(right) - afterMarketPriority(left))
    .slice(0, 5)

  return { premarket, intraday, afterMarket }
}

function uniqueItems(items: DashboardItem[]) {
  const seen = new Set<string>()
  const unique: DashboardItem[] = []

  for (const item of items) {
    const key = dashboardSnapshotKey(item)
    if (seen.has(key)) continue
    seen.add(key)
    unique.push(item)
  }

  return unique
}

export function uniqueRoutineSymbols(deck: RoutineDeck) {
  return Array.from(new Set([...deck.premarket, ...deck.intraday, ...deck.afterMarket].map(item => item.symbol.code))).slice(0, 8)
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

export function routineActionText(item: DashboardItem, mode: 'premarket' | 'intraday' | 'afterMarket') {
  if (mode === 'premarket') {
    return item.next_trigger || item.action_plan_summary || '장전에는 가격대와 손절 기준가를 먼저 확인합니다.'
  }
  if (mode === 'intraday') {
    if (item.live_intraday_candidate) return item.live_intraday_reason || item.next_trigger || '현재가가 핵심 가격대에 붙는지 확인합니다.'
    return item.next_trigger || '현재가가 트리거 근처에 오는지 관찰합니다.'
  }
  if (item.no_signal_flag) return item.reason_summary || '신호가 약하므로 내일 후보에서 제외할지 확인합니다.'
  if (item.risk_flags.length > 0) return item.risk_flags[0]
  if (item.action_plan === 'recheck') return '손절 기준가 이탈 또는 재확인이 필요한지 장후에 정리합니다.'
  return '오늘 판단을 기록하고 다음 스캔에서 유지 여부를 확인합니다.'
}
