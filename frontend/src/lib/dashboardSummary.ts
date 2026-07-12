import type { DashboardResponse, OutcomesSummary } from '@/types/api'

import { dedupeDashboardItems } from './dashboardDecks'
import { INTRADAY_COLLECTION_MODE_LABELS, SETUP_STAGE_LABELS } from './utils'

/**
 * Headline summary + personalization roll-ups for the dashboard. Pure data in,
 * plain objects out — no React, so it can be unit-tested directly.
 */

export function buildDashboardSummary(sections: Array<DashboardResponse | undefined>) {
  const items = dedupeDashboardItems(sections)
  if (items.length === 0) {
    return {
      totalCount: 0,
      readyCount: 0,
      watchCount: 0,
      riskCount: 0,
      avgUp: 0,
      avgReadiness: 0,
      avgQuality: 0,
      bestAction: '후보가 준비되면 이 영역이 채워집니다.',
    }
  }

  const readyCount = items.filter(item => item.action_plan === 'ready_now').length
  const watchCount = items.filter(item => item.action_plan === 'watch').length
  // 나머지는 전부 관망/점검으로 묶어 ready + watch + risk = total이 되도록 유지
  // (헤드라인 힌트의 산수가 total과 안 맞으면 집계 자체를 의심하게 된다)
  const riskCount = items.length - readyCount - watchCount

  return {
    totalCount: items.length,
    readyCount,
    watchCount,
    riskCount,
    avgUp: average(items.map(item => item.p_up)),
    avgReadiness: average(items.map(item => item.trade_readiness_score ?? 0)),
    avgQuality: average(items.map(item => item.data_quality)),
    bestAction:
      readyCount > 0
        ? `지금 바로 볼 후보 ${readyCount}개가 있습니다.`
        : watchCount > 0
          ? `트리거 확인이 필요한 후보 ${watchCount}개가 중심입니다.`
          : '관망 또는 데이터 보강이 필요한 종목 비중이 높습니다.',
  }
}

export function buildIntradaySummary(sections: Array<DashboardResponse | undefined>) {
  const items = dedupeDashboardItems(sections)
  if (items.length === 0) {
    return null
  }

  const liveCount = items.filter(item => item.live_intraday_candidate).length
  const placeholderCount = items.filter(item => item.fetch_status === 'placeholder_pending').length
  const dominantMode = dominantLabel(items.map(item => item.intraday_collection_mode), value => INTRADAY_COLLECTION_MODE_LABELS[value] ?? value)
  const dominantStage = dominantLabel(items.map(item => item.setup_stage), value => SETUP_STAGE_LABELS[value] ?? value)

  return {
    guidance:
      liveCount > 0
        ? `현재 ${liveCount}개는 live 우선 후보입니다.`
        : placeholderCount === items.length
          ? '지금은 임시 후보가 먼저 표시되고 있습니다.'
          : `${dominantMode} 중심으로 정리되고, 셋업은 ${dominantStage} 비중이 큽니다.`,
  }
}

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

function average(values: number[]) {
  if (values.length === 0) return 0
  return values.reduce((sum, value) => sum + value, 0) / values.length
}

function dominantLabel(values: string[], formatter?: (value: string) => string) {
  if (values.length === 0) return '-'

  const counts = values.reduce<Record<string, number>>((acc, value) => {
    acc[value] = (acc[value] ?? 0) + 1
    return acc
  }, {})

  const winner = Object.entries(counts).sort((left, right) => right[1] - left[1])[0]?.[0]
  if (!winner) return '-'
  return formatter ? formatter(winner) : winner
}
