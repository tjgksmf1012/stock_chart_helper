import { useMemo, useState } from 'react'
import { ChevronDown, Loader2 } from 'lucide-react'

import { SectorHeatmap } from '@/components/dashboard/SectorHeatmap'
import { Badge } from '@/components/ui/Badge'
import { Card } from '@/components/ui/Card'
import { QueryError } from '@/components/ui/QueryError'
import type { ObservationDeck } from '@/lib/observationDeck'
import { TIMEFRAME_OPTIONS } from '@/lib/timeframes'
import { cn, fmtPct, PATTERN_NAMES, SETUP_STAGE_LABELS } from '@/lib/utils'
import type { DashboardItem, SectorHeatmapResponse, Timeframe } from '@/types/api'

const OPEN_STORAGE_KEY = 'today-observation-open'
const INITIAL_VISIBLE = 8

type SortMode = 'priority' | 'p_up'

/**
 * 관찰 후보 — 기존 대시보드의 후보 섹션 7개를 종목 중복 없이 하나로 접어 넣은 보조 섹션.
 * 검증 엣지가 얇은(+0.7%/거래) 패턴 엔진 출력이라 기본은 접힘, 정직한 컨텍스트 라벨을 단다.
 */
export function ObservationSection({
  deck,
  isLoading,
  isError,
  onRetry,
  timeframe,
  onTimeframeChange,
  sectors,
  onOpen,
}: {
  deck: ObservationDeck
  isLoading: boolean
  isError: boolean
  onRetry: () => void
  timeframe: Timeframe
  onTimeframeChange: (tf: Timeframe) => void
  sectors: SectorHeatmapResponse | undefined
  onOpen: (item: DashboardItem) => void
}) {
  const [open, setOpen] = useState(() => {
    try {
      return localStorage.getItem(OPEN_STORAGE_KEY) === '1'
    } catch {
      return false
    }
  })
  const [sortMode, setSortMode] = useState<SortMode>('priority')
  const [expanded, setExpanded] = useState(false)

  const toggleOpen = () => {
    setOpen(prev => {
      try {
        localStorage.setItem(OPEN_STORAGE_KEY, prev ? '0' : '1')
      } catch { /* localStorage 불가 환경 무시 */ }
      return !prev
    })
  }

  const sorted = useMemo(() => {
    if (sortMode === 'p_up') return [...deck.items].sort((a, b) => b.p_up - a.p_up)
    return deck.items // priority = 덱 빌더의 섹션 우선순위 순서 그대로 (완성 임박 먼저)
  }, [deck.items, sortMode])

  const visible = expanded ? sorted : sorted.slice(0, INITIAL_VISIBLE)
  const hiddenCount = Math.max(0, sorted.length - INITIAL_VISIBLE)

  return (
    <Card className="space-y-3">
      <button onClick={toggleOpen} className="flex w-full items-center justify-between gap-3 text-left">
        <div className="flex min-w-0 items-center gap-2">
          <ChevronDown size={15} className={cn('shrink-0 text-muted-foreground transition-transform', open && 'rotate-180')} />
          <span className="text-sm font-semibold">관찰 후보 (차트 패턴)</span>
          <span className="hidden text-xs text-muted-foreground sm:inline">
            — 고유 {deck.uniqueCount}종목 · 완성 임박 {deck.armedCount}
          </span>
        </div>
        <span className="shrink-0 text-[11px] text-muted-foreground/80">검증 엣지 얇음(+0.7%/거래) · 참고용</span>
      </button>

      {open && (
        <div className="space-y-3">
          <div className="flex flex-wrap items-center gap-2 text-xs">
            <select
              value={timeframe}
              onChange={e => onTimeframeChange(e.target.value as Timeframe)}
              className="rounded border border-border bg-card px-2 py-1 text-foreground"
            >
              {TIMEFRAME_OPTIONS.map(option => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
            <select
              value={sortMode}
              onChange={e => setSortMode(e.target.value as SortMode)}
              className="rounded border border-border bg-card px-2 py-1 text-foreground"
            >
              <option value="priority">완성 임박순</option>
              <option value="p_up">상승 확률순</option>
            </select>
          </div>

          {isLoading ? (
            <div className="flex h-24 flex-col items-center justify-center gap-2 rounded-lg border border-border bg-background/40 text-muted-foreground">
              <Loader2 size={16} className="animate-spin" />
              <span className="text-xs">후보를 불러오는 중입니다.</span>
            </div>
          ) : isError ? (
            <QueryError compact onRetry={onRetry} />
          ) : sorted.length === 0 ? (
            <div className="rounded-lg border border-dashed border-border bg-background/30 px-4 py-3 text-xs text-muted-foreground">
              조건에 맞는 후보가 아직 없습니다. 스캔이 끝나면 여기에 나타납니다.
            </div>
          ) : (
            <>
              <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-2 xl:grid-cols-3">
                {visible.map(item => (
                  <CompactCandidateCard key={`${item.timeframe}-${item.symbol.code}`} item={item} onOpen={() => onOpen(item)} />
                ))}
              </div>
              {hiddenCount > 0 && (
                <button
                  onClick={() => setExpanded(prev => !prev)}
                  className="inline-flex items-center gap-2 rounded-lg border border-border bg-background/50 px-3 py-2 text-xs font-medium text-muted-foreground transition-colors hover:text-foreground"
                >
                  {expanded ? '접기' : `${hiddenCount}개 더 보기`}
                  <ChevronDown size={14} className={cn('transition-transform', expanded && 'rotate-180')} />
                </button>
              )}
            </>
          )}

          {sectors && sectors.sectors.length > 0 && <SectorHeatmap sectors={sectors.sectors} />}
        </div>
      )}
    </Card>
  )
}

function CompactCandidateCard({ item, onOpen }: { item: DashboardItem; onOpen: () => void }) {
  // 카드마다 다른 내용만 남긴다 — 전 카드 공통 보일러플레이트 문장은 렌더하지 않는 것이 다이어트의 본체
  const uniqueLine = item.trend_warning || item.wyckoff_note || null

  return (
    <button
      onClick={onOpen}
      className="rounded-lg border border-border bg-card/60 p-3 text-left transition-colors hover:border-primary/30 hover:bg-muted/20"
    >
      <div className="flex items-center justify-between gap-2">
        <span className="truncate text-sm font-medium">{item.symbol.name}</span>
        <span className="shrink-0 font-mono text-[11px] text-muted-foreground">{item.symbol.code}</span>
      </div>
      <div className="mt-1.5 flex flex-wrap items-center gap-1.5 text-[11px]">
        <Badge variant="muted">{(item.pattern_type && PATTERN_NAMES[item.pattern_type]) ?? item.pattern_type ?? '패턴 없음'}</Badge>
        <span className="text-muted-foreground">{SETUP_STAGE_LABELS[item.setup_stage] ?? item.setup_stage}</span>
      </div>
      <div className="mt-2 flex gap-4 text-xs text-muted-foreground">
        <span>
          상승 <b className="font-semibold tabular-nums text-foreground">{fmtPct(item.p_up, 0)}</b>
        </span>
        <span>
          준비 <b className="font-semibold tabular-nums text-foreground">{fmtPct(item.trade_readiness_score, 0)}</b>
        </span>
      </div>
      {uniqueLine && <p className="mt-2 line-clamp-2 text-[11px] leading-relaxed text-muted-foreground">{uniqueLine}</p>}
    </button>
  )
}
