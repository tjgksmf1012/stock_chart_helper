import type { LabEligibleStrategy, LabSignal } from '@/types/api'

/**
 * 오늘의 최우선 진입 후보 — 검증 통과(pass) 신호 중 전략 EV가 가장 높은 것.
 * 관찰(watch) 등급은 최우선으로 지목하지 않는다: "오늘의 추천"이라는 이름은
 * 검증을 온전히 통과한 신호에만 붙인다. 랭킹 기준은 상승확률이 아니라
 * 워크포워드 검증 기대값(EV)이다 — 돈이 되는 순서는 확률 순이 아니라 기대값 순.
 */
export function pickTopSignal(
  signals: LabSignal[],
  eligible: LabEligibleStrategy[],
): LabSignal | null {
  const evById = new Map(eligible.map(e => [e.strategy_id, e.ev_pct ?? 0]))
  const candidates = signals.filter(s => s.verdict === 'pass')
  if (candidates.length === 0) return null
  const ranked = [...candidates].sort((a, b) => {
    const evDiff = (evById.get(b.strategy_id) ?? 0) - (evById.get(a.strategy_id) ?? 0)
    if (evDiff !== 0) return evDiff
    if (a.signal_date !== b.signal_date) return b.signal_date.localeCompare(a.signal_date)
    return a.code.localeCompare(b.code)
  })
  return ranked[0]
}
