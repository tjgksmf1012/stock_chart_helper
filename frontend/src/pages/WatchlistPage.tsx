import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Star, Trash2, TrendingUp, TrendingDown, Minus, Loader2 } from 'lucide-react'
import { useAppStore } from '@/store/app'
import { symbolsApi } from '@/lib/api'
import { Card } from '@/components/ui/Card'
import { fmtPrice, fmtPct, PATTERN_NAMES, STATE_COLORS, STATE_LABELS } from '@/lib/utils'
import { cn } from '@/lib/utils'

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

  const changePos = price && price.change >= 0
  const changeColor = !price ? '' : price.change > 0 ? 'text-emerald-400' : price.change < 0 ? 'text-red-400' : 'text-muted-foreground'

  return (
    <Card
      className="flex items-center gap-4 cursor-pointer hover:border-primary/40 transition-colors"
      onClick={() => nav(`/chart/${code}`)}
    >
      {/* Symbol info */}
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <span className="font-semibold text-sm truncate">{name}</span>
          <span className="font-mono text-xs text-muted-foreground shrink-0">{code}</span>
          <span className="text-xs text-muted-foreground shrink-0">{market}</span>
        </div>
        {best ? (
          <div className="flex items-center gap-1.5 mt-0.5">
            <span className="text-xs text-muted-foreground">{PATTERN_NAMES[best.pattern_type] ?? best.pattern_type}</span>
            <span className={cn('text-xs px-1 py-0.5 rounded', STATE_COLORS[best.state])}>
              {STATE_LABELS[best.state]}
            </span>
            <span className="text-xs text-muted-foreground">유사도 {fmtPct(best.textbook_similarity)}</span>
          </div>
        ) : analysisQ.isLoading ? (
          <div className="flex items-center gap-1 mt-0.5">
            <Loader2 size={10} className="animate-spin text-muted-foreground" />
            <span className="text-xs text-muted-foreground">분석 중...</span>
          </div>
        ) : (
          <span className="text-xs text-muted-foreground mt-0.5 block">패턴 미감지</span>
        )}
      </div>

      {/* Probability */}
      {analysis && !analysis.no_signal_flag && (
        <div className="hidden sm:flex items-center gap-3 text-xs">
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

      {/* Price */}
      <div className="text-right shrink-0">
        {priceQ.isLoading ? (
          <Loader2 size={12} className="animate-spin text-muted-foreground" />
        ) : price && price.close > 0 ? (
          <>
            <div className="font-mono text-sm font-semibold">{fmtPrice(price.close)}</div>
            <div className={cn('text-xs font-mono', changeColor)}>
              {price.change >= 0 ? '+' : ''}{fmtPrice(price.change)} ({price.change >= 0 ? '+' : ''}{fmtPct(price.change_pct)})
            </div>
          </>
        ) : (
          <span className="text-xs text-muted-foreground">-</span>
        )}
      </div>

      {/* Remove button */}
      <button
        onClick={e => { e.stopPropagation(); removeFromWatchlist(code) }}
        className="p-1.5 rounded hover:bg-red-400/10 text-muted-foreground hover:text-red-400 transition-colors shrink-0"
        title="관심 종목 삭제"
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
      <div className="flex flex-col items-center justify-center h-80 gap-4 text-muted-foreground">
        <Star size={40} className="opacity-20" />
        <div className="text-center">
          <p className="font-medium">관심 종목이 없습니다</p>
          <p className="text-xs mt-1">대시보드나 차트에서 ★ 버튼을 눌러 추가하세요</p>
        </div>
        <button
          onClick={() => nav('/')}
          className="mt-2 text-xs text-primary hover:underline"
        >
          대시보드 바로가기
        </button>
      </div>
    )
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold flex items-center gap-2">
            <Star size={18} className="text-yellow-400 fill-yellow-400" />
            관심 종목
          </h1>
          <p className="text-xs text-muted-foreground mt-0.5">{watchlist.length}개 종목 모니터링 중</p>
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
