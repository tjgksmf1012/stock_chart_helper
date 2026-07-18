import type { OutlookHorizon } from '@/types/api'

/**
 * 패턴 확률(단기·조건부)과 전망 구간(무조건부 종목 체질)의 충돌 감지.
 * 롱 온리 앱에서 위험한 방향은 "패턴은 위, 체질은 아래" 하나다 —
 * 예: 한샘(009240) 상승확률 65% vs 1개월 중앙값 −1.1%.
 */
const P_UP_THRESHOLD = 0.58

export interface OutlookConflict {
  conflict: boolean
  medianPct: number | null
}

export function detectOutlookConflict(
  pUp: number | null | undefined,
  horizons: OutlookHorizon[],
): OutlookConflict {
  if (pUp == null || pUp < P_UP_THRESHOLD) return { conflict: false, medianPct: null }
  // 체질 판정 기준: 1개월(20일), 없으면 1주(5일)
  const basis =
    horizons.find(h => h.horizon_days === 20) ?? horizons.find(h => h.horizon_days === 5)
  if (!basis) return { conflict: false, medianPct: null }
  return { conflict: basis.q50 < 0, medianPct: basis.q50 }
}
