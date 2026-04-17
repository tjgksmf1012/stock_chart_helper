import { useNavigate } from 'react-router-dom'
import { Star } from 'lucide-react'

import type { DashboardItem } from '@/types/api'
import { Badge } from '@/components/ui/Badge'
import { Card } from '@/components/ui/Card'
import { ProbBar } from '@/components/ui/ProbBar'
import { cn, fmtNumber, fmtPct, PATTERN_NAMES, STATE_COLORS, STATE_LABELS } from '@/lib/utils'
import { useAppStore } from '@/store/app'

interface DashboardCardProps {
  item: DashboardItem
}

function sourceBadge(item: DashboardItem): { label: string; variant: 'muted' | 'warning' | 'default' } | null {
  if (item.data_source === 'krx_eod') return { label: 'KRX 기준', variant: 'muted' }
  if (item.data_source === 'fdr_daily') return { label: '일봉 대체', variant: 'warning' }
  if (item.data_source === 'intraday_store') return { label: '저장 분봉', variant: 'warning' }
  if (item.data_source === 'yahoo_fallback') return { label: '분봉 fallback', variant: 'warning' }
  if (item.data_source === 'kis_intraday' || item.data_source === 'hybrid_intraday') return { label: '실시간/혼합', variant: 'default' }
  return null
}

export function DashboardCard({ item }: DashboardCardProps) {
  const nav = useNavigate()
  const { addToWatchlist, removeFromWatchlist, isWatched, setTimeframe } = useAppStore()
  const watched = isWatched(item.symbol.code)
  const source = sourceBadge(item)

  const toggleWatch = (event: React.MouseEvent) => {
    event.stopPropagation()
    if (watched) {
      removeFromWatchlist(item.symbol.code)
    } else {
      addToWatchlist({ code: item.symbol.code, name: item.symbol.name, market: item.symbol.market })
    }
  }

  return (
    <Card
      className="cursor-pointer space-y-3"
      onClick={() => {
        if (item.timeframe) setTimeframe(item.timeframe)
        nav(`/chart/${item.symbol.code}`)
      }}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-1.5">
            <span className="font-mono text-xs text-muted-foreground">#{item.rank}</span>
            <span className="truncate text-sm font-semibold">{item.symbol.name}</span>
            <span className="font-mono text-xs text-muted-foreground">{item.symbol.code}</span>
          </div>
          <div className="mt-1 flex flex-wrap items-center gap-1.5">
            <span className="text-xs text-muted-foreground">{item.symbol.market}</span>
            {item.timeframe_label && <Badge variant="muted">{item.timeframe_label}</Badge>}
            {source && <Badge variant={source.variant}>{source.label}</Badge>}
            {item.pattern_type ? (
              <span className="text-xs text-muted-foreground">
                {PATTERN_NAMES[item.pattern_type] ?? item.pattern_type}
              </span>
            ) : (
              <span className="text-xs text-muted-foreground">패턴 미감지</span>
            )}
            {item.state && (
              <span className={cn('rounded px-1 py-0.5 text-xs', STATE_COLORS[item.state])}>
                {STATE_LABELS[item.state]}
              </span>
            )}
          </div>
        </div>

        <div className="flex items-center gap-2">
          <div className="text-right">
            <div className="text-xs text-muted-foreground">유사도</div>
            <div className="font-mono text-sm font-semibold text-primary">{fmtPct(item.textbook_similarity)}</div>
          </div>
          <button
            onClick={toggleWatch}
            className={cn(
              'rounded p-1.5 transition-colors',
              watched ? 'text-yellow-400 hover:text-yellow-300' : 'text-muted-foreground hover:text-yellow-400',
            )}
            title={watched ? '관심 종목 해제' : '관심 종목 추가'}
          >
            <Star size={14} className={watched ? 'fill-yellow-400' : ''} />
          </button>
        </div>
      </div>

      <ProbBar p_up={item.p_up} p_down={item.p_down} />

      <div className="grid grid-cols-2 gap-2 text-xs text-muted-foreground">
        <span>완성 임박도 {fmtPct(item.completion_proximity)}</span>
        <span className="text-right">신호 신선도 {fmtPct(item.recency_score)}</span>
        <span>신뢰도 {fmtPct(item.confidence)}</span>
        <span className="text-right">데이터 품질 {fmtPct(item.data_quality)}</span>
        <span>유동성 {fmtPct(item.liquidity_score)}</span>
        <span className="text-right">평균 거래대금 {fmtNumber(item.avg_turnover_billion)}억</span>
      </div>

      <p className="line-clamp-2 text-xs leading-relaxed text-muted-foreground">
        {item.fetch_message ? `${item.fetch_message} ` : ''}
        {item.source_note ? `${item.source_note} ` : ''}
        {item.reason_summary}
      </p>

      <div className="flex flex-wrap gap-2">
        {item.sample_size !== null && (
          <Badge variant="muted">
            표본 {item.sample_size}건
            {item.stats_timeframe ? ` · 기준 ${item.stats_timeframe}` : ''}
          </Badge>
        )}
        {item.available_bars > 0 && <Badge variant="muted">분석 바 {item.available_bars}개</Badge>}
        {item.no_signal_flag && <Badge variant="warning">No Signal</Badge>}
      </div>
    </Card>
  )
}
