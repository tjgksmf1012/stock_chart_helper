import type { OutcomesSummary } from '@/types/api'

/**
 * 내 판단 기록 요약 헬퍼 — 성과판(기록 탭)에서 사용.
 * (대시보드 히어로 지표 요약(buildDashboardSummary 등)은 3탭 재편에서 제거 — git 이력에 있음.)
 */

export function bestPersonalPattern(summary: OutcomesSummary | undefined) {
  if (!summary?.by_pattern) return null
  const entries = Object.entries(summary.by_pattern)
    .filter(([, stats]) => stats.total > 0)
    .sort((left, right) => {
      const [, leftStats] = left
      const [, rightStats] = right
      return rightStats.win_rate - leftStats.win_rate || rightStats.total - leftStats.total
    })
  const best = entries[0]
  if (!best) return null
  return { pattern: best[0], winRate: best[1].win_rate, total: best[1].total }
}

export function bestPersonalIntents(summary: OutcomesSummary | undefined) {
  if (!summary?.by_intent) return []

  const labels: Record<string, string> = {
    observe: '관망',
    breakout_wait: '돌파 대기',
    pullback_candidate: '눌림 매수',
    invalidation_watch: '손절 구간 감시',
  }

  return Object.entries(summary.by_intent)
    .filter(([, stats]) => stats.total > 0)
    .sort((left, right) => {
      const [, leftStats] = left
      const [, rightStats] = right
      return rightStats.total - leftStats.total || rightStats.win_rate - leftStats.win_rate
    })
    .slice(0, 4)
    .map(([key, stats]) => ({
      key,
      label: labels[key] ?? key,
      total: stats.total,
      winRate: stats.win_rate,
    }))
}
