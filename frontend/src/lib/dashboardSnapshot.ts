import type { DashboardItem, Timeframe } from '@/types/api'

/**
 * Dashboard candidate snapshot + movement classification.
 *
 * The dashboard remembers each candidate's priority between visits (in
 * localStorage) so it can flag whether a setup is newly appearing, holding
 * steady, or weakening. Extracted from DashboardPage to keep that page focused
 * on rendering.
 */

export type CandidateMovement = 'new' | 'steady' | 'weakening'

export interface CandidateSnapshot {
  score: number
  actionPlan: string
  noSignal: boolean
  updatedAt: string
}

const DASHBOARD_SNAPSHOT_PREFIX = 'stock-chart-helper:dashboard-snapshot:v1'

export function dashboardSnapshotKey(item: DashboardItem) {
  return `${item.timeframe}:${item.symbol.code}`
}

export function dashboardPriorityScore(item: DashboardItem, movement: CandidateMovement, watched: boolean) {
  const base =
    (item.action_priority_score ?? 0) * 0.28 +
    (item.trade_readiness_score ?? 0) * 0.24 +
    (item.entry_window_score ?? 0) * 0.18 +
    (item.freshness_score ?? 0) * 0.12 +
    (item.historical_edge_score ?? 0) * 0.08 +
    (item.data_quality ?? 0) * 0.06 +
    (item.confluence_score ?? 0) * 0.04

  const movementBonus = movement === 'new' ? 0.12 : movement === 'weakening' ? -0.12 : 0
  const watchBonus = watched ? 0.08 : 0
  const penalty = item.no_signal_flag ? 0.18 : item.action_plan === 'recheck' ? 0.08 : 0

  return base + movementBonus + watchBonus - penalty
}

export function candidateMovement(item: DashboardItem, previous: CandidateSnapshot | undefined): CandidateMovement {
  if (!previous) return 'new'

  const currentScore = item.action_priority_score ?? item.trade_readiness_score ?? 0
  if (item.no_signal_flag || item.action_plan === 'recheck') return 'weakening'
  if (currentScore < previous.score - 0.08) return 'weakening'
  return 'steady'
}

export function readDashboardSnapshot(timeframe: Timeframe): Record<string, CandidateSnapshot> {
  if (typeof window === 'undefined') return {}

  try {
    const raw = window.localStorage.getItem(`${DASHBOARD_SNAPSHOT_PREFIX}:${timeframe}`)
    if (!raw) return {}
    return JSON.parse(raw) as Record<string, CandidateSnapshot>
  } catch {
    return {}
  }
}

export function writeDashboardSnapshot(timeframe: Timeframe, items: DashboardItem[], updatedAt?: string) {
  if (typeof window === 'undefined') return

  const snapshot = items.reduce<Record<string, CandidateSnapshot>>((acc, item) => {
    acc[dashboardSnapshotKey(item)] = {
      score: item.action_priority_score ?? item.trade_readiness_score ?? 0,
      actionPlan: item.action_plan,
      noSignal: item.no_signal_flag,
      updatedAt: updatedAt ?? new Date().toISOString(),
    }
    return acc
  }, {})

  try {
    window.localStorage.setItem(`${DASHBOARD_SNAPSHOT_PREFIX}:${timeframe}`, JSON.stringify(snapshot))
  } catch {
    // Local storage is a convenience only; the dashboard should still render without it.
  }
}
