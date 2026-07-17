import { useMemo } from 'react'
import { Loader2 } from 'lucide-react'

import { Badge } from '@/components/ui/Badge'
import { bestPersonalIntents, bestPersonalPattern } from '@/lib/dashboardSummary'
import { cn, fmtPct, PATTERN_NAMES } from '@/lib/utils'
import type { OutcomesSummary } from '@/types/api'

/** 내 판단 기록의 성과판 — 기록 탭에서는 항상 펼쳐서 보여준다 (대시보드 시절엔 접힘이었음). */
export function PerformanceSummary({ summary, isLoading }: { summary: OutcomesSummary | undefined; isLoading: boolean }) {
  const bestPattern = useMemo(() => bestPersonalPattern(summary), [summary])
  const topIntents = useMemo(() => bestPersonalIntents(summary), [summary])
  const styleProfile = summary?.style_profile
  const total = summary?.total_records ?? 0
  const completed = summary?.completed ?? 0
  const pending = summary?.pending ?? 0
  const cancelled = summary?.cancelled ?? 0

  return (
    <section className="rounded-lg border border-border bg-card/55 p-4">
      <div className="flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <div className="flex items-center gap-2 text-sm font-semibold">
            내 성과 요약
            <Badge variant="muted">{total}건</Badge>
          </div>
          <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
            판단을 저장하고 결과를 닫을수록 이 영역이 내 스타일을 보여주는 성과판이 됩니다.
          </p>
        </div>
        {isLoading && <Loader2 size={14} className="animate-spin text-muted-foreground" />}
      </div>

      {styleProfile && (
        <div className="mt-3 rounded-lg border border-violet-400/20 bg-violet-400/5 p-3">
          <div className="flex flex-wrap items-center gap-2">
            <span className="rounded-md border border-violet-400/30 bg-violet-400/10 px-2 py-1 text-[11px] font-semibold text-violet-100">
              {styleProfile.style_label}
            </span>
            <span className="text-xs text-muted-foreground">
              신뢰도 {fmtPct(styleProfile.confidence ?? 0, 0)} / 종료 기록 {styleProfile.sample_count ?? 0}건
            </span>
          </div>
          <p className="mt-2 text-xs leading-relaxed text-muted-foreground">{styleProfile.summary}</p>
        </div>
      )}

      <div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
        <PerformanceMetric label="전체 기록" value={`${total}건`} />
        <PerformanceMetric label="종료 기록" value={`${completed}건`} />
        <PerformanceMetric label="내 승률" value={completed > 0 ? fmtPct(summary?.win_rate ?? 0, 0) : '-'} tone="text-emerald-300" />
        <PerformanceMetric label="대기 / 취소" value={`${pending} / ${cancelled}`} />
        <PerformanceMetric
          label="강한 패턴"
          value={bestPattern ? `${PATTERN_NAMES[bestPattern.pattern] ?? bestPattern.pattern} ${fmtPct(bestPattern.winRate, 0)}` : '-'}
          tone="text-primary"
        />
      </div>

      {topIntents.length > 0 && (
        <div className="mt-3 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          {topIntents.map(intent => (
            <PerformanceMetric
              key={intent.key}
              label={`${intent.label} 성과`}
              value={`${intent.total}건 / ${fmtPct(intent.winRate, 0)}`}
              tone="text-violet-200"
            />
          ))}
        </div>
      )}

      {total === 0 && !isLoading && (
        <div className="mt-3 rounded-lg border border-border bg-background/60 p-3 text-xs leading-relaxed text-muted-foreground">
          아직 저장된 판단이 없습니다. 차트 화면에서 좋은 셋업을 볼 때 `신호 저장`을 눌러두면, 이후 결과가 자동/수동으로
          정리되고 여기서 내 성과가 쌓입니다.
        </div>
      )}
    </section>
  )
}

function PerformanceMetric({ label, value, tone }: { label: string; value: string; tone?: string }) {
  return (
    <div className="rounded-lg border border-border bg-background/60 p-3">
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className={cn('mt-1 truncate text-sm font-semibold text-foreground', tone)}>{value}</div>
    </div>
  )
}
