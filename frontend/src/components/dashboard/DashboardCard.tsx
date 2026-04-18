import type { MouseEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { AlertTriangle, Layers3, Star } from 'lucide-react'

import type { DashboardItem } from '@/types/api'
import { Badge } from '@/components/ui/Badge'
import { Card } from '@/components/ui/Card'
import { ProbBar } from '@/components/ui/ProbBar'
import { cn, fmtPct, fmtTurnoverBillion, PATTERN_NAMES, STATE_COLORS, STATE_LABELS } from '@/lib/utils'
import { useAppStore } from '@/store/app'

interface DashboardCardProps {
  item: DashboardItem
}

export function DashboardCard({ item }: DashboardCardProps) {
  const nav = useNavigate()
  const { addToWatchlist, removeFromWatchlist, isWatched, setTimeframe } = useAppStore()
  const watched = isWatched(item.symbol.code)

  const toggleWatch = (event: MouseEvent) => {
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
        setTimeframe(item.timeframe)
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
          <div className="mt-1 flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
            <span>{item.symbol.market}</span>
            <span>·</span>
            <span>{item.timeframe_label}</span>
            <Badge variant={item.data_quality >= 0.8 ? 'bullish' : item.data_quality >= 0.6 ? 'muted' : 'warning'}>
              품질 {fmtPct(item.data_quality, 0)}
            </Badge>
            <Badge
              variant={item.confluence_score >= 0.7 ? 'bullish' : item.confluence_score >= 0.5 ? 'muted' : 'warning'}
            >
              합산 {fmtPct(item.confluence_score, 0)}
            </Badge>
            <Badge
              variant={item.sample_reliability >= 0.65 ? 'bullish' : item.sample_reliability >= 0.45 ? 'muted' : 'warning'}
            >
              표본 {fmtPct(item.sample_reliability, 0)}
            </Badge>
            <Badge
              variant={item.historical_edge_score >= 0.65 ? 'bullish' : item.historical_edge_score >= 0.45 ? 'muted' : 'warning'}
            >
              edge {fmtPct(item.historical_edge_score, 0)}
            </Badge>
            <Badge
              variant={item.reward_risk_ratio >= 1.8 ? 'bullish' : item.reward_risk_ratio >= 1.2 ? 'muted' : 'warning'}
            >
              손익비 {item.reward_risk_ratio.toFixed(1)}
            </Badge>
            <Badge
              variant={item.trend_alignment_score >= 0.75 ? 'bullish' : item.trend_alignment_score >= 0.5 ? 'muted' : 'warning'}
            >
              추세 {fmtPct(item.trend_alignment_score, 0)}
            </Badge>
          </div>

          {item.pattern_type ? (
            <div className="mt-2 flex flex-wrap items-center gap-1.5">
              <span className="text-xs text-muted-foreground">{PATTERN_NAMES[item.pattern_type] ?? item.pattern_type}</span>
              {item.state && (
                <span className={cn('rounded px-1 py-0.5 text-xs', STATE_COLORS[item.state])}>{STATE_LABELS[item.state]}</span>
              )}
            </div>
          ) : (
            <div className="mt-2 text-xs text-muted-foreground">뚜렷한 패턴 없음</div>
          )}
        </div>

        <div className="flex items-center gap-2">
          <div className="text-right">
            <div className="text-xs text-muted-foreground">임박도</div>
            <div className="font-mono text-sm font-semibold text-primary">{fmtPct(item.completion_proximity, 0)}</div>
          </div>
          <button
            onClick={toggleWatch}
            className={cn(
              'rounded p-1.5 transition-colors',
              watched ? 'text-yellow-400 hover:text-yellow-300' : 'text-muted-foreground hover:text-yellow-400',
            )}
            title={watched ? '관심 종목 제거' : '관심 종목 추가'}
          >
            <Star size={14} className={watched ? 'fill-yellow-400' : ''} />
          </button>
        </div>
      </div>

      <ProbBar p_up={item.p_up} p_down={item.p_down} />

      <div className="grid grid-cols-2 gap-2 text-xs text-muted-foreground">
        <span>신뢰도 {fmtPct(item.confidence)}</span>
        <span className="text-right">신선도 {fmtPct(item.recency_score)}</span>
        <span>평균 MFE {fmtPct(item.avg_mfe_pct)}</span>
        <span className="text-right">평균 MAE {fmtPct(item.avg_mae_pct)}</span>
        <span>거래대금 {fmtTurnoverBillion(item.avg_turnover_billion)}</span>
        <span className="text-right">표본 {item.sample_size}건</span>
        <span>목표 여지 {fmtPct(item.target_distance_pct)}</span>
        <span className="text-right">손절 거리 {fmtPct(item.stop_distance_pct)}</span>
        <span>보정 승률 {fmtPct(item.empirical_win_rate)}</span>
        <span className="text-right">edge {fmtPct(item.historical_edge_score)}</span>
        <span>평균 결과 바 수 {item.avg_bars_to_outcome.toFixed(1)}</span>
        <span className="text-right">{item.trend_direction}</span>
      </div>

      <div className="rounded-lg border border-border bg-background/60 p-2.5">
        <div className="flex items-center gap-1.5 text-[11px] font-medium text-muted-foreground">
          <Layers3 size={12} />
          멀티 타임프레임 정렬
        </div>
        <p className="mt-1 text-xs text-muted-foreground">{item.confluence_summary}</p>
        <p className="mt-1 text-xs leading-relaxed text-foreground/90">{item.scenario_text}</p>
      </div>

      {(item.fetch_message || item.no_signal_flag) && (
        <div className="rounded-lg border border-border bg-background/60 p-2.5">
          <div className="flex items-center gap-1.5 text-[11px] font-medium text-muted-foreground">
            <AlertTriangle size={12} />
            데이터 메모
          </div>
          <p className="mt-1 text-xs text-muted-foreground">{item.fetch_message || item.source_note}</p>
        </div>
      )}

      {item.trend_warning && (
        <div className="rounded-lg border border-amber-500/20 bg-amber-500/5 p-2.5 text-xs text-amber-200">
          {item.trend_warning}
        </div>
      )}

      <p className="line-clamp-2 text-xs leading-relaxed text-muted-foreground">{item.reason_summary}</p>

      {item.no_signal_flag && <Badge variant="warning">No Signal</Badge>}
    </Card>
  )
}
