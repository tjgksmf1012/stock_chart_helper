# Stock Chart Helper — Improvements Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete remaining infinite-loading fixes, wire the outcomes API into the frontend, and add false-positive flagging.

**Architecture:** Pure frontend changes. `outcomesApi` and all TypeScript types are already in `api.ts` / `types/api.ts` — no new files needed except the outcomes tab component (inlined into PatternPerformancePage). All mutations use React Query `useMutation`, all queries use `useQuery`. No new UI primitives needed; use existing `Card`, `Badge`, `QueryError` components.

**Tech Stack:** React 18, TypeScript, React Query v5 (`@tanstack/react-query`), Axios (via `api.ts`), Tailwind CSS, Lucide React icons.

---

## File Map

| File | Change |
|------|--------|
| `frontend/src/pages/PatternPerformancePage.tsx` | Add `isError`/`refetch`, add "내 기록" tab |
| `frontend/src/pages/PatternLibraryPage.tsx` | Add `isError`/`refetch` + `QueryError` |
| `frontend/src/pages/WatchlistPage.tsx` | Add `analysisQ.isError` branch in `WatchlistRow` |
| `frontend/src/pages/ChartPage.tsx` | Add "신호 저장" button in analysis header |
| `frontend/src/components/chart/AnalysisPanel.tsx` | Add "오탐 신고" button in 확률 분석 card |
| `frontend/src/components/dashboard/DashboardCard.tsx` | Add bookmark save button |

---

## Task 1: PatternLibraryPage — add isError branch

**Files:**
- Modify: `frontend/src/pages/PatternLibraryPage.tsx`

- [ ] **Step 1: Add `QueryError` import and destructure `isError` + `refetch` from useQuery**

Replace the import block and the `useQuery` call:

```tsx
// Add to existing imports at top
import { QueryError } from '@/components/ui/QueryError'
```

Find and replace in `PatternLibraryPage`:
```tsx
// BEFORE (line 107)
  const { data, isLoading } = useQuery({
    queryKey: ['patterns', 'library'],
    queryFn: patternsApi.library,
    staleTime: Infinity,
  })
```
```tsx
// AFTER
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['patterns', 'library'],
    queryFn: patternsApi.library,
    staleTime: Infinity,
  })
```

- [ ] **Step 2: Add `isError` branch in JSX**

Find and replace:
```tsx
// BEFORE (line 158)
      {isLoading ? (
        <div className="py-10 text-center text-muted-foreground">불러오는 중입니다...</div>
      ) : (
        <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
          {filtered.map(entry => (
            <PatternCard key={entry.pattern_type} entry={entry} />
          ))}
        </div>
      )}
```
```tsx
// AFTER
      {isLoading ? (
        <div className="py-10 text-center text-muted-foreground">불러오는 중입니다...</div>
      ) : isError ? (
        <Card>
          <QueryError message="패턴 라이브러리를 불러오지 못했습니다." onRetry={() => refetch()} />
        </Card>
      ) : (
        <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
          {filtered.map(entry => (
            <PatternCard key={entry.pattern_type} entry={entry} />
          ))}
        </div>
      )}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/PatternLibraryPage.tsx
git commit -m "fix: add isError branch to PatternLibraryPage"
```

---

## Task 2: WatchlistPage — error branch per row

**Files:**
- Modify: `frontend/src/pages/WatchlistPage.tsx`

- [ ] **Step 1: Add `QueryError` import**

Add to existing imports:
```tsx
import { QueryError } from '@/components/ui/QueryError'
```

- [ ] **Step 2: Add error branch for `analysisQ` in `WatchlistRow`**

Find and replace the pattern/loading/empty branch inside `WatchlistRow`:
```tsx
// BEFORE
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
        ) : (
          <span className="mt-0.5 block text-xs text-muted-foreground">설명 가능한 패턴이 아직 없습니다</span>
        )}
```
```tsx
// AFTER
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
            onClick={event => { event.stopPropagation(); analysisQ.refetch() }}
            className="mt-0.5 flex items-center gap-1 text-xs text-red-400/70 hover:text-red-400"
          >
            <span>분석 실패 — 재시도</span>
          </button>
        ) : (
          <span className="mt-0.5 block text-xs text-muted-foreground">설명 가능한 패턴이 아직 없습니다</span>
        )}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/WatchlistPage.tsx
git commit -m "fix: add analysisQ error branch in WatchlistPage row"
```

---

## Task 3: PatternPerformancePage — add isError + "내 기록" tab

**Files:**
- Modify: `frontend/src/pages/PatternPerformancePage.tsx`

- [ ] **Step 1: Add new imports**

Add to existing imports at top of file:
```tsx
import { Loader2, Flag } from 'lucide-react'
import { outcomesApi } from '@/lib/api'
import { QueryError } from '@/components/ui/QueryError'
import type { OutcomeRecord, OutcomeStatus } from '@/types/api'
```

Note: `Activity, BarChart2, Clock3, RefreshCw, ShieldCheck, ShieldAlert, Target` are already imported — only add the new ones.

- [ ] **Step 2: Add `isError`/`refetch` to the stats query and add tab state**

Find and replace the query + state block at the top of `PatternPerformancePage`:
```tsx
// BEFORE
  const [timeframe, setTimeframe] = useState<ReportTimeframe>('1d')
  const queryClient = useQueryClient()

  const { data, isLoading } = useQuery({
    queryKey: ['patterns', 'stats'],
    queryFn: patternsApi.stats,
    staleTime: 60_000,
  })
```
```tsx
// AFTER
  const [timeframe, setTimeframe] = useState<ReportTimeframe>('1d')
  const [activeTab, setActiveTab] = useState<'stats' | 'records'>('stats')
  const queryClient = useQueryClient()

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['patterns', 'stats'],
    queryFn: patternsApi.stats,
    staleTime: 60_000,
  })

  const outcomesQ = useQuery({
    queryKey: ['outcomes'],
    queryFn: outcomesApi.list,
    staleTime: 30_000,
    enabled: activeTab === 'records',
  })

  const outcomeUpdateMutation = useMutation({
    mutationFn: ({ id, outcome }: { id: number; outcome: OutcomeStatus }) =>
      outcomesApi.update(id, { outcome }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['outcomes'] }),
  })

  const outcomeDeleteMutation = useMutation({
    mutationFn: (id: number) => outcomesApi.remove(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['outcomes'] }),
  })
```

- [ ] **Step 3: Add tab buttons in the page header area**

Find and replace the page title block:
```tsx
// BEFORE
      <div className="flex items-center gap-3">
        <BarChart2 size={18} className="text-primary" />
        <div>
          <h1 className="text-xl font-bold">패턴 성과 리포트</h1>
          <p className="text-xs text-muted-foreground">
            패턴별 백테스트 우위, 표본 수, 평균 MFE·MAE, 결과 도달 바 수를 타임프레임별로 읽고 어느 패턴을 더 믿을지 판단합니다.
          </p>
        </div>
      </div>
```
```tsx
// AFTER
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-3">
          <BarChart2 size={18} className="text-primary" />
          <div>
            <h1 className="text-xl font-bold">패턴 성과 리포트</h1>
            <p className="text-xs text-muted-foreground">
              패턴별 백테스트 우위, 표본 수, 평균 MFE·MAE, 결과 도달 바 수를 타임프레임별로 읽고 어느 패턴을 더 믿을지 판단합니다.
            </p>
          </div>
        </div>
        <div className="flex gap-1 rounded-lg border border-border bg-card p-1">
          <button
            onClick={() => setActiveTab('stats')}
            className={`rounded-md px-3 py-1.5 text-xs transition-colors ${activeTab === 'stats' ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:text-foreground'}`}
          >
            백테스트 통계
          </button>
          <button
            onClick={() => setActiveTab('records')}
            className={`rounded-md px-3 py-1.5 text-xs transition-colors ${activeTab === 'records' ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:text-foreground'}`}
          >
            내 기록
          </button>
        </div>
      </div>
```

- [ ] **Step 4: Wrap existing stats content in `activeTab === 'stats'` and add `isError` branch**

Find and replace the stats rendering block (the part after the fixed summary/insights cards):
```tsx
// BEFORE
      {isLoading ? (
        <div className="py-10 text-center text-muted-foreground">리포트를 불러오는 중입니다...</div>
      ) : filtered.length === 0 ? (
        <Card className="py-10 text-center text-sm text-muted-foreground">선택한 타임프레임에는 아직 집계된 패턴 통계가 없습니다.</Card>
      ) : (
        <div className="grid grid-cols-1 gap-3 xl:grid-cols-2">
          {filtered.map((item, index) => (
            <PatternStatCard key={`${item.timeframe}-${item.pattern_type}`} item={item} rank={index + 1} />
          ))}
        </div>
      )}
```
```tsx
// AFTER
      {activeTab === 'stats' && (
        <>
          {isLoading ? (
            <div className="py-10 text-center text-muted-foreground">리포트를 불러오는 중입니다...</div>
          ) : isError ? (
            <Card>
              <QueryError message="패턴 통계를 불러오지 못했습니다." onRetry={() => refetch()} />
            </Card>
          ) : filtered.length === 0 ? (
            <Card className="py-10 text-center text-sm text-muted-foreground">선택한 타임프레임에는 아직 집계된 패턴 통계가 없습니다.</Card>
          ) : (
            <div className="grid grid-cols-1 gap-3 xl:grid-cols-2">
              {filtered.map((item, index) => (
                <PatternStatCard key={`${item.timeframe}-${item.pattern_type}`} item={item} rank={index + 1} />
              ))}
            </div>
          )}
        </>
      )}

      {activeTab === 'records' && (
        <OutcomesTab
          records={outcomesQ.data ?? []}
          isLoading={outcomesQ.isLoading}
          isError={outcomesQ.isError}
          onRetry={() => outcomesQ.refetch()}
          onUpdateOutcome={(id, outcome) => outcomeUpdateMutation.mutate({ id, outcome })}
          onDelete={(id) => outcomeDeleteMutation.mutate(id)}
        />
      )}
```

Also wrap the summary + insights + controls cards in `activeTab === 'stats'`:

Find:
```tsx
      <Card className="space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex flex-wrap gap-2">
            {TIMEFRAME_FILTERS.map(option => (
```

Wrap from this Card all the way to the closing `)}` of the summary+insights section:
```tsx
      {activeTab === 'stats' && (
        <>
          <Card className="space-y-4">
            {/* ... existing card content unchanged ... */}
          </Card>

          {summary && (
            <div className="grid grid-cols-1 gap-3 xl:grid-cols-2">
              {/* ... existing InsightCard content unchanged ... */}
            </div>
          )}

          <Card className="space-y-2 border-primary/20 bg-primary/5">
            {/* ... existing 읽는 법 card unchanged ... */}
          </Card>
        </>
      )}
```

- [ ] **Step 5: Add `OutcomesTab` component at the bottom of the file**

Add this entire component after the last function in the file:

```tsx
const OUTCOME_LABELS: Record<string, string> = {
  pending: '대기 중',
  win: '성공',
  loss: '실패',
  stopped_out: '손절',
  cancelled: '취소',
}

const OUTCOME_BADGE_VARIANT: Record<string, 'bullish' | 'warning' | 'muted' | 'neutral' | 'bearish'> = {
  pending: 'muted',
  win: 'bullish',
  loss: 'bearish',
  stopped_out: 'warning',
  cancelled: 'muted',
}

function OutcomesTab({
  records,
  isLoading,
  isError,
  onRetry,
  onUpdateOutcome,
  onDelete,
}: {
  records: OutcomeRecord[]
  isLoading: boolean
  isError: boolean
  onRetry: () => void
  onUpdateOutcome: (id: number, outcome: OutcomeStatus) => void
  onDelete: (id: number) => void
}) {
  const completed = records.filter(r => r.outcome !== 'pending' && r.outcome !== 'cancelled')
  const wins = completed.filter(r => r.outcome === 'win')
  const pending = records.filter(r => r.outcome === 'pending')

  if (isLoading) {
    return (
      <Card className="flex items-center gap-2 py-8 text-sm text-muted-foreground justify-center">
        <Loader2 size={16} className="animate-spin" />
        기록을 불러오는 중입니다...
      </Card>
    )
  }

  if (isError) {
    return (
      <Card>
        <QueryError message="기록을 불러오지 못했습니다." onRetry={onRetry} />
      </Card>
    )
  }

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <SummaryCell icon={<Flag size={14} className="text-primary" />} label="전체 기록" value={`${records.length}건`} />
        <SummaryCell icon={<ShieldCheck size={14} className="text-emerald-300" />} label="성공" value={`${wins.length}건`} />
        <SummaryCell icon={<ShieldAlert size={14} className="text-amber-300" />} label="대기 중" value={`${pending.length}건`} />
        <SummaryCell
          icon={<Activity size={14} className="text-primary" />}
          label="승률"
          value={completed.length > 0 ? `${Math.round((wins.length / completed.length) * 100)}%` : '-'}
        />
      </div>

      {records.length === 0 ? (
        <Card className="py-10 text-center text-sm text-muted-foreground">
          아직 저장된 신호 기록이 없습니다. 차트 화면이나 대시보드 카드에서 신호를 저장해 보세요.
        </Card>
      ) : (
        <div className="space-y-2">
          {records.map(record => (
            <OutcomeRecordCard
              key={record.id}
              record={record}
              onUpdateOutcome={onUpdateOutcome}
              onDelete={onDelete}
            />
          ))}
        </div>
      )}
    </div>
  )
}

function OutcomeRecordCard({
  record,
  onUpdateOutcome,
  onDelete,
}: {
  record: OutcomeRecord
  onUpdateOutcome: (id: number, outcome: OutcomeStatus) => void
  onDelete: (id: number) => void
}) {
  const isFalsePositive = record.notes === 'user_false_positive'

  return (
    <Card className="space-y-2">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-sm font-semibold">{record.symbol_name}</span>
            <span className="font-mono text-xs text-muted-foreground">{record.symbol_code}</span>
            <Badge variant={OUTCOME_BADGE_VARIANT[record.outcome] ?? 'muted'}>
              {isFalsePositive ? '오탐 신고' : (OUTCOME_LABELS[record.outcome] ?? record.outcome)}
            </Badge>
            {record.pattern_type && (
              <Badge variant="muted">{record.pattern_type}</Badge>
            )}
            <Badge variant="muted">{record.timeframe}</Badge>
          </div>
          <div className="mt-0.5 flex flex-wrap gap-3 text-xs text-muted-foreground">
            <span>진입가 {record.entry_price.toLocaleString('ko-KR')}원</span>
            {record.target_price && <span>목표 {record.target_price.toLocaleString('ko-KR')}원</span>}
            {record.stop_price && <span>손절 {record.stop_price.toLocaleString('ko-KR')}원</span>}
            {record.p_up_at_signal != null && <span>당시 상승확률 {Math.round(record.p_up_at_signal * 100)}%</span>}
            <span>저장일 {record.signal_date}</span>
          </div>
        </div>

        <button
          onClick={() => record.id != null && onDelete(record.id)}
          className="shrink-0 rounded p-1 text-xs text-muted-foreground hover:text-red-400"
          title="기록 삭제"
        >
          ✕
        </button>
      </div>

      {record.outcome === 'pending' && !isFalsePositive && (
        <div className="flex flex-wrap gap-1.5">
          {(['win', 'loss', 'stopped_out', 'cancelled'] as OutcomeStatus[]).map(status => (
            <button
              key={status}
              onClick={() => record.id != null && onUpdateOutcome(record.id, status)}
              className={`rounded px-2.5 py-1 text-xs transition-colors border ${
                status === 'win'
                  ? 'border-emerald-400/30 text-emerald-300 hover:bg-emerald-400/10'
                  : status === 'loss'
                    ? 'border-red-400/30 text-red-300 hover:bg-red-400/10'
                    : status === 'stopped_out'
                      ? 'border-amber-400/30 text-amber-300 hover:bg-amber-400/10'
                      : 'border-border text-muted-foreground hover:text-foreground'
              }`}
            >
              {OUTCOME_LABELS[status]}
            </button>
          ))}
        </div>
      )}
    </Card>
  )
}
```

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/PatternPerformancePage.tsx
git commit -m "feat: add isError handling and '내 기록' outcomes tab to PatternPerformancePage"
```

---

## Task 4: ChartPage — "신호 저장" button

**Files:**
- Modify: `frontend/src/pages/ChartPage.tsx`

- [ ] **Step 1: Add mutation imports**

Add to existing imports at top:
```tsx
import { useMutation } from '@tanstack/react-query'
import { Bookmark } from 'lucide-react'
import { outcomesApi } from '@/lib/api'
```

Note: `useQuery` is already imported. Only add `useMutation` and the new icon + api.

- [ ] **Step 2: Add `savedId` state and `saveMutation` to `ChartPage` component body**

Add right after the existing `const watched = ...` line:
```tsx
  const [savedId, setSavedId] = useState<number | null>(null)
  const saveMutation = useMutation({
    mutationFn: () => {
      if (!analysis) return Promise.reject(new Error('no analysis'))
      const bestPattern = analysis.patterns[0]
      return outcomesApi.record({
        symbol_code: symbol!,
        symbol_name: analysis.symbol.name,
        pattern_type: bestPattern?.pattern_type ?? 'no_pattern',
        timeframe,
        signal_date: new Date().toISOString().slice(0, 10),
        entry_price: priceQ.data?.close ?? 0,
        target_price: bestPattern?.target_level ?? null,
        stop_price: bestPattern?.invalidation_level ?? null,
        outcome: 'pending',
        p_up_at_signal: analysis.p_up,
        composite_score_at_signal: analysis.trade_readiness_score ?? 0,
        textbook_similarity_at_signal: analysis.textbook_similarity,
        trade_readiness_at_signal: analysis.trade_readiness_score ?? 0,
      })
    },
    onSuccess: result => setSavedId(result.id),
  })
```

- [ ] **Step 3: Add the save button in the header badges row**

Find the watchlist star button in the JSX (it's the last item in the `flex flex-wrap items-center gap-2` div):
```tsx
// BEFORE — the star button
                  <button
                    onClick={() => {
                      if (!symbol) return
                      if (watched) removeFromWatchlist(symbol)
                      else addToWatchlist({ code: symbol, name: analysis.symbol.name, market: analysis.symbol.market })
                    }}
                    className={cn(
                      'flex items-center gap-1 rounded-md px-2 py-1 text-xs transition-colors',
                      watched
                        ? 'bg-yellow-400/15 text-yellow-400 hover:bg-yellow-400/25'
                        : 'text-muted-foreground hover:bg-yellow-400/10 hover:text-yellow-400',
                    )}
                  >
                    <Star size={12} className={watched ? 'fill-yellow-400' : ''} />
                    {watched ? '관심종목 해제' : '추가'}
                  </button>
```
```tsx
// AFTER — star button stays, save button added after
                  <button
                    onClick={() => {
                      if (!symbol) return
                      if (watched) removeFromWatchlist(symbol)
                      else addToWatchlist({ code: symbol, name: analysis.symbol.name, market: analysis.symbol.market })
                    }}
                    className={cn(
                      'flex items-center gap-1 rounded-md px-2 py-1 text-xs transition-colors',
                      watched
                        ? 'bg-yellow-400/15 text-yellow-400 hover:bg-yellow-400/25'
                        : 'text-muted-foreground hover:bg-yellow-400/10 hover:text-yellow-400',
                    )}
                  >
                    <Star size={12} className={watched ? 'fill-yellow-400' : ''} />
                    {watched ? '관심종목 해제' : '추가'}
                  </button>
                  <button
                    onClick={() => { if (!analysis || savedId != null) return; saveMutation.mutate() }}
                    disabled={savedId != null || saveMutation.isPending || !analysis}
                    className={cn(
                      'flex items-center gap-1 rounded-md px-2 py-1 text-xs transition-colors',
                      savedId != null
                        ? 'bg-primary/15 text-primary'
                        : 'text-muted-foreground hover:bg-primary/10 hover:text-primary disabled:opacity-40',
                    )}
                    title="이 신호를 내 기록에 저장합니다"
                  >
                    <Bookmark size={12} className={savedId != null ? 'fill-primary' : ''} />
                    {savedId != null ? '저장됨' : saveMutation.isPending ? '저장 중...' : '신호 저장'}
                  </button>
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/ChartPage.tsx
git commit -m "feat: add signal save button to ChartPage"
```

---

## Task 5: DashboardCard — bookmark save button

**Files:**
- Modify: `frontend/src/components/dashboard/DashboardCard.tsx`

- [ ] **Step 1: Add new imports**

Add to existing imports:
```tsx
import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { Bookmark } from 'lucide-react'
import { outcomesApi } from '@/lib/api'
```

Note: `MouseEvent` import is already there. Add only `useState`, `useMutation`, `Bookmark`, `outcomesApi`.

- [ ] **Step 2: Add save state and mutation inside `DashboardCard`**

Add right after the `const watched = isWatched(...)` line:
```tsx
  const [savedId, setSavedId] = useState<number | null>(null)
  const saveMutation = useMutation({
    mutationFn: () =>
      outcomesApi.record({
        symbol_code: item.symbol.code,
        symbol_name: item.symbol.name,
        pattern_type: item.pattern_type ?? 'no_pattern',
        timeframe: item.timeframe,
        signal_date: new Date().toISOString().slice(0, 10),
        entry_price: 0,
        target_price: null,
        stop_price: null,
        outcome: 'pending',
        p_up_at_signal: item.p_up,
        composite_score_at_signal: item.trade_readiness_score ?? 0,
        textbook_similarity_at_signal: item.textbook_similarity,
        trade_readiness_at_signal: item.trade_readiness_score ?? 0,
      }),
    onSuccess: result => setSavedId(result.id),
  })
```

- [ ] **Step 3: Add save button beside the star button**

Find the star button block inside `DashboardCard`:
```tsx
          <button
            onClick={toggleWatch}
            className={cn(
              'rounded p-1.5 transition-colors',
              watched ? 'text-yellow-400 hover:text-yellow-300' : 'text-muted-foreground hover:text-yellow-400',
            )}
            title={watched ? '관심종목 해제' : '관심종목 추가'}
          >
            <Star size={14} className={watched ? 'fill-yellow-400' : ''} />
          </button>
```

Replace with (star unchanged, save button added after):
```tsx
          <button
            onClick={toggleWatch}
            className={cn(
              'rounded p-1.5 transition-colors',
              watched ? 'text-yellow-400 hover:text-yellow-300' : 'text-muted-foreground hover:text-yellow-400',
            )}
            title={watched ? '관심종목 해제' : '관심종목 추가'}
          >
            <Star size={14} className={watched ? 'fill-yellow-400' : ''} />
          </button>
          <button
            onClick={event => {
              event.stopPropagation()
              if (savedId != null || saveMutation.isPending) return
              saveMutation.mutate()
            }}
            disabled={savedId != null || saveMutation.isPending}
            className={cn(
              'rounded p-1.5 transition-colors',
              savedId != null ? 'text-primary' : 'text-muted-foreground hover:text-primary disabled:opacity-40',
            )}
            title={savedId != null ? '저장됨' : '신호 저장'}
          >
            <Bookmark size={14} className={savedId != null ? 'fill-primary' : ''} />
          </button>
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/dashboard/DashboardCard.tsx
git commit -m "feat: add signal save bookmark button to DashboardCard"
```

---

## Task 6: AnalysisPanel — "오탐 신고" button

**Files:**
- Modify: `frontend/src/components/chart/AnalysisPanel.tsx`

- [ ] **Step 1: Add new imports to AnalysisPanel**

Add to existing imports:
```tsx
import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { Flag } from 'lucide-react'
import { outcomesApi } from '@/lib/api'
```

- [ ] **Step 2: Change `AnalysisPanel` to accept `symbol` + `timeframe` props and forward to probability card**

Update the props interface:
```tsx
// BEFORE
interface AnalysisPanelProps {
  analysis: AnalysisResult
}

export function AnalysisPanel({ analysis }: AnalysisPanelProps) {
```
```tsx
// AFTER
interface AnalysisPanelProps {
  analysis: AnalysisResult
  symbol?: string
  timeframe?: string
}

export function AnalysisPanel({ analysis, symbol, timeframe }: AnalysisPanelProps) {
```

- [ ] **Step 3: Pass props to the probability card section**

Inside `AnalysisPanel`, find the first `<Card>` which renders the "확률 분석" section and pass analysis+symbol+timeframe to a new sub-component:

Find the entire first Card block:
```tsx
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            {analysis.p_up >= 0.55 ? (
              <TrendingUp size={14} className="text-green-400" />
            ) : analysis.p_down >= 0.55 ? (
              <TrendingDown size={14} className="text-red-400" />
            ) : (
              <Activity size={14} className="text-primary" />
            )}
            확률 분석
            <Badge variant="muted" className="ml-auto">
              {analysis.timeframe_label}
            </Badge>
          </CardTitle>
        </CardHeader>
        {analysis.no_signal_flag ? (
          <div className="space-y-2 text-xs text-muted-foreground">
            <div className="flex items-center gap-2 text-yellow-300">
              <AlertCircle size={14} />
              <span className="font-medium">No Signal</span>
            </div>
            <p>{analysis.no_signal_reason}</p>
            <p>{analysis.reason_summary}</p>
            <div className="rounded-lg border border-amber-400/15 bg-amber-400/5 p-2.5 text-xs leading-relaxed text-amber-100">
              <span className="font-medium">다음 액션:</span> {buildNoSignalAction(analysis)}
            </div>
          </div>
        ) : (
          <div className="space-y-3">
            <ProbBar p_up={analysis.p_up} p_down={analysis.p_down} size="md" />
            <p className="text-xs leading-relaxed text-muted-foreground">{analysis.reason_summary}</p>
          </div>
        )}
      </Card>
```

Replace with a call to a new component:
```tsx
      <ProbabilityCard analysis={analysis} symbol={symbol} timeframe={timeframe} />
```

- [ ] **Step 4: Add `ProbabilityCard` component at the bottom of the file**

Add this new component before the `buildNoSignalAction` function:

```tsx
function ProbabilityCard({
  analysis,
  symbol,
  timeframe,
}: {
  analysis: AnalysisResult
  symbol?: string
  timeframe?: string
}) {
  const [flagged, setFlagged] = useState(false)

  const flagMutation = useMutation({
    mutationFn: () =>
      outcomesApi.record({
        symbol_code: symbol ?? analysis.symbol?.code ?? '',
        symbol_name: analysis.symbol?.name ?? '',
        pattern_type: analysis.patterns[0]?.pattern_type ?? 'no_pattern',
        timeframe: timeframe ?? analysis.timeframe,
        signal_date: new Date().toISOString().slice(0, 10),
        entry_price: 0,
        target_price: null,
        stop_price: null,
        outcome: 'cancelled',
        notes: 'user_false_positive',
        p_up_at_signal: analysis.p_up,
        textbook_similarity_at_signal: analysis.textbook_similarity,
        trade_readiness_at_signal: analysis.trade_readiness_score ?? 0,
      }),
    onSuccess: () => setFlagged(true),
  })

  const canFlag = analysis.patterns.length > 0 && !analysis.no_signal_flag

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          {analysis.p_up >= 0.55 ? (
            <TrendingUp size={14} className="text-green-400" />
          ) : analysis.p_down >= 0.55 ? (
            <TrendingDown size={14} className="text-red-400" />
          ) : (
            <Activity size={14} className="text-primary" />
          )}
          확률 분석
          <Badge variant="muted" className="ml-auto">
            {analysis.timeframe_label}
          </Badge>
          {canFlag && (
            <button
              onClick={() => { if (!flagged) flagMutation.mutate() }}
              disabled={flagged || flagMutation.isPending}
              className={cn(
                'flex items-center gap-1 rounded px-2 py-0.5 text-[11px] transition-colors',
                flagged
                  ? 'text-amber-300'
                  : 'text-muted-foreground hover:text-amber-300 disabled:opacity-40',
              )}
              title="이 패턴은 오탐으로 보입니다 — 기록에 남겨 알고리즘 개선에 활용합니다"
            >
              <Flag size={11} className={flagged ? 'fill-amber-300' : ''} />
              {flagged ? '신고됨' : '오탐 신고'}
            </button>
          )}
        </CardTitle>
      </CardHeader>
      {analysis.no_signal_flag ? (
        <div className="space-y-2 text-xs text-muted-foreground">
          <div className="flex items-center gap-2 text-yellow-300">
            <AlertCircle size={14} />
            <span className="font-medium">No Signal</span>
          </div>
          <p>{analysis.no_signal_reason}</p>
          <p>{analysis.reason_summary}</p>
          <div className="rounded-lg border border-amber-400/15 bg-amber-400/5 p-2.5 text-xs leading-relaxed text-amber-100">
            <span className="font-medium">다음 액션:</span> {buildNoSignalAction(analysis)}
          </div>
        </div>
      ) : (
        <div className="space-y-3">
          <ProbBar p_up={analysis.p_up} p_down={analysis.p_down} size="md" />
          <p className="text-xs leading-relaxed text-muted-foreground">{analysis.reason_summary}</p>
        </div>
      )}
    </Card>
  )
}
```

- [ ] **Step 5: Update ChartPage to pass `symbol` and `timeframe` to AnalysisPanel**

In `ChartPage.tsx`, find:
```tsx
            <AnalysisPanel analysis={analysis} />
```
Replace with:
```tsx
            <AnalysisPanel analysis={analysis} symbol={symbol} timeframe={timeframe} />
```

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/chart/AnalysisPanel.tsx frontend/src/pages/ChartPage.tsx
git commit -m "feat: add false-positive flag button to AnalysisPanel"
```

---

## Task 7: Build check + push

- [ ] **Step 1: Run TypeScript build check**

```bash
cd frontend && npx tsc --noEmit 2>&1 | head -60
```

Expected: no errors. If type errors appear, fix them (they'll be obvious — missing props, wrong type names).

- [ ] **Step 2: Push to trigger Vercel redeploy**

```bash
cd .. && git push origin main
```

Expected output includes `main -> main`.

- [ ] **Step 3: Verify Vercel deployment**

Wait ~2 minutes, then open https://frontend-mu-sooty-i4662dxm4r.vercel.app and confirm:
- PatternLibraryPage loads without infinite spinner when backend is slow
- PatternPerformancePage shows both tabs
- DashboardCard shows bookmark icon

---

## Self-Review Checklist

- [x] **Spec coverage**: Task 1 ✓ PatternLibraryPage, Task 2 ✓ WatchlistPage, Task 3 ✓ PatternPerformancePage isError + outcomes tab, Task 4 ✓ ChartPage save button, Task 5 ✓ DashboardCard save button, Task 6 ✓ AnalysisPanel flag button
- [x] **No placeholders**: All steps have complete code blocks
- [x] **Type consistency**: `OutcomeRecord`, `OutcomeStatus` used consistently everywhere; `outcomesApi.record()` / `.update()` / `.remove()` match api.ts signatures; `setSavedId(result.id)` matches `{ id: number }` return type from `outcomesApi.record()`
- [x] **`outcomesApi` already in api.ts** — no new API wiring needed
- [x] **`OutcomeRecord`/`OutcomeStatus` already in types/api.ts** — no new type declarations needed
- [x] **ScreenerPage already fixed** (lines 755-759 already have isError+QueryError) — correctly excluded from this plan
