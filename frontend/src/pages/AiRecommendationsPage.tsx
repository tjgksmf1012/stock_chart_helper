import { useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { AlertTriangle, BarChart2, Loader2, RefreshCw, ShieldCheck, Sparkles, Target } from 'lucide-react'

import { Card } from '@/components/ui/Card'
import { aiApi } from '@/lib/api'
import { DEFAULT_TIMEFRAME, TIMEFRAME_OPTIONS } from '@/lib/timeframes'
import { cn, fmtDateTime, fmtPct, PATTERN_NAMES } from '@/lib/utils'
import { useAppStore } from '@/store/app'
import type { AiRecommendationItem } from '@/types/api'

const STANCE_STYLES: Record<AiRecommendationItem['stance'], string> = {
  priority_watch: 'border-emerald-500/30 bg-emerald-500/10 text-emerald-200',
  wait_for_trigger: 'border-sky-500/30 bg-sky-500/10 text-sky-200',
  avoid_chase: 'border-amber-500/30 bg-amber-500/10 text-amber-200',
  risk_review: 'border-red-500/30 bg-red-500/10 text-red-200',
}

export default function AiRecommendationsPage() {
  const nav = useNavigate()
  const { selectedTimeframe, setTimeframe } = useAppStore()
  const timeframe = selectedTimeframe ?? DEFAULT_TIMEFRAME

  const recommendationsQ = useQuery({
    queryKey: ['ai-recommendations', timeframe],
    queryFn: () => aiApi.recommendations(timeframe, 10),
    staleTime: 30_000,
    refetchInterval: 90_000,
  })

  const data = recommendationsQ.data
  const topItems = useMemo(() => data?.items.slice(0, 4) ?? [], [data?.items])
  const llmBadge = useMemo(() => buildLlmBadge(data), [data])

  return (
    <div className="space-y-8">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <div className="flex items-center gap-2 text-xl font-bold">
            <Sparkles size={20} className="text-primary" />
            AI 추천
          </div>
          <p className="mt-1 max-w-3xl text-xs leading-relaxed text-muted-foreground">
            패턴 점수, 거래 준비도, 데이터 품질, 손익비, 리스크 플래그를 합쳐 오늘 먼저 볼 후보와 기다릴 후보를 나눕니다.
          </p>
        </div>

        <div className="flex flex-wrap gap-1">
          {TIMEFRAME_OPTIONS.map(option => (
            <button
              key={option.value}
              onClick={() => setTimeframe(option.value)}
              className={cn(
                'rounded-md px-2.5 py-1.5 text-xs transition-colors',
                timeframe === option.value
                  ? 'bg-primary text-primary-foreground'
                  : 'border border-border bg-card text-muted-foreground hover:text-foreground',
              )}
            >
              {option.label}
            </button>
          ))}
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-[1.2fr_0.8fr]">
        <Card className="space-y-4 border-primary/20 bg-primary/5">
          <div className="flex items-center justify-between gap-3">
            <div className="flex items-center gap-2 text-sm font-semibold">
              <ShieldCheck size={16} className="text-primary" />
              오늘의 운용 브리핑
            </div>
            <button
              onClick={() => recommendationsQ.refetch()}
              className="inline-flex items-center gap-1.5 text-xs text-muted-foreground transition-colors hover:text-foreground"
            >
              <RefreshCw size={13} className={recommendationsQ.isFetching ? 'animate-spin' : ''} />
              새로고침
            </button>
          </div>

          {recommendationsQ.isLoading ? (
            <div className="flex min-h-36 items-center justify-center text-sm text-muted-foreground">
              <Loader2 size={16} className="mr-2 animate-spin" />
              추천 후보 계산 중
            </div>
          ) : recommendationsQ.isError ? (
            <div className="rounded-lg border border-red-500/20 bg-red-500/5 p-4 text-sm text-red-100">
              AI 추천 데이터를 불러오지 못했습니다. 잠시 후 다시 시도하세요.
            </div>
          ) : (
            <>
              {llmBadge && (
                <div className={cn('rounded-lg border px-3 py-2 text-xs leading-relaxed', llmBadge.className)}>
                  {llmBadge.text}
                </div>
              )}
              <p className="text-sm leading-relaxed text-foreground">{data?.market_brief}</p>
              <p className="text-sm leading-relaxed text-muted-foreground">{data?.portfolio_guidance}</p>

              <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
                <Metric label="우선 검토" value={`${data?.priority_items.length ?? 0}개`} />
                <Metric label="대기 후보" value={`${data?.watch_items.length ?? 0}개`} />
                <Metric label="리스크 점검" value={`${data?.risk_items.length ?? 0}개`} />
                <Metric label="업데이트" value={fmtDateTime(data?.generated_at)} />
              </div>
            </>
          )}
        </Card>

        <Card className="space-y-3">
          <div className="flex items-center gap-2 text-sm font-semibold">
            <Target size={16} className="text-emerald-300" />
            상위 후보 빠른 보기
          </div>
          <div className="space-y-2">
            {topItems.length === 0 && !recommendationsQ.isLoading ? (
              <div className="rounded-lg border border-border bg-background/60 p-3 text-xs text-muted-foreground">
                아직 표시할 후보가 없습니다.
              </div>
            ) : (
              topItems.map(item => (
                <button
                  key={`${item.symbol.code}-${item.stance}`}
                  onClick={() => nav(item.chart_path)}
                  className="flex w-full items-center justify-between gap-3 rounded-lg border border-border bg-background/60 p-3 text-left transition-colors hover:border-primary/40"
                >
                  <div>
                    <div className="text-sm font-semibold">{item.symbol.name}</div>
                    <div className="text-xs text-muted-foreground">{item.symbol.code}</div>
                  </div>
                  <div className="text-right">
                    <div className="text-sm font-bold text-primary">{Math.round(item.score)}점</div>
                    <div className="text-xs text-muted-foreground">{item.stance_label}</div>
                  </div>
                </button>
              ))
            )}
          </div>
        </Card>
      </div>

      <RecommendationBand
        title="우선 검토"
        icon={<Sparkles size={16} className="text-emerald-300" />}
        items={data?.priority_items ?? []}
        loading={recommendationsQ.isLoading}
        empty="지금은 강한 우선 후보가 없습니다."
      />

      <RecommendationBand
        title="트리거 대기"
        icon={<BarChart2 size={16} className="text-sky-300" />}
        items={data?.watch_items ?? []}
        loading={recommendationsQ.isLoading}
        empty="트리거를 기다릴 후보가 없습니다."
      />

      <RecommendationBand
        title="리스크 / 관망"
        icon={<AlertTriangle size={16} className="text-amber-300" />}
        items={data?.risk_items ?? []}
        loading={recommendationsQ.isLoading}
        empty="리스크 점검 후보가 없습니다."
      />

      {data?.disclaimer && (
        <div className="rounded-lg border border-border bg-card px-4 py-3 text-xs leading-relaxed text-muted-foreground">
          {data.disclaimer}
        </div>
      )}
    </div>
  )
}

function buildLlmBadge(data: { llm_enabled?: boolean; llm_status?: string; llm_cached_at?: string | null; llm_error?: string | null } | undefined) {
  if (!data) return null

  if (data.llm_enabled && data.llm_status === 'cached_refreshing') {
    return {
      className: 'border-cyan-500/20 bg-cyan-500/5 text-cyan-100',
      text: `최근 OpenAI 코멘트를 보여주는 중입니다. 백그라운드에서 새 코멘트를 다시 생성하고 있어요.${data.llm_cached_at ? ` 마지막 AI 갱신 ${fmtDateTime(data.llm_cached_at)}.` : ''}`,
    }
  }

  if (data.llm_enabled) {
    return {
      className: 'border-emerald-500/20 bg-emerald-500/5 text-emerald-100',
      text: `OpenAI 코멘트가 적용된 상태입니다.${data.llm_cached_at ? ` 마지막 AI 갱신 ${fmtDateTime(data.llm_cached_at)}.` : ''}`,
    }
  }

  if (data.llm_status === 'refreshing') {
    return {
      className: 'border-sky-500/20 bg-sky-500/5 text-sky-100',
      text: '지금은 규칙 기반 코멘트를 먼저 보여주고 있습니다. OpenAI 해설은 백그라운드에서 생성 중이며, 다음 새로고침 때 자동 반영됩니다.',
    }
  }

  if (data.llm_error) {
    return {
      className: 'border-amber-500/20 bg-amber-500/5 text-amber-100',
      text: `OpenAI 해설이 바로 붙지 않아 규칙 기반 코멘트로 표시 중입니다. 최근 상태: ${data.llm_error}.`,
    }
  }

  return {
    className: 'border-border bg-background/60 text-muted-foreground',
    text: '현재는 규칙 기반 코멘트를 표시 중입니다.',
  }
}

function RecommendationBand({
  title,
  icon,
  items,
  loading,
  empty,
}: {
  title: string
  icon: React.ReactNode
  items: AiRecommendationItem[]
  loading: boolean
  empty: string
}) {
  return (
    <section className="space-y-3">
      <div className="flex items-center gap-2 text-sm font-semibold">
        {icon}
        {title}
      </div>

      {loading ? (
        <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
          {[0, 1].map(index => (
            <Card key={index} className="min-h-56 animate-pulse bg-card/70">
              <div />
            </Card>
          ))}
        </div>
      ) : items.length === 0 ? (
        <div className="rounded-lg border border-border bg-card p-4 text-sm text-muted-foreground">{empty}</div>
      ) : (
        <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
          {items.map(item => (
            <RecommendationCard key={`${item.symbol.code}-${item.rank}-${item.stance}`} item={item} />
          ))}
        </div>
      )}
    </section>
  )
}

function RecommendationCard({ item }: { item: AiRecommendationItem }) {
  const nav = useNavigate()
  const patternName = item.pattern_type ? PATTERN_NAMES[item.pattern_type] ?? item.pattern_type : '패턴 없음'

  return (
    <Card className="space-y-4" onClick={() => nav(item.chart_path)}>
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <div className="flex items-center gap-2">
            <span className="text-xs text-muted-foreground">#{item.rank}</span>
            <h2 className="text-lg font-bold">{item.symbol.name}</h2>
            <span className="text-xs text-muted-foreground">{item.symbol.code}</span>
          </div>
          <div className="mt-1 text-xs text-muted-foreground">
            {patternName} · {item.timeframe_label} · {item.state ?? 'scan'}
          </div>
        </div>

        <div className="flex items-center gap-2">
          <span className={cn('rounded-md border px-2 py-1 text-xs font-medium', STANCE_STYLES[item.stance])}>
            {item.stance_label}
          </span>
          <span className="rounded-md border border-primary/30 bg-primary/10 px-2 py-1 text-xs font-bold text-primary">
            {Math.round(item.score)}점
          </span>
        </div>
      </div>

      <p className="text-sm leading-relaxed text-foreground">{item.summary}</p>

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Metric label="상승확률" value={fmtPct(item.p_up)} />
        <Metric label="신뢰도" value={fmtPct(item.confidence)} />
        <Metric label="진입구간" value={fmtPct(item.entry_window_score, 0)} />
        <Metric label="손익비" value={item.reward_risk_ratio.toFixed(2)} />
      </div>

      <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
        <InfoList title="판단 근거" items={item.reasons} />
        <InfoList title="다음 확인" items={item.next_actions} />
      </div>

      {item.risk_flags.length > 0 && (
        <div className="rounded-lg border border-amber-500/20 bg-amber-500/5 p-3">
          <div className="mb-2 text-xs font-semibold text-amber-200">리스크</div>
          <div className="flex flex-wrap gap-1.5">
            {item.risk_flags.map(flag => (
              <span key={flag} className="rounded-md bg-amber-500/10 px-2 py-1 text-xs text-amber-100">
                {flag}
              </span>
            ))}
          </div>
        </div>
      )}

      <div className="rounded-lg border border-border bg-background/60 p-3 text-xs leading-relaxed text-muted-foreground">
        {item.position_hint}
      </div>
    </Card>
  )
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-border bg-background/60 p-3">
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className="mt-1 text-sm font-semibold">{value}</div>
    </div>
  )
}

function InfoList({ title, items }: { title: string; items: string[] }) {
  return (
    <div className="rounded-lg border border-border bg-background/60 p-3">
      <div className="mb-2 text-xs font-semibold text-muted-foreground">{title}</div>
      <ul className="space-y-1.5 text-xs leading-relaxed text-foreground">
        {items.slice(0, 4).map(item => (
          <li key={item}>{item}</li>
        ))}
      </ul>
    </div>
  )
}
