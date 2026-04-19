import { useNavigate } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { DatabaseZap, Loader2, Star, Trash2, TrendingDown, TrendingUp } from 'lucide-react'

import { Badge } from '@/components/ui/Badge'
import { Card } from '@/components/ui/Card'
import { symbolsApi, systemApi } from '@/lib/api'
import { cn, fmtPct, fmtPrice, PATTERN_NAMES, STATE_COLORS, STATE_LABELS } from '@/lib/utils'
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
            <span className={cn('rounded px-1 py-0.5 text-xs', STATE_COLORS[best.state])}>
              {STATE_LABELS[best.state]}
            </span>
            <span className="text-xs text-muted-foreground">유사도 {fmtPct(best.textbook_similarity)}</span>
          </div>
        ) : analysisQ.isLoading ? (
          <div className="mt-0.5 flex items-center gap-1">
            <Loader2 size={10} className="animate-spin text-muted-foreground" />
            <span className="text-xs text-muted-foreground">분석 중...</span>
          </div>
        ) : (
          <span className="mt-0.5 block text-xs text-muted-foreground">뚜렷한 패턴 없음</span>
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
        title="관심종목 제거"
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

  if (watchlist.length === 0) {
    return (
      <div className="flex h-80 flex-col items-center justify-center gap-4 text-muted-foreground">
        <Star size={40} className="opacity-20" />
        <div className="text-center">
          <p className="font-medium">관심종목이 없습니다</p>
          <p className="mt-1 text-xs">대시보드나 차트에서 별 버튼을 눌러 추가해 주세요.</p>
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
          <p className="mt-0.5 text-xs text-muted-foreground">{watchlist.length}개 종목 모니터링 중</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            onClick={() => warmupMutation.mutate(false)}
            disabled={warmupMutation.isPending}
            className="inline-flex items-center gap-1.5 rounded-md border border-border bg-card px-3 py-1.5 text-xs text-muted-foreground transition-colors hover:text-foreground disabled:cursor-not-allowed disabled:opacity-60"
          >
            <DatabaseZap size={13} className={warmupMutation.isPending ? 'animate-pulse' : ''} />
            저장/공개 분봉 갱신
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

      <Card className="space-y-2 border-primary/20 bg-primary/5">
        <div className="flex items-center gap-2 text-sm font-semibold">
          <DatabaseZap size={15} className="text-primary" />
          관심종목 분봉 캐시
        </div>
        <p className="text-xs leading-relaxed text-muted-foreground">
          관심종목의 15분, 30분, 60분 데이터를 미리 저장해두면 차트 분석과 분봉 스캐너가 더 안정적으로 동작합니다.
          기본 갱신은 KIS 호출을 아끼고, 장중 최신성이 중요할 때만 KIS 포함 갱신을 사용하세요.
        </p>
        {warmupMutation.data && (
          <div className="flex flex-wrap items-center gap-2 text-xs">
            <Badge variant={warmupMutation.data.failure_count > 0 ? 'warning' : 'bullish'}>
              성공 {warmupMutation.data.success_count}/{warmupMutation.data.total_requests}
            </Badge>
            <Badge variant={warmupMutation.data.allow_live ? 'bullish' : 'muted'}>
              {warmupMutation.data.allow_live ? 'KIS 포함' : '저장/공개 우선'}
            </Badge>
            {warmupMutation.data.results.slice(0, 4).map(result => (
              <span key={`${result.symbol}-${result.timeframe}`} className="text-muted-foreground">
                {result.symbol} {result.timeframe} {result.bars}봉
              </span>
            ))}
          </div>
        )}
        {warmupMutation.isError && (
          <div className="text-xs text-red-300">분봉 캐시 갱신 중 오류가 발생했습니다. 운영 상태 페이지와 백엔드 로그를 확인해 주세요.</div>
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

function actionVariant(plan: string): 'bullish' | 'warning' | 'muted' | 'neutral' {
  if (plan === 'ready_now') return 'bullish'
  if (plan === 'watch') return 'neutral'
  if (plan === 'recheck') return 'warning'
  return 'muted'
}
