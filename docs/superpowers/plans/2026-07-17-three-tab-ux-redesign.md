# 3-탭 여정 재편 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 내비 9개 페이지를 오늘/분석/기록 3탭 여정으로 재편하고, 검증된 실험실 신호를 홈 최상단으로 승격한다.

**Architecture:** 프론트엔드 전용 리팩터링(백엔드 API 변경 없음). Layout이 3탭+유틸 아이콘을 렌더하고, 분석/기록은 서브탭 셸(AnalysisShell/JournalShell)이 기존 페이지를 `<Outlet/>`으로 감싼다. 신설 TodayPage는 기존 대시보드의 데이터 훅과 lib 헬퍼(dashboardDecks 등)를 재사용하되 화면은 5개 섹션으로 압축한다. 순수 로직(관찰 후보 통합·중복 제거)은 `lib/observationDeck.ts`로 분리해 vitest로 TDD한다.

**Tech Stack:** React 18 + react-router-dom 6 + TanStack Query 5 + Tailwind + vitest (기존 그대로)

**Verification:** 프론트 컴포넌트는 `npx tsc --noEmit` + 브라우저 QA로 검증. 순수 lib 로직만 vitest TDD. 명령은 전부 `frontend/` 디렉토리에서 실행.

**참고 — 기존 코드 위치:**
- 대시보드 데이터 훅·덱 빌더: `frontend/src/pages/DashboardPage.tsx:77-320` (overviewQ/statusQ/outcomesQ/regimeQ, buildFocusDeck/buildWatchlistDeck, filterDashboard)
- 신호 게이트 UI: `frontend/src/pages/LabPage.tsx:118-284` (suggestShares, loadSizingConfig, LiveSignals)
- 판정 카드: `frontend/src/pages/LabPage.tsx:286-380` (ReportCard, Metric, signedPct, ratioVsRandom)
- 라우팅: `frontend/src/main.tsx:60-74`

---

### Task 1: 관찰 후보 통합 로직 (lib, TDD)

여러 대시보드 섹션을 하나로 합치며 종목 중복을 제거하는 순수 함수.

**Files:**
- Create: `frontend/src/lib/observationDeck.ts`
- Test: `frontend/src/lib/observationDeck.test.ts`

- [ ] **Step 1: 실패하는 테스트 작성**

```ts
// frontend/src/lib/observationDeck.test.ts
import { describe, expect, it } from 'vitest'

import { buildObservationDeck } from './observationDeck'
import type { DashboardItem, DashboardResponse } from '@/types/api'

function makeItem(code: string, overrides: Partial<DashboardItem> = {}): DashboardItem {
  return {
    symbol: { code, name: `종목${code}` },
    timeframe: 'D',
    pattern_type: 'double_bottom',
    setup_stage: 'late_base',
    p_up: 0.6,
    trade_readiness_score: 0.7,
    action_priority_score: 0.5,
    ...overrides,
  } as unknown as DashboardItem
}

function wrap(items: DashboardItem[]): DashboardResponse {
  return { items } as unknown as DashboardResponse
}

describe('buildObservationDeck', () => {
  it('여러 섹션을 합치되 같은 종목은 한 번만 남긴다 (먼저 온 섹션 우선)', () => {
    const deck = buildObservationDeck({
      armed: wrap([makeItem('005930')]),
      long: wrap([makeItem('005930', { p_up: 0.99 }), makeItem('000660')]),
      forming: wrap([makeItem('000660'), makeItem('035420')]),
    })
    expect(deck.items.map(i => i.symbol.code)).toEqual(['005930', '000660', '035420'])
    // armed 섹션의 005930이 이겨야 한다 (p_up 0.6 쪽)
    expect(deck.items[0].p_up).toBe(0.6)
  })

  it('임박(armed) 카운트와 고유 종목 수를 요약한다', () => {
    const deck = buildObservationDeck({
      armed: wrap([makeItem('A'), makeItem('B')]),
      long: wrap([makeItem('B'), makeItem('C')]),
    })
    expect(deck.uniqueCount).toBe(3)
    expect(deck.armedCount).toBe(2)
  })

  it('빈 입력은 빈 덱', () => {
    const deck = buildObservationDeck({})
    expect(deck.items).toEqual([])
    expect(deck.uniqueCount).toBe(0)
  })

  it('undefined 섹션은 건너뛴다', () => {
    const deck = buildObservationDeck({ armed: undefined, long: wrap([makeItem('A')]) })
    expect(deck.uniqueCount).toBe(1)
  })
})
```

- [ ] **Step 2: 실패 확인** — Run: `npx vitest run src/lib/observationDeck.test.ts` → Expected: FAIL (module not found)

- [ ] **Step 3: 최소 구현**

```ts
// frontend/src/lib/observationDeck.ts
import type { DashboardItem, DashboardResponse } from '@/types/api'

/**
 * 대시보드의 여러 후보 섹션을 "관찰 후보" 단일 덱으로 합친다.
 * 같은 종목이 여러 섹션에 나오면 먼저 온 섹션(호출부가 우선순위 순서로 전달)이 이긴다.
 * 섹션 키 순서: armed(완성 임박) → long(지금 볼) → live → forming → sim → short → nosig
 */
export interface ObservationDeck {
  items: DashboardItem[]
  uniqueCount: number
  armedCount: number
}

export function buildObservationDeck(
  sections: Partial<Record<'armed' | 'long' | 'live' | 'forming' | 'sim' | 'short' | 'nosig', DashboardResponse | undefined>>,
): ObservationDeck {
  const order: Array<keyof typeof sections> = ['armed', 'long', 'live', 'forming', 'sim', 'short', 'nosig']
  const seen = new Set<string>()
  const items: DashboardItem[] = []
  let armedCount = 0

  for (const key of order) {
    for (const item of sections[key]?.items ?? []) {
      const code = item.symbol.code
      if (seen.has(code)) continue
      seen.add(code)
      items.push(item)
      if (key === 'armed') armedCount += 1
    }
  }
  return { items, uniqueCount: items.length, armedCount }
}
```

- [ ] **Step 4: 통과 확인** — Run: `npx vitest run src/lib/observationDeck.test.ts` → Expected: PASS (4 tests)
- [ ] **Step 5: 기존 lib 테스트 회귀 확인** — Run: `npx vitest run` → Expected: 전부 PASS
- [ ] **Step 6: Commit** — `git add frontend/src/lib/observationDeck.* && git commit -m "feat(ux): 관찰 후보 통합 덱 빌더 (중복 제거, TDD)"`

---

### Task 2: LiveSignals 컴포넌트 추출

LabPage 안의 신호 게이트 UI를 재사용 가능한 컴포넌트로 이동한다 (오늘 탭 + 전략 검증 페이지 양쪽에서 사용).

**Files:**
- Create: `frontend/src/components/lab/LiveSignals.tsx`
- Modify: `frontend/src/pages/LabPage.tsx`

- [ ] **Step 1: 파일 이동** — `LabPage.tsx:118-284`의 `suggestShares`, `SIZING_STORAGE_KEY`, `loadSizingConfig`, `LiveSignals`를 그대로 `components/lab/LiveSignals.tsx`로 옮기고 `export function LiveSignals`, 신호용 배지 설정도 함께 이동:

```tsx
// frontend/src/components/lab/LiveSignals.tsx 상단
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Zap } from 'lucide-react'

import { Card } from '@/components/ui/Card'
import { QueryError } from '@/components/ui/QueryError'
import { cn, fmtDateTime, fmtPrice } from '@/lib/utils'
import type { LabSignal } from '@/types/api'

export const SIGNAL_VERDICT_BADGE: Record<string, { label: string; badge: string }> = {
  pass: { label: '통과', badge: 'border-emerald-400/30 bg-emerald-400/10 text-emerald-300' },
  watch: { label: '관찰', badge: 'border-amber-400/30 bg-amber-400/10 text-amber-300' },
  fail: { label: '탈락', badge: 'border-red-400/30 bg-red-400/10 text-red-300' },
}
```
(함수 본문은 LabPage에서 그대로 복사 — `VERDICT_CFG[sig.verdict]` 참조만 `SIGNAL_VERDICT_BADGE[sig.verdict ?? 'watch'] ?? SIGNAL_VERDICT_BADGE.watch`로 변경.)

- [ ] **Step 2: LabPage에서 import로 교체** — LabPage에서 옮긴 코드 삭제, `import { LiveSignals } from '@/components/lab/LiveSignals'` 추가. LabPage의 `VERDICT_CFG`는 ReportCard용으로 유지.
- [ ] **Step 3: 검증** — Run: `npx tsc --noEmit` → Expected: 에러 0. 브라우저 `/lab`에서 신호 테이블 렌더 확인.
- [ ] **Step 4: Commit** — `git commit -m "refactor(ux): LiveSignals를 재사용 컴포넌트로 추출"`

---

### Task 3: 셸 + 라우팅 골격 (3탭 Layout, AnalysisShell, JournalShell, 리다이렉트)

**Files:**
- Modify: `frontend/src/components/Layout.tsx`
- Create: `frontend/src/components/shell/SubTabs.tsx`
- Create: `frontend/src/pages/journal/JournalRecordsPage.tsx` (임시 골격 → Task 5에서 채움)
- Create: `frontend/src/pages/journal/JournalPaperPage.tsx` (임시 골격 → Task 5에서 채움)
- Create: `frontend/src/pages/journal/JournalStrategiesPage.tsx`
- Modify: `frontend/src/main.tsx`

- [ ] **Step 1: SubTabs 공용 컴포넌트**

```tsx
// frontend/src/components/shell/SubTabs.tsx
import { NavLink, Outlet } from 'react-router-dom'
import { cn } from '@/lib/utils'

export interface SubTab {
  to: string
  label: string
  end?: boolean
}

/** 분석/기록 탭 공용 서브탭 셸 — 기존 라우트를 그대로 Outlet으로 렌더한다. */
export function SubTabs({ tabs }: { tabs: SubTab[] }) {
  return (
    <div className="space-y-5">
      <nav className="flex items-center gap-1 overflow-x-auto rounded-lg border border-border bg-card/60 p-1">
        {tabs.map(tab => (
          <NavLink
            key={tab.to}
            to={tab.to}
            end={tab.end ?? true}
            className={({ isActive }) =>
              cn(
                'whitespace-nowrap rounded-md px-3 py-1.5 text-xs font-medium transition-colors',
                isActive ? 'bg-primary/15 text-primary' : 'text-muted-foreground hover:text-foreground',
              )
            }
          >
            {tab.label}
          </NavLink>
        ))}
      </nav>
      <Outlet />
    </div>
  )
}
```

- [ ] **Step 2: JournalStrategiesPage** — 기존 LabPage 내용을 그대로 씀 (LiveSignals 제외: 신호는 오늘 탭이 주인, 여기는 판정 기록만):

```tsx
// frontend/src/pages/journal/JournalStrategiesPage.tsx
// LabPage에서 reportsQ/paperQ + ReportCard/Metric/VERDICT_CFG/UNIVERSE_LABELS/DRIFT_CFG/
// signedPct/ratioVsRandom + "읽기 전 주의" 카드를 이 파일로 이동.
// LiveSignals 호출부와 signalsQ는 가져오지 않는다 (오늘 탭으로 승격됨).
// 헤더 문구는 유지: "전략 실험실 — 모든 전략은 같은 저울로 잽니다..."
export default function JournalStrategiesPage() { /* LabPage 본문에서 LiveSignals 부분만 뺀 것 */ }
```

- [ ] **Step 3: Journal 골격 페이지 2개** (Task 5에서 완성 — 골격도 실제 내용의 자리만 잡고 placeholder 문구는 쓰지 않는다):

```tsx
// frontend/src/pages/journal/JournalRecordsPage.tsx (골격)
export default function JournalRecordsPage() {
  return <div className="space-y-6" data-page="journal-records" />
}
// frontend/src/pages/journal/JournalPaperPage.tsx (골격)
export default function JournalPaperPage() {
  return <div className="space-y-6" data-page="journal-paper" />
}
```

- [ ] **Step 4: Layout 3탭 + 유틸 아이콘** — `NAV_ITEMS`를 교체하고 우측에 아이콘 2개:

```tsx
// Layout.tsx 교체 요점
import { useLocation } from 'react-router-dom'
import { BarChart2, CalendarCheck, LineChart, NotebookPen, ServerCog, Star } from 'lucide-react'

const TABS = [
  { to: '/', label: '오늘', icon: CalendarCheck, match: (p: string) => p === '/' },
  {
    to: '/chart', label: '분석', icon: LineChart,
    match: (p: string) => ['/chart', '/screener', '/watchlist', '/library', '/reference-charts'].some(x => p.startsWith(x)),
  },
  {
    to: '/journal', label: '기록', icon: NotebookPen,
    match: (p: string) => ['/journal', '/reports', '/lab'].some(x => p.startsWith(x)),
  },
]
// 렌더: const { pathname } = useLocation(); TABS.map(tab => <NavLink ... className={cn(base, tab.match(pathname) ? active : idle)}>)
// 우측 유틸: <NavLink to="/watchlist" title="관심종목"><Star size={15}/>{watchlist.length > 0 && 배지}</NavLink>
//            <NavLink to="/system" title="시스템 상태"><ServerCog size={15}/></NavLink>
// 탭 폰트는 text-sm으로 키운다 (3개뿐이므로). 모바일 mask-image 힌트는 제거해도 잘림이 없다.
```

- [ ] **Step 5: 라우팅 재편** — `main.tsx`의 Routes를:

```tsx
import { Navigate } from 'react-router-dom'
// lazy 추가: TodayPage(임시로 DashboardPage 유지 — Task 4에서 교체), JournalRecordsPage, JournalPaperPage, JournalStrategiesPage
// SubTabs는 lazy 불필요 (Layout과 함께 로드)

<Route path="/" element={<Layout />}>
  <Route index element={<DashboardPage />} /> {/* Task 4에서 TodayPage로 교체 */}
  <Route path="ai" element={<Navigate to="/" replace />} />
  <Route
    element={<SubTabs tabs={[
      { to: '/chart', label: '차트', end: false },
      { to: '/screener', label: '종목 필터' },
      { to: '/watchlist', label: '관심종목' },
      { to: '/library', label: '패턴 사전' },
    ]} />}
  >
    <Route path="chart" element={<ChartPage />} />
    <Route path="chart/:symbol" element={<ChartPage />} />
    <Route path="screener" element={<ScreenerPage />} />
    <Route path="watchlist" element={<WatchlistPage />} />
    <Route path="library" element={<PatternLibraryPage />} />
  </Route>
  <Route
    element={<SubTabs tabs={[
      { to: '/journal', label: '내 기록' },
      { to: '/journal/paper', label: '실측 (종이매매)' },
      { to: '/journal/strategies', label: '전략 검증' },
      { to: '/reports/patterns', label: '패턴 적중률' },
    ]} />}
  >
    <Route path="journal" element={<JournalRecordsPage />} />
    <Route path="journal/paper" element={<JournalPaperPage />} />
    <Route path="journal/strategies" element={<JournalStrategiesPage />} />
    <Route path="reports/patterns" element={<PatternPerformancePage />} />
  </Route>
  <Route path="lab" element={<Navigate to="/journal/strategies" replace />} />
  <Route path="reference-charts" element={<ReferenceChartsPage />} />
  <Route path="system" element={<SystemStatusPage />} />
</Route>
// AiRecommendationsPage lazy import 삭제. LabPage lazy import 삭제.
```

- [ ] **Step 6: LabPage 파일 삭제** — 내용이 JournalStrategiesPage로 이동 완료된 후 `git rm frontend/src/pages/LabPage.tsx`.
- [ ] **Step 7: 검증** — `npx tsc --noEmit` 에러 0. 브라우저에서: 상단 탭 3개 렌더, `/lab` → `/journal/strategies` 리다이렉트, `/screener` 진입 시 분석 탭 활성 + 서브탭 표시.
- [ ] **Step 8: Commit** — `git commit -m "feat(ux): 3탭 셸 + 서브탭 + 리다이렉트 라우팅"`

---

### Task 4: TodayPage — 검증된 신호 승격 + 오늘 확인할 것 + 스캔 스트립

**Files:**
- Create: `frontend/src/pages/TodayPage.tsx`
- Modify: `frontend/src/main.tsx` (index 라우트 교체)

- [ ] **Step 1: TodayPage 작성** — DashboardPage에서 필요한 훅만 가져온다:

```tsx
// frontend/src/pages/TodayPage.tsx — 구조 (데이터 훅은 DashboardPage 것을 그대로 복사)
export default function TodayPage() {
  // 유지하는 훅: regimeQ, statusQ(폴링 로직 포함), overviewQ, outcomesQ,
  //   triggerScan/cancelScan/자동 스캔 effect (DashboardPage:152-195 그대로),
  //   sections/allDashboardItems/watchlistDeck (dashboardDecks 재사용)
  // 새 훅: signalsQ + paperQ 없이 signalsQ만 (LabPage:51-57의 refetchInterval 로직 그대로)
  // 버리는 훅: sectorQ 제외한 routine/kisPrime/snapshot 관련 전부
  return (
    <div className="space-y-5">
      {/* 1. 시장 체제: <MarketRegimeBar data={regimeQ.data}/> + regimeWarning + data_source_note 배너 (DashboardPage:325-344 그대로) */}
      {/* 2. 검증된 신호: <LiveSignals loading=... signals=... /> — LabPage:75-82와 동일한 프롭 배선 */}
      {/* 3. 오늘 확인할 것: <TodayChecklist .../> */}
      {/* 4. 관찰 후보: Task 5에서 <ObservationSection/> 추가 */}
      {/* 5. 스캔 스트립: <ScanStrip status={statusQ.data} onTrigger={triggerScan} onCancel={cancelScan} isTriggering={...}/> */}
    </div>
  )
}
```

- [ ] **Step 2: TodayChecklist 섹션** (같은 파일 내 비공개 컴포넌트):

```tsx
function TodayChecklist({ pending, watchTrigger, watchRisk, onOpenChart }: {
  pending: OutcomeRecord[]           // outcomesQ에서 outcome==='pending' 필터 (타임프레임 무관, 최대 5)
  watchTrigger: DashboardItem[]      // watchlistDeck.triggerClose
  watchRisk: DashboardItem[]         // watchlistDeck.riskClose
  onOpenChart: (code: string) => void
}) {
  const isEmpty = pending.length === 0 && watchTrigger.length === 0 && watchRisk.length === 0
  return (
    <Card className="space-y-3">
      <div className="text-sm font-semibold">오늘 확인할 것</div>
      {isEmpty && <p className="text-xs text-muted-foreground">지금 처리할 항목이 없습니다. 검증된 신호와 관찰 후보만 보면 됩니다.</p>}
      {/* 행 3종: 
          watchTrigger → <Row icon={Bell} tone="amber" text={`관심종목 ${names}이(가) 트리거 가격에 근접`} onClick=차트로/>
          watchRisk → <Row icon={ShieldAlert} tone="red" text={`관심종목 ${names} 손절 기준가 확인 필요`}/>
          pending → <Row icon={Clock} tone="muted" text={`${r.symbol_name} 판단 기록이 미정리 — 기록 탭에서 닫기`} onClick={() => nav('/journal')}/> */}
    </Card>
  )
}
```
(조사 처리는 기존 `lib/josa` 유틸 사용 — 파일명은 실행 시 확인.)

- [ ] **Step 3: ScanStrip** (같은 파일 내): 실행 중일 때 — 진행 바 한 줄 + `n / m종목` + 취소 링크 (DashboardPage:488-519의 클램프·cancel_requested 로직 유지). 대기 중일 때 — `마지막 스캔 {fmtDateTime(last_finished_at)} · 캐시 {n}개` + [빠른 갱신] 텍스트 버튼. `text-xs` 단일 행 Card.
- [ ] **Step 4: 라우트 교체** — main.tsx index를 `<TodayPage />`로. DashboardPage lazy import는 아직 유지 (Task 5에서 삭제).
- [ ] **Step 5: 검증** — `npx tsc --noEmit`, 브라우저 `/`: 신호 카드가 최상단 근처, 계산 중이면 "계산하는 중..." 표시, 스캔 스트립 동작.
- [ ] **Step 6: Commit** — `git commit -m "feat(ux): 오늘 탭 — 검증된 신호 승격 + 오늘 확인할 것 + 스캔 스트립"`

---### Task 5: 관찰 후보 섹션 (접힘 + 카드 다이어트) + 기록 탭 내용 채우기 + 구 페이지 삭제

**Files:**
- Create: `frontend/src/components/today/ObservationSection.tsx`
- Modify: `frontend/src/pages/TodayPage.tsx`
- Modify: `frontend/src/pages/journal/JournalRecordsPage.tsx`, `JournalPaperPage.tsx`
- Delete: `frontend/src/pages/DashboardPage.tsx`, `frontend/src/pages/AiRecommendationsPage.tsx`
- Create(이동): `frontend/src/components/journal/PendingDecisions.tsx`, `frontend/src/components/journal/PerformanceSummary.tsx`

- [ ] **Step 1: ObservationSection** — 접힌 상태가 기본. 헤더: `관찰 후보 (차트 패턴) — 고유 N종목 · 완성 임박 M` + 우측 정직 라벨 `검증 엣지 얇음(+0.7%/거래) · 참고용`. 펼치면: 타임프레임 셀렉트(TIMEFRAME_OPTIONS) + 정렬 셀렉트(완성 임박순=armed 우선 그대로 / 상승확률순=p_up desc) + CompactCandidateCard 그리드(2열) + SectorHeatmap(sectorQ 데이터 있으면):

```tsx
function CompactCandidateCard({ item, onOpen }: { item: DashboardItem; onOpen: () => void }) {
  const uniqueLine = item.trend_warning || item.wyckoff_note || item.next_trigger || null
  return (
    <button onClick={onOpen} className="rounded-lg border border-border bg-card/60 p-3 text-left transition-colors hover:border-primary/30">
      <div className="flex items-center justify-between gap-2">
        <span className="text-sm font-medium">{item.symbol.name}</span>
        <span className="font-mono text-[11px] text-muted-foreground">{item.symbol.code}</span>
      </div>
      <div className="mt-1 flex flex-wrap items-center gap-1.5 text-[11px]">
        <Badge variant="muted">{PATTERN_NAMES[item.pattern_type ?? ''] ?? item.pattern_type ?? '패턴 없음'}</Badge>
        <span className="text-muted-foreground">{item.setup_stage_label ?? item.setup_stage}</span>
      </div>
      <div className="mt-2 flex gap-4 text-xs">
        <span>상승 <b className="tabular-nums">{fmtPct(item.p_up, 0)}</b></span>
        <span>준비 <b className="tabular-nums">{fmtPct(item.trade_readiness_score, 0)}</b></span>
      </div>
      {uniqueLine && <p className="mt-2 line-clamp-2 text-[11px] leading-relaxed text-muted-foreground">{uniqueLine}</p>}
    </button>
  )
}
```
공통 보일러플레이트(`action_plan_summary`, `next_trigger` 기본 문구, 실전 판단 문단)는 렌더하지 않는다 — 그것이 다이어트의 본체. `setup_stage_label`이 타입에 없으면 setup_stage 원문 사용 (실행 시 타입 확인).

- [ ] **Step 2: TodayPage에 배선** — `buildObservationDeck({ armed: sections.armedData, long: sections.longData, live: sections.liveData, forming: sections.formingData, sim: sections.simData, short: sections.shortData, nosig: sections.noSigData })`. 접힘 토글은 `useState(false)` + localStorage `'today-observation-open'` 기억.
- [ ] **Step 3: 기록 탭 — 내 기록** — DashboardPage의 `PendingDecisionDesk`(미정리 판단, :650-659 배선)와 `PersonalPerformanceDesk`(:661)를 `components/journal/`로 이동해 JournalRecordsPage에서 조립. 타임프레임 필터는 제거(전체 표시). 관련 훅(outcomesQ, outcomesSummaryQ, update/evaluate mutation)도 함께 이동.
- [ ] **Step 4: 기록 탭 — 실측** — JournalPaperPage: `labApi.paperTradesSummary` 쿼리, 전략별 행: 라벨, 실측 n건/EV, 진행중 n건, 드리프트 배지(DRIFT_CFG 재사용 — JournalStrategiesPage에서 export), drifting이면 경고 문장. 설명 헤더: "신호가 나올 때마다 자동으로 종이매매로 기록하고, 백테스트와 같은 규칙으로 청산해 실측 성적을 만듭니다."
- [ ] **Step 5: 구 페이지 삭제** — `git rm frontend/src/pages/DashboardPage.tsx frontend/src/pages/AiRecommendationsPage.tsx` + main.tsx에서 lazy import 제거. 이 시점에 깨지는 참조(FocusColumn 등 페이지 내부 컴포넌트, RoutineRow, buildFocusDeck/buildRoutineDeck 사용처)를 확인: `lib/dashboardDecks.ts`의 buildFocusDeck/buildRoutineDeck/routineActionText/uniqueRoutineSymbols와 `lib/dashboardSnapshot.ts`, `lib/dashboardSummary.ts`, `lib/intradayFilters.ts` 중 더 이상 사용처가 없는 export는 해당 테스트와 함께 삭제 (grep으로 사용처 0 확인 후).
- [ ] **Step 6: 검증** — `npx tsc --noEmit` + `npx vitest run` 전부 PASS. 브라우저: `/` 관찰 후보 접힘/펼침·중복 없음, `/journal` 내 기록, `/journal/paper` 실측, `/ai` 리다이렉트.
- [ ] **Step 7: Commit** — `git commit -m "feat(ux): 관찰 후보 통합 섹션 + 기록 탭 완성 + 구 대시보드/추천 페이지 제거"`

---

### Task 6: 차트 페이지 정리 (핵심 위, 참고 아코디언)

**Files:**
- Create: `frontend/src/components/ui/Collapsible.tsx`
- Modify: `frontend/src/pages/ChartPage.tsx`

- [ ] **Step 1: Collapsible 공용 컴포넌트**

```tsx
// frontend/src/components/ui/Collapsible.tsx
import { useState, type ReactNode } from 'react'
import { ChevronDown } from 'lucide-react'
import { Card } from '@/components/ui/Card'
import { cn } from '@/lib/utils'

export function Collapsible({ title, summary, defaultOpen = false, children }: {
  title: string
  summary?: string   // 접혀 있을 때 한 줄 요약
  defaultOpen?: boolean
  children: ReactNode
}) {
  const [open, setOpen] = useState(defaultOpen)
  return (
    <Card className="space-y-3">
      <button onClick={() => setOpen(v => !v)} className="flex w-full items-center justify-between gap-3 text-left">
        <div>
          <div className="text-sm font-semibold">{title}</div>
          {!open && summary && <p className="mt-0.5 text-xs text-muted-foreground">{summary}</p>}
        </div>
        <ChevronDown size={15} className={cn('shrink-0 text-muted-foreground transition-transform', open && 'rotate-180')} />
      </button>
      {open && children}
    </Card>
  )
}
```

- [ ] **Step 2: ChartPage 재배치** — 순서: 차트(CandleChart) → AnalysisPanel(실전 판단) → OutlookCard → 데이터 준비도. 그 아래를 Collapsible로 감싼다: 수급(MoneyFlowCard), 과거 레퍼런스 비교(:628 부근 섹션), 읽는 포인트(:689 부근 섹션). 정밀 분석은 이미 deepOpen 토글(:403)이 있으므로 유지. 각 Collapsible의 summary에 실제 한 줄 요약(예: "외국인/기관 수급 흐름", "닮은 과거 시나리오 비교", "구름대·꼬리 읽기 가이드").
- [ ] **Step 3: 검증** — `npx tsc --noEmit`, 브라우저 `/chart/005930`: 첫 화면에 차트+판단+전망이 스크롤 1.5화면 내, 접힘 섹션 펼침 동작.
- [ ] **Step 4: Commit** — `git commit -m "feat(ux): 차트 페이지 — 핵심 상단 고정, 참고 정보 아코디언"`

---

### Task 7: 전체 QA + 마무리

- [ ] **Step 1: 타입/테스트 최종** — `npx tsc --noEmit` + `npx vitest run` (frontend), `python -m pytest -q` (backend — 변경 없음 확인).
- [ ] **Step 2: 브라우저 여정 QA** — ① `/`에서 신호 행 클릭 → `/chart/{code}` 이동 ② 분석 서브탭 4개 순회 ③ `/journal` 서브탭 4개 순회 ④ 리다이렉트 2종(`/ai`, `/lab`) ⑤ 콘솔 에러 0 확인.
- [ ] **Step 3: 모바일 QA** — 뷰포트 375px: 탭 3개 잘림 없음, 관찰 후보 카드 1열, 신호 테이블 가로 스크롤 동작.
- [ ] **Step 4: README 갱신** — 화면 구성 설명이 있으면 3탭 구조로 수정.
- [ ] **Step 5: Commit + push + PR** — `git push -u origin feat/three-tab-ux`, PR 생성 (스펙 링크 포함), 머지는 사용자 위임 지침에 따라 자체 판단.
