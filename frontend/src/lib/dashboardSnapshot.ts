import type { DashboardItem } from '@/types/api'

/**
 * 후보 우선순위 점수 — 후보 레일과 관심종목 알림 덱의 정렬 기준.
 * (스냅샷 비교(신규/유지/약화) 저장 로직은 3탭 재편에서 제거 — git 이력에 있음.)
 */

export type CandidateMovement = 'new' | 'steady' | 'weakening'

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
