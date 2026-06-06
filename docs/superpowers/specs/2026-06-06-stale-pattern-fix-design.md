# 오래된 패턴 필터링 + 상태 전환 수정 설계 (v2)

**날짜:** 2026-06-06  
**범위:** 백엔드 (timeframe_service, pattern_engine, dashboard, 캐시 키) + 프론트엔드 (AnalysisPanel, DashboardCard)

---

## 1. 문제 정의

### 증상
- 대시보드에 이미 끝난 패턴(`played_out`/`invalidated`)이 계속 표시됨
- 일봉 차트 분석에서 18~21개월 전 패턴이 여전히 `armed` 상태로 표시됨
- 가격이 neckline을 돌파했음에도 `confirmed` 대신 `armed`로 표시됨
- 이미 익절 기준가 근처/이상인데 `played_out`으로 전환 안 됨

### 근본 원인

**원인 1: 일봉 lookback 부족 (400일 = 약 13개월)**  
`timeframe_service.py`의 `1d` 스펙에서 `analysis_lookback_days = 400`.  
21개월 전 시작 패턴의 두 바닥점이 데이터 범위 밖이므로 상태 감지 불안정.

**원인 2: 두 경로의 상태 강등 로직**  
패턴 엔진에 `confirmed` → `armed` 강등이 2가지 경로로 존재:

- **경로 A — `_normalize_state()` 함수 (line 560-567)**:
  ```python
  if breakout_quality < 0.42: return "armed"
  if retest_quality < 0.28:   return "armed"
  ```
- **경로 B — 각 패턴 인라인 블록 (double_bottom, double_top, H&S, I-H&S, triangle, rectangle 등 6곳 이상)**:
  ```python
  if state == "confirmed" and (leg_balance < 0.46 or reversal_energy < 0.44 or variant_fit < 0.66):
      state = "armed"
  elif state == "armed" and (leg_balance < 0.34 or ...):
      state = "forming"
  ```

실제 가격이 neckline 위에 있는데 품질 점수 때문에 `armed`로 내려가는 것은 가격 기반 사실과 모순.

**원인 3: 대시보드 필터 미비**  
`_long_response`, `_short_response`, `_similarity_response` 등에 `played_out`/`invalidated` 제외 및 freshness 하한선 없음.

**원인 4: 캐시 버전 미갱신**  
lookback 또는 패턴 엔진 수정 후에도 기존 캐시 키가 구버전 결과를 돌려줌.

**원인 5: 프론트 "핵심 요약" 탭 상단 카드 미구현**  
설계 스펙에서 탭 최상단에 `[패턴명 — 상태 / 손절·익절·확률]` 한눈에 보기 카드를 추가하기로 했으나 코드에 없음.

**원인 6: DashboardCard 한 줄 요약 미구현**  
`"{STATE_LABELS[state]} · 오를 확률 N%"` 문구가 종목명 아래에 없음.

---

## 2. 수정 내용

### 2-1. Lookback 확장 (`timeframe_service.py`)

```python
# 변경 전
"1d": TimeframeSpec("1d", "일봉", 365, 400, 400, 40),
# 변경 후
"1d": TimeframeSpec("1d", "일봉", 365, 730, 730, 40),
```

`chart_lookback_days`(365)는 프론트 차트 표시용이라 유지. 분석·스캐너 lookback만 730으로 확장.  
`1wk`(1825일), `1mo`(3650일)는 이미 충분하므로 변경 없음.

### 2-2. 상태 강등 로직 완전 제거 (`pattern_engine.py`)

**제거 대상 A — `_normalize_state()` 함수 (line 560-567)**  
함수 자체를 identity로 단순화:
```python
def _normalize_state(state: str, breakout_quality: float, retest_quality: float) -> str:
    return state  # 상태는 가격 기반으로만 결정, 품질은 textbook_similarity에 반영
```

**제거 대상 B — 각 패턴 인라인 다운그레이드 블록**  
double_bottom, double_top, head_and_shoulders, inverse_head_and_shoulders, triangles(ascending/descending/symmetric), rectangle, cup_and_handle, vcp에서:
```python
# 이 블록들을 모두 삭제
if state == "confirmed" and (leg_balance < 0.46 or reversal_energy < 0.44 or variant_fit < 0.66):
    state = "armed"
elif state == "armed" and (leg_balance < 0.34 or reversal_energy < 0.30 or variant_fit < 0.58):
    state = "forming"
```

**상태 결정 원칙**: 상태는 오직 가격 기반(neckline 돌파 여부, high/low vs target/invalidation).  
품질 점수는 `textbook_similarity`와 각 fit 점수에만 반영.  
`_refresh_pattern_state`의 현재가 기반 `played_out`/`invalidated` 전환은 그대로 유지.

### 2-3. 대시보드 필터 강화 (`dashboard.py`)

헬퍼 추가:
```python
_TERMINAL_STATES = frozenset({"played_out", "invalidated"})

def _is_active_candidate(row: dict) -> bool:
    """active = 아직 살아있는 패턴 후보 (종료·무효 아님, 신선도 기준 이상)"""
    return (
        row.get("state") not in _TERMINAL_STATES
        and row.get("freshness_score", 0.0) >= 0.15
    )
```

| 함수 | 추가 조건 |
|---|---|
| `_long_response` | `_is_active_candidate(row)` 추가 |
| `_short_response` | `_is_active_candidate(row)` 추가 |
| `_similarity_response` | `_is_active_candidate(row)` 추가 |
| `_armed_response` | state 필터 이미 있음 → `freshness_score >= 0.15` 추가 |
| `_forming_response` | state 필터 이미 있음 → `freshness_score >= 0.15` 추가 |
| `_no_signal_response` | `freshness_score >= 0.05` 추가 (기준 완화) |

### 2-4. 캐시 키 버전 업그레이드

| 파일 | 기존 키 | 변경 후 |
|---|---|---|
| `symbols.py` | `analysis:v8:{symbol}:{timeframe}` | `analysis:v9:{symbol}:{timeframe}` |
| `scanner.py` | `scanner:v9:full_results:{timeframe}` | `scanner:v10:full_results:{timeframe}` |
| `scanner.py` | `scan:v9:result:{timeframe}:{code}:{mode}` | `scan:v10:result:{timeframe}:{code}:{mode}` |

### 2-5. AnalysisPanel 핵심 요약 탭 상단 카드 추가 (`AnalysisPanel.tsx`)

"핵심 요약" 탭 최상단에 `PatternSummaryCard` 추가. `ActionPlanCard` 앞에 배치.

표시 조건: `!analysis.no_signal_flag && analysis.patterns.length > 0`

```tsx
// 표시 내용 (mock)
[이중바닥] — [돌파 완료]  [A급]
손절 기준가: 139,986원    익절 기준가: 184,900원
오를 확률: 74%  /  내릴 확률: 26%
```

스타일: 상단 강조 카드 (border-primary/20, bg-primary/5). 가격은 red/emerald 컬러 적용.  
`no_signal_flag=true`일 때는 렌더링하지 않음 (기존 `ProbabilityCard`의 No Signal 표시로 충분).

### 2-6. DashboardCard 한 줄 요약 추가 (`DashboardCard.tsx`)

종목명 아래, 뱃지 행 위에 한 줄 요약 텍스트 삽입:
```
"돌파 직전 · 오를 확률 68%"
```

조건: `item.pattern_type && item.state` 이 있을 때만 표시.  
포맷: `{STATE_LABELS[item.state]} · 오를 확률 {Math.round(item.p_up * 100)}%`

---

## 3. 구현 파일 목록

| 파일 | 작업 | 중요도 |
|---|---|---|
| `backend/app/services/timeframe_service.py` | 1d lookback 400→730 | Critical |
| `backend/app/services/pattern_engine.py` | `_normalize_state` 단순화 + 인라인 강등 블록 제거 | Critical |
| `backend/app/api/routes/dashboard.py` | `_is_active_candidate` 헬퍼 + 각 섹션 적용 | Critical |
| `backend/app/api/routes/symbols.py` | 분석 캐시 키 v8→v9 | High |
| `backend/app/services/scanner.py` | 스캔 캐시 키 v9→v10 | High |
| `frontend/src/components/chart/AnalysisPanel.tsx` | `PatternSummaryCard` 추가 | Medium |
| `frontend/src/components/dashboard/DashboardCard.tsx` | 한 줄 요약 텍스트 추가 | Medium |

---

## 4. 범위 밖

- 프론트 페이지 구조 변경 (스크리너, 패턴 사전 등)
- AI 추천 로직 변경
- 새 패턴 타입 추가
- 개인화 시스템 변경
- 매매 결과 추적 UI 변경
