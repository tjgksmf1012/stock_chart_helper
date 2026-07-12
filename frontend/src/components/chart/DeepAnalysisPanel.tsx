import { useQuery } from '@tanstack/react-query'
import { Loader2, Microscope } from 'lucide-react'

import { Card } from '@/components/ui/Card'
import { QueryError } from '@/components/ui/QueryError'
import { symbolsApi } from '@/lib/api'
import { cn, fmtPrice, PATTERN_NAMES } from '@/lib/utils'
import type { DeepAnalysisResponse, DeepPatternCase, DeepPatternStat } from '@/types/api'

/**
 * 온디맨드 정밀분석 패널 — 이 종목의 과거 패턴 성적표 + 장기 맥락.
 * [정밀분석] 버튼을 눌렀을 때만 마운트되어 무거운 백엔드 리플레이를 호출한다
 * (서버 12h 캐시, 첫 호출은 수 초~수십 초 소요).
 */

const OUTCOME_LABELS: Record<DeepPatternCase['outcome'], { text: string; cls: string }> = {
  success: { text: '성공', cls: 'text-emerald-300' },
  fail: { text: '실패', cls: 'text-red-300' },
  timeout: { text: '미결', cls: 'text-muted-foreground' },
}

function patternName(type: string): string {
  return PATTERN_NAMES[type] ?? type
}

function pct(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined) return '-'
  return `${(value * 100).toFixed(digits)}%`
}

// 베어리시 패턴은 성공 등락이 음수(하락 도달)라 무조건 '+'를 붙이면 "+-6.3%"가 됨
function signedPct(value: number, digits = 1): string {
  return `${value > 0 ? '+' : ''}${pct(value, digits)}`
}

export function DeepAnalysisPanel({ symbol }: { symbol: string }) {
  const deepQ = useQuery({
    queryKey: ['deep-analysis', symbol],
    queryFn: () => symbolsApi.getDeepAnalysis(symbol),
    staleTime: 1_800_000, // 서버가 12h 캐시하므로 클라이언트는 30분이면 충분
    retry: 0,
  })

  // 분석이 도는 동안만 1초 간격으로 리플레이 진행률 폴링 (서버 캐시 적중 시엔 안 뜸)
  const progressQ = useQuery({
    queryKey: ['deep-analysis-progress', symbol],
    queryFn: () => symbolsApi.getDeepAnalysisProgress(symbol),
    enabled: deepQ.isLoading,
    refetchInterval: deepQ.isLoading ? 1_000 : false,
    retry: 0,
  })
  const progress = progressQ.data
  const progressPct =
    progress?.running && progress.total > 0 ? Math.round((progress.done / progress.total) * 100) : null

  return (
    <Card className="space-y-4 p-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2 text-sm font-semibold">
            <Microscope size={15} className="text-primary" />
            정밀분석 — 이 종목의 과거 패턴 성적표
          </div>
          <p className="mt-1 text-xs text-muted-foreground">
            일봉 약 6년 이력을 리플레이해 같은 패턴이 이 종목에서 실제로 어떻게 끝났는지 계산합니다. 시장 전체 통계가 아니라 이
            종목만의 성적입니다.
          </p>
        </div>
      </div>

      {deepQ.isLoading ? (
        <div className="flex h-36 flex-col items-center justify-center gap-3 text-sm text-muted-foreground">
          <Loader2 size={18} className="animate-spin" />
          <p>
            {progressPct !== null
              ? `과거 이력 리플레이 중 — ${progress!.done} / ${progress!.total} 구간 (${progressPct}%)`
              : '과거 이력을 불러오는 중입니다 (첫 분석은 수십 초 걸릴 수 있어요).'}
          </p>
          <div className="h-1.5 w-full max-w-sm overflow-hidden rounded-full bg-muted/40">
            {progressPct !== null ? (
              <div
                className="h-full rounded-full bg-primary transition-all duration-500"
                style={{ width: `${progressPct}%` }}
              />
            ) : (
              <div className="h-full w-1/3 animate-pulse rounded-full bg-primary/60" />
            )}
          </div>
        </div>
      ) : deepQ.isError ? (
        <QueryError message="정밀분석에 실패했습니다." onRetry={() => deepQ.refetch()} />
      ) : deepQ.data ? (
        <DeepAnalysisBody data={deepQ.data} />
      ) : null}
    </Card>
  )
}

function DeepAnalysisBody({ data }: { data: DeepAnalysisResponse }) {
  const ctx = data.long_context ?? {}

  if (data.note) {
    return <p className="text-sm text-muted-foreground">{data.note}</p>
  }

  return (
    <div className="space-y-4">
      {/* 장기 맥락 */}
      <div className="grid gap-3 sm:grid-cols-3">
        <ContextCell
          label="52주 위치"
          value={ctx.week52_position !== undefined ? pct(ctx.week52_position, 0) : '-'}
          hint={
            ctx.week52_high !== undefined && ctx.week52_low !== undefined
              ? `${fmtPrice(ctx.week52_low)} ~ ${fmtPrice(ctx.week52_high)}`
              : undefined
          }
        />
        <ContextCell
          label="변동성 국면"
          value={ctx.volatility_regime ?? '-'}
          hint={
            ctx.volatility_recent_pct !== undefined
              ? `최근 20일 ${ctx.volatility_recent_pct}% · 1년 ${ctx.volatility_year_pct}%`
              : undefined
          }
        />
        <ContextCell label="리플레이 표본" value={`${data.case_count ?? data.cases.length}건`} hint={`${data.available_bars}봉 이력 기준`} />
      </div>

      {/* 패턴별 성적표 */}
      {data.stats.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          이 종목의 과거 이력에서 결론까지 간 확정 패턴이 발견되지 않았습니다.
        </p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[560px] text-xs">
            <thead>
              <tr className="border-b border-border/70 text-left text-muted-foreground">
                <th className="py-2 pr-3 font-medium">패턴</th>
                <th className="py-2 pr-3 font-medium">표본</th>
                <th className="py-2 pr-3 font-medium">성공/실패/미결</th>
                <th className="py-2 pr-3 font-medium">승률</th>
                <th className="py-2 pr-3 font-medium">평균 기간</th>
                <th className="py-2 pr-3 font-medium">평균 성공 수익</th>
                <th className="py-2 font-medium">평균 실패 손실</th>
              </tr>
            </thead>
            <tbody>
              {data.stats.map((stat: DeepPatternStat) => (
                <tr key={stat.pattern_type} className="border-b border-border/40">
                  <td className="py-2 pr-3 font-medium text-foreground">{patternName(stat.pattern_type)}</td>
                  <td className="py-2 pr-3">{stat.total}건</td>
                  <td className="py-2 pr-3">
                    <span className="text-emerald-300">{stat.wins}</span> /{' '}
                    <span className="text-red-300">{stat.losses}</span> /{' '}
                    <span className="text-muted-foreground">{stat.timeouts}</span>
                  </td>
                  <td className={cn('py-2 pr-3 font-semibold', (stat.win_rate ?? 0) >= 0.5 ? 'text-emerald-300' : 'text-red-300')}>
                    {stat.win_rate !== null ? pct(stat.win_rate, 0) : '-'}
                  </td>
                  <td className="py-2 pr-3">{stat.avg_bars_to_outcome !== null ? `${stat.avg_bars_to_outcome}봉` : '-'}</td>
                  <td className="py-2 pr-3 text-emerald-300">{stat.avg_win_move_pct !== null ? signedPct(stat.avg_win_move_pct) : '-'}</td>
                  <td className="py-2 text-red-300">{stat.avg_loss_move_pct !== null ? signedPct(stat.avg_loss_move_pct) : '-'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* 최근 사례 */}
      {data.cases.length > 0 && (
        <div>
          <div className="mb-1.5 text-xs font-medium text-muted-foreground">최근 사례 (최신순)</div>
          <div className="grid gap-1.5 sm:grid-cols-2">
            {data.cases.slice(0, 8).map((c: DeepPatternCase) => {
              const outcome = OUTCOME_LABELS[c.outcome]
              // pnl_pct는 패턴 방향 반영 손익(숏 성공 = +수익). 구버전 캐시 응답에는
              // 없을 수 있어 move_pct로 폴백한다.
              const pnl = c.pnl_pct ?? c.move_pct
              return (
                <div
                  key={`${c.pattern_type}-${c.signal_date}`}
                  className="flex items-center justify-between gap-2 rounded-lg border border-border/50 bg-background/40 px-3 py-2 text-xs"
                >
                  <span className="font-mono text-muted-foreground">{c.signal_date}</span>
                  <span className="min-w-0 flex-1 truncate">
                    {patternName(c.pattern_type)}
                    {c.direction === 'short' && <span className="ml-1 text-[10px] text-muted-foreground">(숏)</span>}
                  </span>
                  <span className={cn('font-semibold', outcome.cls)}>{outcome.text}</span>
                  <span className={cn('font-mono', pnl >= 0 ? 'text-emerald-300' : 'text-red-300')}>
                    {pnl >= 0 ? '+' : ''}
                    {pct(pnl)}
                  </span>
                  <span className="text-muted-foreground">{c.bars_to_outcome !== null ? `${c.bars_to_outcome}봉` : '-'}</span>
                </div>
              )
            })}
          </div>
        </div>
      )}

      <p className="text-[11px] leading-relaxed text-muted-foreground/80">
        수익률은 패턴 방향 기준입니다 — 하락 패턴(숏)은 가격이 내려간 만큼이 +수익으로 집계됩니다. 과거 성적은 미래를 보장하지
        않습니다. 같은 패턴이라도 시장 국면·수급에 따라 결과가 달라질 수 있으니 현재 분석과 함께 참고용으로만 사용하세요.
      </p>
    </div>
  )
}

function ContextCell({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="rounded-lg border border-border/50 bg-background/40 px-3 py-2.5">
      <div className="text-[11px] text-muted-foreground">{label}</div>
      <div className="mt-0.5 text-sm font-semibold">{value}</div>
      {hint && <div className="mt-0.5 text-[11px] text-muted-foreground/80">{hint}</div>}
    </div>
  )
}
