import { useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import { useMutation, useQuery } from '@tanstack/react-query'
import { NotebookPen } from 'lucide-react'

import { PendingDecisions } from '@/components/journal/PendingDecisions'
import { PerformanceSummary } from '@/components/journal/PerformanceSummary'
import { QueryError } from '@/components/ui/QueryError'
import { outcomesApi } from '@/lib/api'
import type { OutcomeStatus } from '@/types/api'

/** 기록 > 내 기록 — 저장한 판단의 미정리 목록과 성과판. 타임프레임 구분 없이 전체를 보여준다. */
export default function JournalRecordsPage() {
  const nav = useNavigate()
  const outcomesQ = useQuery({ queryKey: ['outcomes', 'journal'], queryFn: outcomesApi.list, staleTime: 60_000 })
  const summaryQ = useQuery({ queryKey: ['outcomes', 'summary', 'journal'], queryFn: outcomesApi.summary, staleTime: 60_000 })

  const updateMutation = useMutation({
    mutationFn: ({ id, outcome }: { id: number; outcome: OutcomeStatus }) =>
      outcomesApi.update(id, { outcome, exit_date: new Date().toISOString().slice(0, 10) }),
    onSuccess: () => {
      outcomesQ.refetch()
      summaryQ.refetch()
    },
  })
  const evaluateMutation = useMutation({
    mutationFn: outcomesApi.evaluatePending,
    onSuccess: () => {
      outcomesQ.refetch()
      summaryQ.refetch()
    },
  })

  const pendingRecords = useMemo(
    () => (outcomesQ.data ?? []).filter(record => record.outcome === 'pending'),
    [outcomesQ.data],
  )

  return (
    <div className="space-y-6">
      <div>
        <div className="flex items-center gap-2 text-xl font-bold">
          <NotebookPen size={20} className="text-primary" />
          내 기록
        </div>
        <p className="mt-1 max-w-3xl text-sm leading-relaxed text-muted-foreground">
          차트에서 저장한 판단을 여기서 닫습니다. 닫힌 기록이 쌓일수록 내 승률과 강한 패턴이 데이터로 보입니다.
        </p>
      </div>

      {outcomesQ.isError && <QueryError message="판단 기록을 불러오지 못했습니다." onRetry={() => outcomesQ.refetch()} />}

      <PendingDecisions
        records={pendingRecords}
        isLoading={outcomesQ.isLoading}
        isUpdating={updateMutation.isPending}
        isEvaluating={evaluateMutation.isPending}
        evaluationResult={evaluateMutation.data}
        onOpen={code => nav(`/chart/${code}`)}
        onUpdate={(id, outcome) => updateMutation.mutate({ id, outcome })}
        onEvaluate={() => evaluateMutation.mutate()}
      />

      <PerformanceSummary summary={summaryQ.data} isLoading={summaryQ.isLoading} />
    </div>
  )
}
