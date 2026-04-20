import { useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import { useMutation, useQueries, useQuery, useQueryClient } from '@tanstack/react-query'
import { DatabaseZap, Loader2, Star, Target, Trash2, TrendingDown, TrendingUp } from 'lucide-react'

import { Badge } from '@/components/ui/Badge'
import { Card } from '@/components/ui/Card'
import { symbolsApi, systemApi } from '@/lib/api'
import { cn, fmtPct, fmtPrice, PATTERN_NAMES, STATE_COLORS, STATE_LABELS } from '@/lib/utils'
import type { AnalysisResult } from '@/types/api'
import { useAppStore } from '@/store/app'

function WatchlistRow({ code, name, market }: { code: string; name: string; market: string }) {
  const nav = useNavigate()
  const { removeFromWatchlist } = useAppStore()

  const priceQ = useQuery({
    queryKey: ['price', code],
    queryFn: () => symbolsApi.getPrice(code),
    staleTime: 60_000,
    refetchInterval: 120_000,
  })

  const analysisQ = useQuery({
    queryKey: ['analysis', code, '1d'],
    queryFn: () => symbolsApi.getAnalysis(code, '1d'),
    staleTime: 300_000,
  })

  const price = priceQ.data
  const analysis = analysisQ.data
  const best = analysis?.patterns[0]
  const changeColor = !price ? '' : price.change > 0 ? 'text-emerald-400' : price.change < 0 ? 'text-red-400' : 'text-muted-foreground'

  return (
    <Card
      className="flex cursor-pointer items-center gap-4 transition-colors hover:border-primary/40"
      onClick={() => nav(`/chart/${code}`)}
    >
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className="truncate text-sm font-semibold">{name}</span>
          <span className="shrink-0 font-mono text-xs text-muted-foreground">{code}</span>
          <span className="shrink-0 text-xs text-muted-foreground">{market}</span>
          {analysis?.action_plan_label && <Badge variant={actionVariant(analysis.action_plan)}>{analysis.action_plan_label}</Badge>}
        </div>

        {best ? (
          <div className="mt-0.5 flex flex-wrap items-center gap-1.5">
            <span className="text-xs text-muted-foreground">{PATTERN_NAMES[best.pattern_type] ?? best.pattern_type}</span>
            <span className={cn('rounded px-1 py-0.5 text-xs', STATE_COLORS[best.state])}>{STATE_LABELS[best.state]}</span>
            <span className="text-xs text-muted-foreground">유사도 {fmtPct(best.textbook_similarity)}</span>
          </div>
        ) : analysisQ.isLoading ? (
          <div className="mt-0.5 flex items-center gap-1">
            <Loader2 size={10} className="animate-spin text-muted-foreground" />
            <span className="text-xs text-muted-foreground">분석 중...</span>
          </div>
        ) : analysisQ.isError ? (
          <button
            onClick={event => { event.stopPropagation(); void analysisQ.refetch() }}
            className="mt-0.5 flex items-center gap-1 text-xs text-red-400/70 hover:text-red-400"
          >
            <span>분석 실패 — 재시도</span>
          </button>
        ) : (
          <span className="mt-0.5 block text-xs text-muted-foreground">설명 가능한 패턴이 아직 없습니다</span>
        )}

        {analysis?.next_trigger && <p className="mt-1 line-clamp-1 text-xs text-muted-foreground">{analysis.next_trigger}</p>}
      </div>

      {analysis && !analysis.no_signal_flag && (
        <div className="hidden items-center gap-3 text-xs sm:flex">
          <div className="flex items-center gap-1">
            <TrendingUp size={11} className="text-emerald-400" />
            <span className="text-emerald-400">{fmtPct(analysis.p_up)}</span>
          </div>
          <div className="flex items-center gap-1">
            <TrendingDown size={11} className="text-red-400" />
            <span className="text-red-400">{fmtPct(analysis.p_down)}</span>
          </div>
        </div>
      )}

      <div className="shrink-0 text-right">
        {priceQ.isLoading ? (
          <Loader2 size={12} className="animate-spin text-muted-foreground" />
        ) : price && price.close > 0 ? (
          <>
            <div className="font-mono text-sm font-semibold">{fmtPrice(price.close)}</div>
            <div className={cn('font-mono text-xs', changeColor)}>
              {price.change >= 0 ? '+' : ''}
              {fmtPrice(price.change)} ({price.change >= 0 ? '+' : ''}
              {fmtPct(price.change_pct)})
            </div>
          </>
        ) : (
          <span className="text-xs text-muted-foreground">-</span>
        )}
      </div>

      <button
        onClick={event => {
          event.stopPropagation()
          removeFromWatchlist(code)
        }}
        className="shrink-0 rounded p-1.5 text-muted-foreground transition-colors hover:bg-red-400/10 hover:text-red-400"
        title="관심종목에서 제거"
      >
        <Trash2 size={14} />
      </button>
    </Card>
  )
}

export default function WatchlistPage() {
  const { watchlist } = useAppStore()
  const nav = useNavigate()
  const queryClient = useQueryClient()

  const analysisQueries = useQueries({
    queries: watchlist.map(item => ({
      queryKey: ['analysis', item.code, '1d'],
      queryFn: () => symbolsApi.getAnalysis(item.code, '1d'),
      staleTime: 300_000,
    })),
  })

  const warmupMutation = useMutation({
    mutationFn: (allowLive: boolean) =>
      systemApi.warmupIntraday({
        symbols: watchlist.map(item => item.code),
        timeframes: ['15m', '30m', '60m'],
        allow_live: allowLive,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['system', 'status'] })
    },
  })

  const summary = useMemo(() => {
    const markets = new Map<string, number>()
    watchlist.forEach(item => markets.set(item.market, (markets.get(item.market) ?? 0) + 1))

    const analyses = analysisQueries
      .map((query, index) => (query.data ? { item: watchlist[index], analysis: query.data } : null))
      .filter((entry): entry is { item: (typeof watchlist)[number]; analysis: AnalysisResult } => Boolean(entry))

    const actionable = analyses.filter(entry => entry.analysis.action_plan === 'ready_now')
    const watchOnly = analyses.filter(entry => entry.analysis.action_plan === 'watch')
    const caution = analyses.filter(
      entry => entry.analysis.action_plan === 'recheck' || entry.analysis.no_signal_flag || (entry.analysis.trade_readiness_score ?? 0) < 0.45,
    )
    const avgUp =
      analyses.length > 0 ? analyses.reduce((sum, entry) => sum + (entry.analysis.no_signal_flag ? 0 : entry.analysis.p_up), 0) / analyses.length : 0
    const avgReadiness =
      analyses.length > 0 ? analyses.reduce((sum, entry) => sum + (entry.analysis.trade_readiness_score ?? 0), 0) / analyses.length : 0

    const focusList = [...analyses]
      .filter(entry => !entry.analysis.no_signal_flag)
      .sort((a, b) => {
        if ((b.analysis.action_priority_score ?? 0) !== (a.analysis.action_priority_score ?? 0)) {
          return (b.analysis.action_priority_score ?? 0) - (a.analysis.action_priority_score ?? 0)
        }
        return (b.analysis.trade_readiness_score ?? 0) - (a.analysis.trade_readiness_score ?? 0)
      })
      .slice(0, 3)

    return {
      total: watchlist.length,
      kospi: markets.get('KOSPI') ?? 0,
      kosdaq: markets.get('KOSDAQ') ?? 0,
      analyses,
      actionableCount: actionable.length,
      watchCount: watchOnly.length,
      cautionCount: caution.length,
      avgUp,
      avgReadiness,
      focusList,
      loadingCount: analysisQueries.filter(query => query.isLoading).length,
    }
  }, [analysisQueries, watchlist])

  if (watchlist.length === 0) {
    return (
      <div className="flex h-80 flex-col items-center justify-center gap-4 text-muted-foreground">
        <Star size={40} className="opacity-20" />
        <div className="text-center">
          <p className="font-medium">관심종목이 아직 없습니다.</p>
          <p className="mt-1 text-xs">대시보드나 차트 화면에서 별 버튼을 눌러 관찰할 종목을 추가해 보세요.</p>
        </div>
        <button onClick={() => nav('/')} className="mt-2 text-xs text-primary hover:underline">
          대시보드로 돌아가기
        </button>
      </div>
    )
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
        <div>
          <h1 className="flex items-center gap-2 text-xl font-bold">
            <Star size={18} className="fill-yellow-400 text-yellow-400" />
            관심종목
          </h1>
          <p className="mt-0.5 text-xs text-muted-foreground">
            {summary.total}개 종목을 관찰 중입니다. KOSPI {summary.kospi} / KOSDAQ {summary.kosdaq}
            {summary.loadingCount > 0 && ` · 분석 로딩 ${summary.loadingCount}개`}
          </p>
        </div>

        <div className="flex flex-wrap gap-2">
          <button
            onClick={() => warmupMutation.mutate(false)}
            disabled={warmupMutation.isPending}
            className="inline-flex items-center gap-1.5 rounded-md border border-border bg-card px-3 py-1.5 text-xs text-muted-foreground transition-colors hover:text-foreground disabled:cursor-not-allowed disabled:opacity-60"
          >
            <DatabaseZap size={13} className={warmupMutation.isPending ? 'animate-pulse' : ''} />
            저장 우선 분봉 갱신
          </button>
          <button
            onClick={() => warmupMutation.mutate(true)}
            disabled={warmupMutation.isPending}
            className="inline-flex items-center gap-1.5 rounded-md border border-primary/30 bg-primary/10 px-3 py-1.5 text-xs text-primary transition-colors hover:bg-primary/15 disabled:cursor-not-allowed disabled:opacity-60"
          >
            <DatabaseZap size={13} className={warmupMutation.isPending ? 'animate-pulse' : ''} />
            KIS 포함 갱신
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <SummaryMetric label="지금 바로 볼 후보" value={`${summary.actionableCount}개`} tone="bullish" badgeLabel="우선 확인" />
        <SummaryMetric label="지켜볼 후보" value={`${summary.watchCount}개`} tone="neutral" badgeLabel="관찰" />
        <SummaryMetric label="보수적으로 볼 후보" value={`${summary.cautionCount}개`} tone="warning" badgeLabel="주의" />
        <SummaryMetric label="평균 거래 준비도" value={fmtPct(summary.avgReadiness, 0)} tone="muted" badgeLabel="평균" />
      </div>

      <Card className="space-y-3 border-primary/20 bg-primary/5">
        <div className="flex items-center gap-2 text-sm font-semibold">
          <Target size={15} className="text-primary" />
          한눈에 보는 관심종목 판단
        </div>
        <p className="text-xs leading-relaxed text-muted-foreground">
          지금 바로 볼 종목은 {summary.actionableCount}개, 조금 더 지켜볼 종목은 {summary.watchCount}개입니다. 일봉 기준 평균 상승 확률은{' '}
          {fmtPct(summary.avgUp, 0)}이고, 전체 평균 거래 준비도는 {fmtPct(summary.avgReadiness, 0)}입니다.
        </p>
        {summary.focusList.length > 0 ? (
          <div className="grid grid-cols-1 gap-2 lg:grid-cols-3">
            {summary.focusList.map(entry => (
              <button
                key={entry.item.code}
                onClick={() => nav(`/chart/${entry.item.code}`)}
                className="rounded-lg border border-border bg-background/60 p-3 text-left transition-colors hover:border-primary/40"
              >
                <div className="flex items-center justify-between gap-2">
                  <div>
                    <div className="text-sm font-semibold">{entry.item.name}</div>
                    <div className="text-xs text-muted-foreground">
                      {entry.item.code} · {entry.item.market}
                    </div>
                  </div>
                  <Badge variant={actionVariant(entry.analysis.action_plan)}>{entry.analysis.action_plan_label}</Badge>
                </div>
                <p className="mt-2 line-clamp-2 text-xs leading-relaxed text-muted-foreground">{entry.analysis.action_plan_summary}</p>
                <div className="mt-2 flex flex-wrap gap-2 text-xs text-muted-foreground">
                  <span>준비도 {fmtPct(entry.analysis.trade_readiness_score ?? 0, 0)}</span>
                  <span>진입 {fmtPct(entry.analysis.entry_window_score ?? 0, 0)}</span>
                  <span>신선도 {fmtPct(entry.analysis.freshness_score ?? 0, 0)}</span>
                </div>
              </button>
            ))}
          </div>
        ) : (
          <div className="rounded-lg border border-border bg-background/60 p-3 text-xs leading-relaxed text-muted-foreground">
            아직 분석이 충분히 모이지 않았습니다. 잠시 후 다시 보거나 분봉 캐시를 먼저 갱신해 주세요.
          </div>
        )}
      </Card>

      <Card className="space-y-2 border-primary/20 bg-primary/5">
        <div className="flex items-center gap-2 text-sm font-semibold">
          <DatabaseZap size={15} className="text-primary" />
          관심종목 분봉 캐시
        </div>
        <p className="text-xs leading-relaxed text-muted-foreground">
          관심종목의 15분, 30분, 60분 데이터를 미리 채워 두면 차트 상세와 분봉 대시보드가 훨씬 빠르고 안정적으로 열립니다. 기본은 저장
          우선 방식이 가볍고, 장중 최신성까지 꼭 필요할 때만 KIS 포함 갱신을 쓰는 편이 좋습니다.
        </p>

        {warmupMutation.data && (
          <div className="flex flex-wrap items-center gap-2 text-xs">
            <Badge variant={warmupMutation.data.failure_count > 0 ? 'warning' : 'bullish'}>
              성공 {warmupMutation.data.success_count}/{warmupMutation.data.total_requests}
            </Badge>
            <Badge variant={warmupMutation.data.allow_live ? 'bullish' : 'muted'}>
              {warmupMutation.data.allow_live ? 'KIS 포함' : '저장 우선'}
            </Badge>
            {warmupMutation.data.results.slice(0, 4).map(result => (
              <span key={`${result.symbol}-${result.timeframe}`} className="text-muted-foreground">
                {result.symbol} {result.timeframe} {result.bars}개
              </span>
            ))}
          </div>
        )}

        {warmupMutation.isError && (
          <div className="text-xs text-red-300">
            분봉 캐시 갱신 중 오류가 발생했습니다. 운영 상태 페이지와 백엔드 로그를 함께 확인해 주세요.
          </div>
        )}
      </Card>

      <div className="space-y-2">
        {[...watchlist].reverse().map(item => (
          <WatchlistRow key={item.code} code={item.code} name={item.name} market={item.market} />
        ))}
      </div>
    </div>
  )
}

function SummaryMetric({
  label,
  value,
  tone,
  badgeLabel,
}: {
  label: string
  value: string
  tone: 'bullish' | 'warning' | 'muted' | 'neutral'
  badgeLabel: string
}) {
  return (
    <Card className="space-y-2">
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className="flex items-center justify-between gap-2">
        <div className="text-lg font-semibold">{value}</div>
        <Badge variant={tone}>{badgeLabel}</Badge>
      </div>
    </Card>
  )
}

function actionVariant(plan: string): 'bullish' | 'warning' | 'muted' | 'neutral' {
  if (plan === 'ready_now') return 'bullish'
  if (plan === 'watch') return 'neutral'
  if (plan === 'recheck') return 'warning'
  return 'muted'
}
