import { useEffect, useState } from 'react'
import { Loader2, RefreshCw } from 'lucide-react'

import { cn, fmtPrice, PATTERN_NAMES } from '@/lib/utils'
import type { OutcomeEvaluationResponse, OutcomeRecord, OutcomeStatus } from '@/types/api'

const PENDING_OUTCOME_LABELS: Record<OutcomeStatus, string> = {
  pending: '대기',
  win: '성공',
  loss: '실패',
  stopped_out: '손절',
  cancelled: '취소',
}

const PENDING_OUTCOME_TONES: Record<OutcomeStatus, string> = {
  pending: 'border-sky-400/25 bg-sky-400/10 text-sky-100',
  win: 'border-emerald-400/25 bg-emerald-400/10 text-emerald-100',
  loss: 'border-red-400/25 bg-red-400/10 text-red-100',
  stopped_out: 'border-amber-400/25 bg-amber-400/10 text-amber-100',
  cancelled: 'border-border bg-background/70 text-muted-foreground',
}

export function PendingDecisions({
  records,
  isLoading,
  isUpdating,
  isEvaluating,
  evaluationResult,
  onOpen,
  onUpdate,
  onEvaluate,
}: {
  records: OutcomeRecord[]
  isLoading: boolean
  isUpdating: boolean
  isEvaluating: boolean
  evaluationResult: OutcomeEvaluationResponse | undefined
  onOpen: (code: string) => void
  onUpdate: (id: number, outcome: OutcomeStatus) => void
  onEvaluate: () => void
}) {
  // 원클릭 오확정 방지 — 첫 클릭은 확정 대기 상태로만 만들고, 같은 버튼을 한 번 더
  // 눌러야 실제로 닫는다 (몇 초 지나면 자동 해제).
  const [confirming, setConfirming] = useState<{ id: number; outcome: OutcomeStatus } | null>(null)

  useEffect(() => {
    if (!confirming) return
    const timer = window.setTimeout(() => setConfirming(null), 4000)
    return () => window.clearTimeout(timer)
  }, [confirming])

  const handleOutcomeClick = (id: number, outcome: OutcomeStatus) => {
    if (confirming && confirming.id === id && confirming.outcome === outcome) {
      setConfirming(null)
      onUpdate(id, outcome)
      return
    }
    setConfirming({ id, outcome })
  }

  if (isLoading || records.length === 0) {
    return (
      <section className="rounded-lg border border-border bg-card/55 p-4">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <div className="text-sm font-semibold">미정리 판단</div>
            <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
              {isLoading ? '저장한 판단 기록을 확인하는 중입니다.' : '현재 닫아야 할 대기 기록이 없습니다.'}
            </p>
            {evaluationResult && !isLoading && (
              <p className="mt-2 text-xs text-muted-foreground">
                마지막 자동 점검: {evaluationResult.checked}건 확인, {evaluationResult.updated}건 정리
              </p>
            )}
          </div>
          {isLoading ? (
            <Loader2 size={14} className="animate-spin text-muted-foreground" />
          ) : (
            <button
              onClick={onEvaluate}
              disabled={isEvaluating}
              className="inline-flex items-center justify-center gap-2 rounded-lg border border-border bg-background/60 px-3 py-2 text-xs text-muted-foreground transition-colors hover:text-foreground disabled:cursor-not-allowed disabled:opacity-60"
            >
              {isEvaluating ? <Loader2 size={13} className="animate-spin" /> : <RefreshCw size={13} />}
              자동 점검
            </button>
          )}
        </div>
      </section>
    )
  }

  return (
    <section className="space-y-3 rounded-lg border border-amber-400/20 bg-amber-400/10 p-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <div className="text-sm font-semibold">미정리 판단</div>
          <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
            저장해둔 시나리오는 성공, 실패, 손절, 취소 중 하나로 닫아야 내 성과 데이터가 쌓입니다.
          </p>
          {evaluationResult && (
            <p className="mt-2 text-xs text-amber-100">
              자동 점검: {evaluationResult.checked}건 확인, {evaluationResult.updated}건 정리, {evaluationResult.skipped}건 보류
            </p>
          )}
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            onClick={onEvaluate}
            disabled={isEvaluating}
            className="inline-flex items-center justify-center gap-2 rounded-lg border border-amber-400/25 bg-amber-400/10 px-3 py-2 text-xs text-amber-100 transition-colors hover:bg-amber-400/15 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {isEvaluating ? <Loader2 size={13} className="animate-spin" /> : <RefreshCw size={13} />}
            현재가로 자동 점검
          </button>
          <span className="rounded-md border border-amber-400/25 bg-amber-400/10 px-2 py-2 text-xs text-amber-100">
            대기 {records.length}건
          </span>
        </div>
      </div>

      <div className="grid gap-2 xl:grid-cols-2">
        {records.map(record => (
          <div key={record.id ?? `${record.symbol_code}-${record.signal_date}`} className="rounded-lg border border-border bg-background/60 p-3">
            <div className="flex flex-wrap items-start justify-between gap-2">
              <button onClick={() => onOpen(record.symbol_code)} className="min-w-0 text-left">
                <div className="flex flex-wrap items-center gap-1.5">
                  <span className="text-sm font-semibold text-foreground">{record.symbol_name}</span>
                  <span className="font-mono text-[11px] text-muted-foreground">{record.symbol_code}</span>
                  <span className={cn('rounded-md border px-1.5 py-0.5 text-[11px]', PENDING_OUTCOME_TONES.pending)}>
                    {PENDING_OUTCOME_LABELS.pending}
                  </span>
                </div>
                <div className="mt-1 flex flex-wrap gap-3 text-[11px] text-muted-foreground">
                  <span>{PATTERN_NAMES[record.pattern_type] ?? record.pattern_type}</span>
                  <span>{record.signal_date}</span>
                  <span>진입 {record.entry_price > 0 ? fmtPrice(record.entry_price) : '-'}</span>
                </div>
              </button>

              {record.id != null && (
                <div className="flex shrink-0 flex-wrap justify-end gap-1">
                  {(['win', 'loss', 'stopped_out', 'cancelled'] as OutcomeStatus[]).map(outcome => {
                    const isArmed = confirming?.id === record.id && confirming?.outcome === outcome
                    return (
                      <button
                        key={outcome}
                        onClick={() => handleOutcomeClick(record.id!, outcome)}
                        disabled={isUpdating}
                        className={cn(
                          'rounded-md border px-2 py-1 text-[11px] transition-colors disabled:cursor-not-allowed disabled:opacity-50',
                          PENDING_OUTCOME_TONES[outcome],
                          isArmed && 'ring-1 ring-inset ring-current font-semibold',
                        )}
                      >
                        {isArmed ? `${PENDING_OUTCOME_LABELS[outcome]} 확정?` : PENDING_OUTCOME_LABELS[outcome]}
                      </button>
                    )
                  })}
                </div>
              )}
            </div>
          </div>
        ))}
      </div>
    </section>
  )
}
