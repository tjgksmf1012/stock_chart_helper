# UX 언어 개선 + 손절/익절 라인 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 앱 전체 어려운 용어를 쉬운 한국어로 교체하고, 차트의 목표가/무효화선을 익절 기준가/손절 기준가로 개명하며, 대시보드·차트 분석·AI 추천 3개 페이지의 핵심 라벨·구조를 개선한다.

**Architecture:** 모든 변경은 프론트엔드 전용. 공유 상수(utils.ts)를 먼저 수정하고, 각 파일에서 하드코딩된 텍스트를 순서대로 교체한다. 백엔드 변경 없음.

**Tech Stack:** React 18, TypeScript, Tailwind CSS, lightweight-charts v4

---

## File Map

| 파일 | 작업 |
|---|---|
| `frontend/src/lib/utils.ts` | STATE_LABELS 교체 |
| `frontend/src/components/Layout.tsx` | NAV_ITEMS 텍스트 4개 교체 |
| `frontend/src/components/chart/CandleChart.tsx` | 레전드 텍스트 7개 + 설명 문구 교체 |
| `frontend/src/components/chart/AnalysisPanel.tsx` | 탭 이름, 가격 라벨, 지표 라벨 교체 |
| `frontend/src/pages/DashboardPage.tsx` | HeroMetric 라벨 3개 + bestAction 문구 |
| `frontend/src/components/dashboard/DashboardCard.tsx` | KeyMetric 라벨, OUTCOME_INTENT 텍스트 |
| `frontend/src/pages/AiRecommendationsPage.tsx` | 페이지 제목, 브리핑 제목, 지표 라벨 |

---

## Task 1: utils.ts — STATE_LABELS 교체

**Files:**
- Modify: `frontend/src/lib/utils.ts:36-42`

- [ ] **Step 1: STATE_LABELS 교체**

`frontend/src/lib/utils.ts` 의 `STATE_LABELS` 블록을 아래로 교체:

```typescript
export const STATE_LABELS: Record<string, string> = {
  forming: '진행 중',
  armed: '돌파 직전',
  confirmed: '돌파 완료',
  invalidated: '패턴 실패',
  played_out: '목표가 도달',
}
```

- [ ] **Step 2: 타입 체크**

```
npx tsc --noEmit
```

Expected: 에러 없음 (exit 0)

- [ ] **Step 3: Commit**

```bash
git add frontend/src/lib/utils.ts
git commit -m "feat(ux): simplify STATE_LABELS to plain Korean"
```

---

## Task 2: Layout.tsx — 네비게이션 텍스트

**Files:**
- Modify: `frontend/src/components/Layout.tsx:8-17`

- [ ] **Step 1: NAV_ITEMS 교체**

`NAV_ITEMS` 배열을 아래로 교체:

```typescript
const NAV_ITEMS = [
  { to: '/', label: '대시보드', icon: LayoutDashboard, end: true },
  { to: '/ai', label: 'AI 추천', icon: Sparkles, end: true },
  { to: '/chart', label: '차트 분석', icon: BarChart2, end: false },
  { to: '/watchlist', label: '관심종목', icon: Star, end: true },
  { to: '/library', label: '패턴 사전', icon: BookOpen, end: true },
  { to: '/reports/patterns', label: '패턴 적중률', icon: TrendingUp, end: true },
  { to: '/screener', label: '종목 필터', icon: SlidersHorizontal, end: true },
  { to: '/system', label: '시스템 상태', icon: ServerCog, end: true },
]
```

- [ ] **Step 2: 타입 체크**

```
npx tsc --noEmit
```

Expected: 에러 없음

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/Layout.tsx
git commit -m "feat(ux): rename nav items to plain Korean"
```

---

## Task 3: CandleChart.tsx — 레전드 + 설명 문구

**Files:**
- Modify: `frontend/src/components/chart/CandleChart.tsx:401-459`

- [ ] **Step 1: 레전드 텍스트 교체**

JSX 내 레전드 블록(return 안)을 아래로 교체. 변경 포인트:
- `전환선` → `단기선`
- `기준선` → `중기선`
- `상승 구름` → `지지 구름`
- `하락 구름` → `저항 구름`
- `목선` → `돌파선`
- `목표가` (레전드 라벨) → `익절 기준가`
- `무효화` (레전드 라벨) → `손절 기준가`

```tsx
<div className="space-y-2 px-2 text-xs text-muted-foreground">
  <div className="flex flex-wrap items-center gap-4">
    <span className="flex items-center gap-1">
      <span className="inline-block h-px w-3 bg-blue-400" /> 단기선
    </span>
    <span className="flex items-center gap-1">
      <span className="inline-block h-px w-3 bg-amber-400" /> 중기선
    </span>
    <span className="flex items-center gap-1">
      <span className="inline-block h-2.5 w-3 rounded-sm bg-emerald-400/25 ring-1 ring-emerald-400/30" /> 지지 구름
    </span>
    <span className="flex items-center gap-1">
      <span className="inline-block h-2.5 w-3 rounded-sm bg-red-400/20 ring-1 ring-red-400/30" /> 저항 구름
    </span>
    {chartPattern && (
      <>
        <span className="flex items-center gap-1">
          <span className="inline-block h-px w-3 bg-amber-400" style={{ borderTop: '1px dashed' }} /> 돌파선
        </span>
        <span className="flex items-center gap-1">
          <span className="inline-block h-px w-3 bg-green-400" style={{ borderTop: '1px dotted' }} /> 익절 기준가
        </span>
        <span className="flex items-center gap-1">
          <span className="inline-block h-px w-3 bg-red-400" style={{ borderTop: '1px dotted' }} /> 손절 기준가
        </span>
      </>
    )}
    {projectionScenarios.length > 0 && (
      <>
        <span className="flex items-center gap-1">
          <span
            className="inline-block h-px w-3"
            style={{ borderTop: `2px dashed ${scenarioColor(projectionScenarios[0])}` }}
          /> 주 시나리오
        </span>
        {projectionScenarios.some(scenario => scenario.key === 'range') && (
          <span className="flex items-center gap-1">
            <span className="inline-block h-px w-3" style={{ borderTop: `1px dotted ${OVERLAY_COLORS.projectionNeutral}` }} /> 횡보 대안
          </span>
        )}
        {projectionScenarios.some(scenario => scenario.key === 'risk') && (
          <span className="flex items-center gap-1">
            <span className="inline-block h-px w-3" style={{ borderTop: `1px dotted ${OVERLAY_COLORS.projectionRisk}` }} /> 리스크 대안
          </span>
        )}
      </>
    )}
  </div>
  <p className="leading-relaxed text-muted-foreground/90">
    구름대 위에서 버티면 지지, 아래로 밀리면 주의 — 단기선·중기선과 함께 보세요.
  </p>
  {projectionScenarios.length > 0 && (
    <p className="leading-relaxed text-muted-foreground/90">
      예상 경로는 확정 예언이 아니라 최근 변동성과 현재 준비도를 반영한 조건부 경로입니다. 주 시나리오만 보지 말고 횡보와 리스크 경로도 같이 확인해 주세요.
    </p>
  )}
</div>
```

- [ ] **Step 2: 타입 체크**

```
npx tsc --noEmit
```

Expected: 에러 없음

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/chart/CandleChart.tsx
git commit -m "feat(ux): rename chart legend — 손절/익절 기준가, 단기/중기선, 지지/저항 구름"
```

---

## Task 4: AnalysisPanel.tsx — 탭 이름 + 가격 라벨

**Files:**
- Modify: `frontend/src/components/chart/AnalysisPanel.tsx`

- [ ] **Step 1: ANALYSIS_TABS 교체 (line 35-40)**

```typescript
const ANALYSIS_TABS: Array<{ key: AnalysisTab; label: string }> = [
  { key: 'overview', label: '핵심 요약' },
  { key: 'setup', label: '진입 준비도' },
  { key: 'pattern', label: '패턴 분석' },
  { key: 'data', label: '참고사항' },
]
```

- [ ] **Step 2: BestPatternCard 가격 라벨 교체 (line 353-362)**

`목선` → `돌파선`, `목표가` → `익절 기준가`, `무효화 기준` → `손절 기준가`:

```tsx
<div className="space-y-2">
  {pattern.neckline !== null && <StatRow label="돌파선" value={fmtPrice(pattern.neckline)} />}
  {pattern.target_level !== null && (
    <StatRow label="익절 기준가" value={<span className="text-emerald-300">{fmtPrice(pattern.target_level)}</span>} />
  )}
  {pattern.invalidation_level !== null && (
    <StatRow label="손절 기준가" value={<span className="text-red-300">{fmtPrice(pattern.invalidation_level)}</span>} />
  )}
  {pattern.target_hit_at && <StatRow label="목표가 도달" value={fmtDateTime(pattern.target_hit_at)} />}
  {pattern.invalidated_at && <StatRow label="패턴 실패 시점" value={fmtDateTime(pattern.invalidated_at)} />}
</div>
```

- [ ] **Step 3: ScoreOverviewCard 확률 라벨 교체 (line 226-233)**

`상승 확률` → `오를 확률`, `하락 확률` → `내릴 확률`:

```typescript
const metrics = [
  { label: '오를 확률', value: fmtPct(analysis.p_up, 0), tone: 'text-emerald-300' },
  { label: '내릴 확률', value: fmtPct(analysis.p_down, 0), tone: 'text-red-300' },
  { label: '신뢰도', value: fmtPct(analysis.confidence, 0) },
  { label: '손익비', value: analysis.reward_risk_ratio.toFixed(2) },
  { label: 'Edge', value: fmtPct(analysis.historical_edge_score, 0) },
  { label: '표본 신뢰도', value: fmtPct(analysis.sample_reliability, 0) },
]
```

- [ ] **Step 4: ActionPlanCard `준비도` → `진입 준비도` (line 403-407)**

```tsx
<div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
  <CompactMetric label="진입 준비도" value={fmtPct(analysis.trade_readiness_score ?? 0, 0)} />
  <CompactMetric label="진입 구간" value={fmtPct(analysis.entry_window_score ?? 0, 0)} />
  <CompactMetric label="신선도" value={fmtPct(analysis.freshness_score ?? 0, 0)} />
  <CompactMetric label="행동 우선순위" value={fmtPct(analysis.action_priority_score, 0)} />
</div>
```

- [ ] **Step 5: CautionCard 문구 교체 (line 320-331)**

`무효화된` → `패턴이 실패한`, `무효화` → `손절 기준가`, `거래 준비도` → `진입 준비도`:

```tsx
function CautionCard() {
  return (
    <Card className="space-y-2">
      <div className="flex items-center gap-2 text-sm font-semibold">
        <ShieldAlert size={15} className="text-orange-400" />
        해석 주의
      </div>
      <p className="text-xs leading-relaxed text-muted-foreground">
        이 화면은 패턴 기반 보조 분석 도구입니다. 이미 목표가에 도달했거나 패턴이 실패한 경우 신선도와 진입 준비도에서 강하게 감점되며, 실전 판단 전에는 추세와 거래대금, 손절 기준가를 함께 보는 편이 안전합니다.
      </p>
    </Card>
  )
}
```

- [ ] **Step 6: 타입 체크**

```
npx tsc --noEmit
```

Expected: 에러 없음

- [ ] **Step 7: Commit**

```bash
git add frontend/src/components/chart/AnalysisPanel.tsx
git commit -m "feat(ux): rename analysis panel tabs + price labels to plain Korean"
```

---

## Task 5: DashboardPage.tsx — 히어로 지표 + bestAction 문구

**Files:**
- Modify: `frontend/src/pages/DashboardPage.tsx`

- [ ] **Step 1: HeroMetric 라벨 교체**

파일에서 아래 세 HeroMetric을 찾아 교체:

```tsx
<HeroMetric
  label="오늘 주목할 종목"
  value={overviewQ.isLoading ? '-' : `${summary.totalCount}개`}
  hint={overviewQ.isLoading ? '스캔 결과 불러오는 중...' : `지금 바로 ${summary.readyCount}개 · 대기 중 ${summary.watchCount}개`}
/>
<HeroMetric
  label="평균 오를 확률"
  value={summary.totalCount > 0 ? fmtPct(summary.avgUp, 0) : '-'}
  hint={summary.bestAction}
/>
<HeroMetric
  label="평균 진입 준비도"
  value={summary.totalCount > 0 ? fmtPct(summary.avgReadiness, 0) : '-'}
  hint={`데이터 품질 ${summary.totalCount > 0 ? fmtPct(summary.avgQuality, 0) : '-'}`}
/>
```

- [ ] **Step 2: bestAction 문구 교체**

파일 하단 `computeSummary` 함수(또는 useMemo)에서 `bestAction` 계산 부분을 찾아 교체:

현재:
```typescript
bestAction:
  readyCount > 0
    ? `즉시 검토 후보 ${readyCount}개가 먼저 보입니다.`
    : watchCount > 0
      ? `트리거 확인이 필요한 후보 ${watchCount}개가 중심입니다.`
```

교체 후:
```typescript
bestAction:
  readyCount > 0
    ? `지금 바로 볼 후보 ${readyCount}개가 있습니다.`
    : watchCount > 0
      ? `트리거 확인이 필요한 후보 ${watchCount}개가 중심입니다.`
```

- [ ] **Step 3: 타입 체크**

```
npx tsc --noEmit
```

Expected: 에러 없음

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/DashboardPage.tsx
git commit -m "feat(ux): simplify dashboard hero metric labels"
```

---

## Task 6: DashboardCard.tsx — KeyMetric 라벨 + OUTCOME_INTENT 텍스트

**Files:**
- Modify: `frontend/src/components/dashboard/DashboardCard.tsx`

- [ ] **Step 1: KeyMetric `준비도` → `진입 준비도` (line 130)**

```tsx
<div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
  <KeyMetric label="진입 준비도" value={fmtPct(item.trade_readiness_score ?? 0, 0)} tone={scoreTone(item.trade_readiness_score ?? 0)} />
  <KeyMetric label="진입 구간" value={fmtPct(item.entry_window_score ?? 0, 0)} tone={scoreTone(item.entry_window_score ?? 0)} />
  <KeyMetric label="신선도" value={fmtPct(item.freshness_score ?? 0, 0)} tone={scoreTone(item.freshness_score ?? 0)} />
  <KeyMetric label="데이터 품질" value={fmtPct(item.data_quality, 0)} tone={scoreTone(item.data_quality)} />
</div>
```

- [ ] **Step 2: OUTCOME_INTENT_OPTIONS 교체 (line 303-308)**

`무효화 감시` → `손절 구간 감시`:

```typescript
const OUTCOME_INTENT_OPTIONS: Array<{ value: OutcomeIntent; label: string }> = [
  { value: 'observe', label: '관망' },
  { value: 'breakout_wait', label: '돌파 대기' },
  { value: 'pullback_candidate', label: '눌림 매수 후보' },
  { value: 'invalidation_watch', label: '손절 구간 감시' },
]
```

- [ ] **Step 3: OUTCOME_INTENT_DESCRIPTIONS 교체 (line 310-315)**

`무효화 여부` → `손절 기준가 이탈 여부`:

```typescript
const OUTCOME_INTENT_DESCRIPTIONS: Record<OutcomeIntent, string> = {
  observe: '아직 진입보다 구조 관찰이 더 중요한 후보입니다.',
  breakout_wait: '트리거 돌파와 거래 반응이 확인될 때 대응할 후보입니다.',
  pullback_candidate: '돌파 뒤 눌림이나 지지 확인을 기다리는 후보입니다.',
  invalidation_watch: '신규 진입보다 손절 기준가 이탈 여부를 먼저 체크해야 하는 후보입니다.',
}
```

- [ ] **Step 4: 타입 체크**

```
npx tsc --noEmit
```

Expected: 에러 없음

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/dashboard/DashboardCard.tsx
git commit -m "feat(ux): rename dashboard card labels — 진입 준비도, 손절 구간 감시"
```

---

## Task 7: AiRecommendationsPage.tsx — 제목 + 브리핑 제목 + 지표 라벨

**Files:**
- Modify: `frontend/src/pages/AiRecommendationsPage.tsx`

- [ ] **Step 1: 페이지 제목 + 설명 문구 교체 (line 73-79)**

```tsx
<div>
  <div className="flex items-center gap-2 text-xl font-bold">
    <Sparkles size={20} className="text-primary" />
    AI 종목 추천
  </div>
  <p className="mt-1 max-w-3xl text-sm leading-relaxed text-muted-foreground">
    점수, 진입 준비도, 데이터 품질, 내 과거 성과를 묶어서 오늘 먼저 볼 종목과 기다릴 종목을 구분해 보여줍니다.
  </p>
</div>
```

- [ ] **Step 2: 브리핑 카드 제목 교체 (line 104-106)**

`오늘의 운용 브리핑` → `오늘의 AI 의견`:

```tsx
<div className="flex items-center gap-2 text-sm font-semibold">
  <ShieldCheck size={16} className="text-primary" />
  오늘의 AI 의견
</div>
```

- [ ] **Step 3: 브리핑 카드 내 지표 라벨 교체 (line 137-142)**

`우선 검토` → `주목 종목`, `트리거 대기` → `대기 종목`, `리스크 점검` → `주의 종목`:

```tsx
<div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
  <Metric label="주목 종목" value={`${data?.priority_items.length ?? 0}개`} />
  <Metric label="대기 종목" value={`${data?.watch_items.length ?? 0}개`} />
  <Metric label="주의 종목" value={`${data?.risk_items.length ?? 0}개`} />
  <Metric label="업데이트" value={fmtDateTime(data?.generated_at)} />
</div>
```

- [ ] **Step 4: 타입 체크**

```
npx tsc --noEmit
```

Expected: 에러 없음

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/AiRecommendationsPage.tsx
git commit -m "feat(ux): rename AI recommendations page title and briefing labels"
```

---

## Task 8: 최종 빌드 검증 + Push

- [ ] **Step 1: 전체 타입 체크**

```
npx tsc --noEmit
```

Expected: 에러 없음

- [ ] **Step 2: Push**

```bash
git push origin main
```

Expected: Vercel 빌드 트리거, 2-3분 후 배포 완료

---

## Self-Review

**스펙 커버리지 확인:**
- ✅ 손절/익절 기준가 → Task 3 (CandleChart 레전드), Task 4 (AnalysisPanel 가격 라벨)
- ✅ STATE_LABELS 전면 교체 → Task 1
- ✅ 네비게이션 4개 교체 → Task 2
- ✅ 일목균형표 레전드 → Task 3
- ✅ 탭 이름 → Task 4
- ✅ 상승/하락 확률 → Task 4
- ✅ 준비도 → 진입 준비도 → Task 4, 5, 6
- ✅ 대시보드 히어로 지표 → Task 5
- ✅ OUTCOME_INTENT 텍스트 → Task 6
- ✅ AI 추천 페이지 제목 + 브리핑 제목 → Task 7

**플레이스홀더 없음:** 모든 태스크에 실제 코드 포함됨.

**타입 일관성:** 모든 변경은 string literal 교체이며 타입 변경 없음. 각 태스크 후 `tsc --noEmit` 으로 검증.
