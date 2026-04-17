import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Star, Trash2, TrendingDown, TrendingUp, Loader2 } from 'lucide-react'

import { useAppStore } from '@/store/app'
import { symbolsApi } from '@/lib/api'
import { Card } from '@/components/ui/Card'
import { fmtPrice, fmtPct, PATTERN_NAMES, STATE_COLORS, STATE_LABELS, cn } from '@/lib/utils'

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
        </div>
        {best ? (
          <div className="mt-0.5 flex items-center gap-1.5">
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
              {price.change >= 0 ? '+' : ''}{fmtPrice(price.change)} ({price.change >= 0 ? '+' : ''}{fmtPct(price.change_pct)})
            </div>
          </>
        ) : (
          <span className="text-xs text-muted-foreground">-</span>
        )}
      </div>

      <button
        onClick={e => { e.stopPropagation(); removeFromWatchlist(code) }}
        className="shrink-0 rounded p-1.5 text-muted-foreground transition-colors hover:bg-red-400/10 hover:text-red-400"
        title="관심 종목 제거"
      >
        <Trash2 size={14} />
      </button>
    </Card>
  )
}

export default function WatchlistPage() {
  const { watchlist } = useAppStore()
  const nav = useNavigate()

  if (watchlist.length === 0) {
    return (
      <div className="flex h-80 flex-col items-center justify-center gap-4 text-muted-foreground">
        <Star size={40} className="opacity-20" />
        <div className="text-center">
          <p className="font-medium">관심 종목이 없습니다</p>
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
      <div className="flex items-center justify-between">
        <div>
          <h1 className="flex items-center gap-2 text-xl font-bold">
            <Star size={18} className="fill-yellow-400 text-yellow-400" />
            관심 종목
          </h1>
          <p className="mt-0.5 text-xs text-muted-foreground">{watchlist.length}개 종목 모니터링 중</p>
        </div>
      </div>

      <div className="space-y-2">
        {[...watchlist].reverse().map(item => (
          <WatchlistRow key={item.code} code={item.code} name={item.name} market={item.market} />
        ))}
      </div>
    </div>
  )
}
