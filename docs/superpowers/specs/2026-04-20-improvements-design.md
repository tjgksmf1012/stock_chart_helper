# Stock Chart Helper — Frontend Improvements Design
**Date:** 2026-04-20  
**Scope:** Three independent frontend improvements; no backend changes required.

---

## 1. Complete Infinite Loading Fixes

### Problem
Four pages still have incomplete error handling from the previous session:
- `ScreenerPage.tsx` — `isError` destructured but JSX not updated
- `PatternPerformancePage.tsx` — `isError` missing from `useQuery` destructuring
- `PatternLibraryPage.tsx` — unknown state, needs audit
- `WatchlistPage.tsx` — unknown state, needs audit

### Design
- Add `isError` + `refetch` to every `useQuery` call that doesn't have them
- Wrap existing loading spinner blocks with an `isError` branch that renders `<QueryError compact onRetry={refetch} />`
- Pattern: `{isLoading ? <spinner> : isError ? <QueryError> : <content>}`
- Use the existing `QueryError` component (`frontend/src/components/ui/QueryError.tsx`) — no new UI needed

---

## 2. Signal Save Workflow (Outcomes)

### Problem
Backend `/outcomes` CRUD API is 100% complete (`backend/app/api/routes/outcomes.py`), but there is zero frontend integration. Users cannot save, view, or close out signals.

### Design

#### 2a. Save button — ChartPage
- Small "신호 저장" button in the header area (next to the watchlist star)
- On click: opens a compact inline form (no modal) pre-filled from `analysis` data:
  - symbol, pattern_type, timeframe, entry_price (current close from `priceQ`), target_price, stop_price, p_up_at_signal, trade_readiness_at_signal
- Submit → `POST /outcomes` → show a brief success toast ("저장됐습니다")
- Button becomes "저장됨 ✓" (disabled) for that analysis session

#### 2b. Save button — DashboardCard
- Small bookmark icon button beside the star watchlist button
- Same one-click save using item's analysis data
- Shows saved state visually (filled bookmark icon)

#### 2c. Outcomes tab — PatternPerformancePage
- Add a second tab: "백테스트 통계" (existing) + "내 기록" (new)
- "내 기록" tab fetches `GET /outcomes` and shows:
  - Summary row: total saved, pending, wins, losses, win_rate
  - List of OutcomeRecord cards with status badge (pending/win/loss/stopped_out)
  - Each card has inline controls: "성공" / "실패" / "손절" / "취소" → `PATCH /outcomes/:id`

#### 2d. API wiring
- Add `outcomesApi` to `frontend/src/lib/api.ts`:
  - `create(record)` → `POST /outcomes`
  - `list()` → `GET /outcomes`
  - `update(id, update)` → `PATCH /outcomes/:id`
  - `summary()` → `GET /outcomes/summary`
- Add TypeScript types for `OutcomeRecord` and `OutcomeUpdate` to `frontend/src/types/api.ts`

---

## 3. False Positive Flagging

### Problem
When a pattern looks wrong to the user ("이건 아닌데"), there's no way to record it. This data is the seed for algorithm calibration.

### Design
- Add a small "오탐 신고" button on `AnalysisPanel.tsx` in the "확률 분석" card (only shown when a pattern exists and state is not `no_signal`)
- On click: immediately calls `POST /outcomes` with:
  - `outcome: "cancelled"`
  - `notes: "user_false_positive"`
  - snapshot scores at time of flag
- Shows "신고됨" confirmation inline (no toast)
- These records appear in the "내 기록" tab with a distinct badge: "오탐 신고"

---

## Out of Scope
- Backend changes (all existing APIs are sufficient)
- Explainability improvements (already well-covered by existing AnalysisPanel cards)
- Intraday infrastructure (pykrx Korean IP limitation is server-level, not UI-solvable)
- Automated outcome resolution (requires price data polling; future work once records accumulate)

---

## Files to Change

| File | Change |
|------|--------|
| `frontend/src/lib/api.ts` | Add `outcomesApi` |
| `frontend/src/types/api.ts` | Add `OutcomeRecord`, `OutcomeUpdate`, `OutcomesSummary` types |
| `frontend/src/pages/ScreenerPage.tsx` | Add isError branch in JSX |
| `frontend/src/pages/PatternPerformancePage.tsx` | Add isError + "내 기록" tab |
| `frontend/src/pages/PatternLibraryPage.tsx` | Add isError branch |
| `frontend/src/pages/WatchlistPage.tsx` | Add isError branches |
| `frontend/src/pages/ChartPage.tsx` | Add "신호 저장" button |
| `frontend/src/components/chart/AnalysisPanel.tsx` | Add "오탐 신고" button |
| `frontend/src/components/dashboard/DashboardCard.tsx` | Add save bookmark button |
