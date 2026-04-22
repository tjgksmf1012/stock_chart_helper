import { type ReactNode, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import {
  AlertTriangle,
  BarChart2,
  BrainCircuit,
  Loader2,
  RefreshCw,
  ShieldCheck,
  Sparkles,
  Star,
  Target,
} from 'lucide-react'

import { Card } from '@/components/ui/Card'
import { aiApi } from '@/lib/api'
import { TIMEFRAME_OPTIONS, normalizeDisplayTimeframe } from '@/lib/timeframes'
import { cn, fmtDateTime, fmtPct, PATTERN_NAMES } from '@/lib/utils'
import { useAppStore } from '@/store/app'
import type { AiRecommendationItem, PersonalStyleProfile } from '@/types/api'

const STANCE_STYLES: Record<AiRecommendationItem['stance'], string> = {
  priority_watch: 'border-emerald-500/30 bg-emerald-500/10 text-emerald-200',
  wait_for_trigger: 'border-sky-500/30 bg-sky-500/10 text-sky-200',
  avoid_chase: 'border-amber-500/30 bg-amber-500/10 text-amber-200',
  risk_review: 'border-red-500/30 bg-red-500/10 text-red-200',
}

export default function AiRecommendationsPage() {
  const nav = useNavigate()
  const { selectedTimeframe, setTimeframe, isWatched } = useAppStore()
  const timeframe = normalizeDisplayTimeframe(selectedTimeframe)

  const recommendationsQ = useQuery({
    queryKey: ['ai-recommendations', timeframe],
    queryFn: () => aiApi.recommendations(timeframe, 6),
    staleTime: 30_000,
    refetchInterval: 90_000,
  })

  const data = recommendationsQ.data
  const topItems = useMemo(() => sortAiItems(data?.items ?? [], isWatched).slice(0, 4), [data?.items, isWatched])
  const priorityItems = useMemo(() => sortAiItems(data?.priority_items ?? [], isWatched), [data?.priority_items, isWatched])
  const watchItems = useMemo(() => sortAiItems(data?.watch_items ?? [], isWatched), [data?.watch_items, isWatched])
  const riskItems = useMemo(() => sortAiItems(data?.risk_items ?? [], isWatched), [data?.risk_items, isWatched])
  const personalizedItems = useMemo(
    () => sortAiItems(data?.personalized_items ?? [], isWatched).slice(0, 4),
    [data?.personalized_items, isWatched],
  )
  const watchlistFocusItems = useMemo(() => {
    const fromServer = data?.watchlist_focus_items ?? []
    const source = fromServer.length > 0 ? fromServer : data?.items ?? []
    return sortAiItems(source.filter(item => isWatched(item.symbol.code)), isWatched).slice(0, 4)
  }, [data?.items, data?.watchlist_focus_items, isWatched])
  const watchlistTriggerItems = useMemo(
    () => watchlistFocusItems.filter(item => item.stance !== 'risk_review').slice(0, 4),
    [watchlistFocusItems],
  )
  const watchlistRiskItems = useMemo(
    () =>
      watchlistFocusItems
        .filter(item => item.stance === 'risk_review' || item.risk_flags.length > 0)
        .slice(0, 4),
    [watchlistFocusItems],
  )
  const llmBadge = useMemo(() => buildLlmBadge(data), [data])

  return (
    <div className="space-y-8">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <div className="flex items-center gap-2 text-xl font-bold">
            <Sparkles size={20} className="text-primary" />
            AI 추천
          </div>
          <p className="mt-1 max-w-3xl text-sm leading-relaxed text-muted-foreground">
            점수, 준비도, 데이터 품질, 내 과거 성과를 함께 묶어서 오늘 먼저 볼 후보와 기다릴 후보를 나눠서 보여줍니다.
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
              AI 추천 데이터를 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.
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
                <Metric label="트리거 대기" value={`${data?.watch_items.length ?? 0}개`} />
                <Metric label="리스크 점검" value={`${data?.risk_items.length ?? 0}개`} />
                <Metric label="업데이트" value={fmtDateTime(data?.generated_at)} />
              </div>
            </>
          )}
        </Card>

        <div className="space-y-4">
          <QuickEntryCard items={topItems} loading={recommendationsQ.isLoading} onOpen={code => nav(`/chart/${code}`)} />
          <PersonalStyleCard profile={data?.personal_style} loading={recommendationsQ.isLoading} />
        </div>
      </div>

      <RecommendationBand
        title="내 스타일 기준 오늘의 후보"
        icon={<BrainCircuit size={16} className="text-violet-300" />}
        items={personalizedItems}
        loading={recommendationsQ.isLoading}
        empty="아직 내 기록이 충분하지 않거나 오늘 후보 중 개인화 우선순위가 높은 종목이 없습니다."
      />

      <RecommendationBand
        title="내 관심종목 중 트리거 가까운 것"
        icon={<Star size={16} className="text-amber-300" />}
        items={watchlistTriggerItems}
        loading={recommendationsQ.isLoading}
        empty="관심종목 중 오늘 바로 다시 볼 가격대에 가까운 후보가 없습니다."
      />

      <RecommendationBand
        title="내 관심종목 중 무효화 위험"
        icon={<AlertTriangle size={16} className="text-rose-300" />}
        items={watchlistRiskItems}
        loading={recommendationsQ.isLoading}
        empty="관심종목 중 지금 당장 무효화 위험이 크게 올라온 후보는 없습니다."
      />

      <RecommendationBand
        title="우선 검토"
        icon={<Sparkles size={16} className="text-emerald-300" />}
        items={priorityItems}
        loading={recommendationsQ.isLoading}
        empty="지금은 강한 우선 검토 후보가 없습니다."
      />

      <RecommendationBand
        title="트리거 대기"
        icon={<BarChart2 size={16} className="text-sky-300" />}
        items={watchItems}
        loading={recommendationsQ.isLoading}
        empty="트리거를 기다릴 후보가 없습니다."
      />

      <RecommendationBand
        title="리스크 점검 / 관망"
        icon={<AlertTriangle size={16} className="text-amber-300" />}
        items={riskItems}
        loading={recommendationsQ.isLoading}
        empty="지금은 리스크 점검이 필요한 후보가 없습니다."
      />

      {data?.disclaimer && (
        <div className="rounded-lg border border-border bg-card px-4 py-3 text-xs leading-relaxed text-muted-foreground">
          {data.disclaimer}
        </div>
      )}
    </div>
  )
}

function sortAiItems(items: AiRecommendationItem[], isWatched: (code: string) => boolean) {
  return [...items].sort((left, right) => {
    const watchDelta = Number(isWatched(right.symbol.code)) - Number(isWatched(left.symbol.code))
    if (watchDelta !== 0) return watchDelta
    return (right.personal_fit_score ?? 0) - (left.personal_fit_score ?? 0) || right.score - left.score
  })
}

function buildLlmBadge(data: { llm_enabled?: boolean; llm_status?: string; llm_cached_at?: string | null; llm_error?: string | null } | undefined) {
  if (!data) return null

  if (data.llm_enabled && data.llm_status === 'cached_refreshing') {
    return {
      className: 'border-cyan-500/20 bg-cyan-500/5 text-cyan-100',
      text: `최근 OpenAI 코멘트를 먼저 보여주고 있습니다. 백그라운드에서 새 코멘트를 다시 생성 중입니다.${data.llm_cached_at ? ` 마지막 갱신 ${fmtDateTime(data.llm_cached_at)}.` : ''}`,
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
      text: '지금은 규칙 기반 코멘트를 먼저 보여주고 있습니다. OpenAI 코멘트는 백그라운드에서 생성 중이며 다음 새로고침 때 반영됩니다.',
    }
  }

  if (data.llm_error) {
    return {
      className: 'border-amber-500/20 bg-amber-500/5 text-amber-100',
      text: `OpenAI 코멘트를 붙이지 못해 규칙 기반 코멘트로 표시 중입니다. 최근 상태: ${data.llm_error}.`,
    }
  }

  return {
    className: 'border-border bg-background/60 text-muted-foreground',
    text: '현재는 규칙 기반 코멘트를 표시 중입니다.',
  }
}

function QuickEntryCard({
  items,
  loading,
  onOpen,
}: {
  items: AiRecommendationItem[]
  loading: boolean
  onOpen: (code: string) => void
}) {
  return (
    <Card className="space-y-3">
      <div className="flex items-center gap-2 text-sm font-semibold">
        <Target size={16} className="text-emerald-300" />
        빠른 진입 후보
      </div>
      <div className="space-y-2">
        {loading ? (
          <div className="flex min-h-28 items-center justify-center text-sm text-muted-foreground">
            <Loader2 size={16} className="mr-2 animate-spin" />
            후보 정리 중
          </div>
        ) : items.length === 0 ? (
          <div className="rounded-lg border border-border bg-background/60 p-3 text-xs text-muted-foreground">
            아직 우선해서 볼 후보가 없습니다.
          </div>
        ) : (
          items.map(item => (
            <button
              key={`${item.symbol.code}-${item.stance}`}
              onClick={() => onOpen(item.symbol.code)}
              className="flex w-full items-center justify-between gap-3 rounded-lg border border-border bg-background/60 p-3 text-left transition-colors hover:border-primary/40"
            >
              <div>
                <div className="flex flex-wrap items-center gap-1.5">
                  <span className="text-sm font-semibold">{item.symbol.name}</span>
                  <span className={cn('rounded px-1.5 py-0.5 text-[11px]', fitToneClass(item.personal_fit_score ?? 0).chip)}>
                    {item.personal_fit_label ?? '학습 전'}
                  </span>
                </div>
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
  )
}

function PersonalStyleCard({ profile, loading }: { profile?: PersonalStyleProfile; loading: boolean }) {
  const focusPoints = profile?.focus_points?.slice(0, 3) ?? []
  return (
    <Card className="space-y-4 border-violet-500/20 bg-violet-500/5">
      <div className="flex items-center gap-2 text-sm font-semibold">
        <BrainCircuit size={16} className="text-violet-300" />
        내 스타일 프로필
      </div>

      {loading ? (
        <div className="flex min-h-28 items-center justify-center text-sm text-muted-foreground">
          <Loader2 size={16} className="mr-2 animate-spin" />
          프로필 계산 중
        </div>
      ) : (
        <>
          <div className="flex flex-wrap items-center gap-2">
            <span className="rounded-md border border-violet-400/30 bg-violet-400/10 px-2 py-1 text-xs font-semibold text-violet-100">
              {profile?.style_label ?? '학습 중'}
            </span>
            <span className="text-xs text-muted-foreground">
              신뢰도 {fmtPct(profile?.confidence ?? 0, 0)} / 종료 기록 {profile?.sample_count ?? 0}건
            </span>
          </div>

          <p className="text-sm leading-relaxed text-foreground">
            {profile?.summary ?? '아직 종료 기록이 충분하지 않아 개인화가 학습 중입니다.'}
          </p>

          <div className="grid grid-cols-2 gap-3">
            <Metric label="주 성향" value={profile?.primary_intent_label ?? '-'} />
            <Metric label="보조 성향" value={profile?.secondary_intent_label ?? '-'} />
            <Metric label="강한 패턴" value={formatPatternWin(profile?.best_pattern, profile?.best_pattern_win_rate)} />
            <Metric label="강한 타임프레임" value={formatTimeframeWin(profile?.best_timeframe_label, profile?.best_timeframe_win_rate)} />
          </div>

          {focusPoints.length > 0 && (
            <div className="rounded-lg border border-border bg-background/60 p-3">
              <div className="mb-2 text-xs font-semibold text-muted-foreground">개인화 포인트</div>
              <ul className="space-y-1.5 text-xs leading-relaxed text-foreground">
                {focusPoints.map(point => (
                  <li key={point}>{point}</li>
                ))}
              </ul>
            </div>
          )}
        </>
      )}
    </Card>
  )
}

function RecommendationBand({
  title,
  icon,
  items,
  loading,
  empty,
}: {
  title: string
  icon: ReactNode
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
  const { isWatched } = useAppStore()
  const watched = isWatched(item.symbol.code)
  const patternName = item.pattern_type ? PATTERN_NAMES[item.pattern_type] ?? item.pattern_type : '패턴 없음'
  const fitStyle = fitToneClass(item.personal_fit_score ?? 0)

  return (
    <Card className="space-y-4" onClick={() => nav(item.chart_path)}>
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <div className="flex items-center gap-2">
            <span className="text-xs text-muted-foreground">#{item.rank}</span>
            <h2 className="text-lg font-bold">{item.symbol.name}</h2>
            <span className="text-xs text-muted-foreground">{item.symbol.code}</span>
            {watched && (
              <span className="inline-flex items-center gap-1 rounded bg-amber-400/10 px-1.5 py-0.5 text-[11px] text-amber-200">
                <Star size={10} className="fill-amber-200" />
                관심종목
              </span>
            )}
          </div>
          <div className="mt-1 text-xs text-muted-foreground">
            {patternName} / {item.timeframe_label} / {item.state ?? 'scan'}
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <span className={cn('rounded-md border px-2 py-1 text-xs font-medium', fitStyle.chip)}>
            내 스타일 {item.personal_fit_label ?? '학습 전'}
          </span>
          <span className={cn('rounded-md border px-2 py-1 text-xs font-medium', STANCE_STYLES[item.stance])}>
            {item.stance_label}
          </span>
          <span className="rounded-md border border-primary/30 bg-primary/10 px-2 py-1 text-xs font-bold text-primary">
            {Math.round(item.score)}점
          </span>
        </div>
      </div>

      <p className="text-sm leading-relaxed text-foreground">{item.summary}</p>

      <div className="rounded-lg border border-primary/20 bg-primary/10 p-3 text-sm font-semibold leading-relaxed text-primary">
        {item.action_line || item.next_actions[0] || '지금은 핵심 가격대만 확인하고 재평가'}
      </div>

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
        <Metric label="상승 확률" value={fmtPct(item.p_up)} />
        <Metric label="신뢰도" value={fmtPct(item.confidence)} />
        <Metric label="진입 구간" value={fmtPct(item.entry_window_score, 0)} />
        <Metric label="손익비" value={item.reward_risk_ratio.toFixed(2)} />
        <Metric label="개인 적합도" value={`${Math.round(item.personal_fit_score ?? 0)}점`} />
      </div>

      <div className="grid gap-3 lg:grid-cols-2">
        <ActionDetail title="지금 할 일" body={item.do_now || item.action_line} tone="primary" />
        <ActionDetail title="진입 금지 조건" body={item.avoid_if || item.risk_flags[0] || '리스크 신호가 정리될 때까지 대기'} tone="danger" />
        <ActionDetail title="다시 볼 가격" body={item.review_price || item.next_trigger || '핵심 가격대를 확인한 뒤 재평가'} tone="sky" />
        <ActionDetail title="오늘 안 봐도 되는 이유" body={item.skip_reason || '트리거가 아직 완성되지 않았습니다.'} tone="muted" />
      </div>

      <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
        <InfoList title="판단 근거" items={item.reasons} />
        <InfoList title="내 기록 기준" items={item.personal_fit_reasons ?? []} />
      </div>

      {(item.risk_flags.length > 0 || item.overlap_risk) && (
        <div className="rounded-lg border border-amber-500/20 bg-amber-500/5 p-3">
          <div className="mb-2 text-xs font-semibold text-amber-200">리스크 / 중복 노출</div>
          <div className="flex flex-wrap gap-1.5">
            {item.risk_flags.map(flag => (
              <span key={flag} className="rounded-md bg-amber-500/10 px-2 py-1 text-xs text-amber-100">
                {flag}
              </span>
            ))}
            {item.overlap_risk && (
              <span className="rounded-md bg-amber-500/10 px-2 py-1 text-xs text-amber-100">{item.overlap_risk}</span>
            )}
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

function ActionDetail({ title, body, tone }: { title: string; body: string; tone: 'primary' | 'danger' | 'sky' | 'muted' }) {
  const toneClass = {
    primary: 'border-primary/20 bg-primary/8',
    danger: 'border-red-500/20 bg-red-500/5',
    sky: 'border-sky-500/20 bg-sky-500/5',
    muted: 'border-border bg-background/60',
  }[tone]

  return (
    <div className={cn('rounded-lg border p-3', toneClass)}>
      <div className="mb-1 text-xs font-semibold text-muted-foreground">{title}</div>
      <div className="text-sm leading-relaxed text-foreground">{body}</div>
    </div>
  )
}

function InfoList({ title, items }: { title: string; items: string[] }) {
  if (items.length === 0) {
    return (
      <div className="rounded-lg border border-border bg-background/60 p-3">
        <div className="mb-2 text-xs font-semibold text-muted-foreground">{title}</div>
        <div className="text-xs leading-relaxed text-muted-foreground">아직 개인화 재료가 충분하지 않습니다.</div>
      </div>
    )
  }

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

function formatPatternWin(pattern?: string | null, winRate?: number) {
  if (!pattern) return '-'
  const name = PATTERN_NAMES[pattern] ?? pattern
  return typeof winRate === 'number' && winRate > 0 ? `${name} ${fmtPct(winRate, 0)}` : name
}

function formatTimeframeWin(timeframeLabel?: string | null, winRate?: number) {
  if (!timeframeLabel) return '-'
  return typeof winRate === 'number' && winRate > 0 ? `${timeframeLabel} ${fmtPct(winRate, 0)}` : timeframeLabel
}

function fitToneClass(score: number) {
  if (score >= 76) {
    return {
      chip: 'border-violet-400/30 bg-violet-400/10 text-violet-100',
    }
  }
  if (score >= 62) {
    return {
      chip: 'border-sky-400/30 bg-sky-400/10 text-sky-100',
    }
  }
  if (score >= 48) {
    return {
      chip: 'border-amber-400/30 bg-amber-400/10 text-amber-100',
    }
  }
  return {
    chip: 'border-border bg-background/60 text-muted-foreground',
  }
}
