# 펀드매니저급 기능 3종 설계

**날짜:** 2026-06-08  
**범위:** Market Intelligence (A) + Smart Money Flow (B) + Risk Engine (C)  
**개발 순서:** A → B → C (독립 서브프로젝트, 각각 독립 배포 가능)

---

## 서브프로젝트 A — Market Intelligence Layer

### 목표
개별 종목 신호를 보기 전에 시장 전반의 체제(bull/correction/bear/sideways)와  
업종별 패턴 분포를 한눈에 파악할 수 있도록 대시보드에 맥락 레이어를 추가한다.

### A-1. 시장 체제 판정 (Market Regime)

**체제 정의 (KOSPI, KOSDAQ 각각 계산):**

| 체제 | 조건 |
|---|---|
| `bull` | 현재가 > 20일선 > 60일선 > 120일선 |
| `correction` | 현재가 < 20일선, but 현재가 > 60일선 |
| `bear` | 현재가 < 60일선 |
| `sideways` | 20/60/120일선이 현재가 기준 ±3% 내에 몰려있을 때 |

**데이터 소스:** pykrx `stock.get_index_ohlcv_by_date("KOSPI")` / `("KOSDAQ")`  
**캐시:** Redis TTL 1시간 (장중에는 30분)

**백엔드 엔드포인트:**
```
GET /api/dashboard/market-regime
Response:
  kospi: { price, change_pct, regime, ma20, ma60, ma120, distance_pct }
  kosdaq: { price, change_pct, regime, ma20, ma60, ma120, distance_pct }
  overall_regime: "bull" | "correction" | "bear" | "sideways"
  generated_at: str
```

**프론트엔드 컴포넌트:**  
`MarketRegimeBar` — 대시보드 최상단, 스캔 상태 바 위에 고정 배치

```
KOSPI  2,643 ▲+0.8%  [상승 추세]  120일선 위 +3.2%
KOSDAQ   820 ▲+1.2%  [상승 추세]   60일선 위 +1.8%
```

- 체제별 색상: bull=emerald, correction=amber, bear=rose, sideways=slate
- 체제에 따라 대시보드 섹션 카드에 경고 문구 추가  
  예: `bear` 상태면 long 섹션 상단에 "⚠️ 시장 하락 추세 — 매수 신호 신뢰도 저하"

### A-2. 섹터 히트맵 (Sector Heatmap)

**데이터 소스:** pykrx `stock.get_market_sector_classifications("KOSPI")` + `("KOSDAQ")`  
→ 종목 코드 → 섹터 코드 매핑 테이블 생성  
→ 스캔 결과 종목의 패턴 방향을 섹터별로 집계

**백엔드 엔드포인트:**
```
GET /api/dashboard/sector-heatmap
Response:
  sectors: [
    { sector_name, bullish_count, bearish_count, net_score, top_symbols: [str] }
  ]
  generated_at: str
```

**캐시:** Redis TTL 30분

**프론트엔드 컴포넌트:**  
`SectorHeatmap` — 대시보드에 접을 수 있는 섹션으로 추가

```
강세 섹터                    약세 섹터
🟢 반도체/IT       매수 7    🔴 화학/에너지      매도 5
🟢 바이오          매수 4    🔴 건설/부동산      매도 3
```

**DashboardCard 보강:**  
섹터 분류를 알 수 있는 종목의 경우 카드에 섹터 배지 추가:
```
섹터: 반도체/IT  🟢 강세  (or 🔴 약세 / 🟡 중립)
```

### A-3. 체제별 신호 신뢰도 가중치

분석 결과(`AnalysisResult`)에 `market_regime_context` 필드 추가:
```json
{
  "market_regime": "correction",
  "regime_confidence_modifier": -0.12,
  "regime_note": "시장 조정 구간 — 매수 신호 확률 -12% 하향 적용"
}
```

AnalysisPanel "핵심 요약" 탭의 PatternSummaryCard에서 표시.

---

## 서브프로젝트 B — Smart Money Flow

### 목표
pykrx의 외국인/기관 일별 순매수 데이터를 패턴 분석에 통합해  
"패턴 방향 + 수급 방향이 일치하는가"를 즉시 확인할 수 있게 한다.

### B-1. 수급 데이터 수집

**데이터 소스:** pykrx `stock.get_market_trading_value_by_date(fromdate, todate, code)`  
→ 외국인(foreign) / 기관(institution) / 개인(individual) 일별 순매수(억원)

**수집 범위:** 최근 20거래일  
**캐시:** Redis TTL 4시간 (T+1 데이터이므로 장중 갱신 불필요)

**백엔드 엔드포인트:**
```
GET /api/symbols/{symbol}/money-flow
Response:
  foreign_net_3d: float   # 외국인 3일 순매수 (억원, 양수=순매수)
  foreign_net_10d: float
  institution_net_3d: float
  institution_net_10d: float
  individual_net_3d: float
  daily: [{ date, foreign, institution, individual }]  # 최근 20일
  alignment: "aligned" | "diverged" | "mixed" | "neutral"
    # aligned: 패턴 방향 = 수급 방향 (3일 기준)
    # diverged: 패턴 방향 ≠ 수급 방향
    # mixed: 외국인↑ 기관↓ (또는 반대)
    # neutral: 수급이 뚜렷하지 않음 (절대값 < 임계치)
  generated_at: str
```

**정렬 판정 로직:**
```python
def _money_flow_alignment(foreign_3d, institution_3d, pattern_bias):
    # pattern_bias: "bullish" | "bearish"
    combined = foreign_3d * 0.6 + institution_3d * 0.4
    if abs(combined) < 50:  # 50억 미만은 neutral
        return "neutral"
    flow_direction = "bullish" if combined > 0 else "bearish"
    if flow_direction == pattern_bias:
        return "aligned"
    elif foreign_3d * institution_3d < 0:  # 외인/기관 엇갈림
        return "mixed"
    else:
        return "diverged"
```

### B-2. 분석 결과 통합

`AnalysisResult` 스키마에 money_flow 필드 추가 (optional, 없으면 None):
```json
{
  "money_flow": {
    "foreign_net_3d": 2340.5,
    "institution_net_3d": -820.3,
    "alignment": "mixed",
    "alignment_label": "외국인 순매수 / 기관 순매도",
    "alignment_note": "외인 유입은 긍정적이나 기관 이탈 주의"
  }
}
```

`analyze_symbol_dataframe`에서 money flow를 비동기로 병렬 수집.  
pykrx 오류 시 graceful skip (money_flow=None).

### B-3. 프론트엔드 표시

**AnalysisPanel "핵심 요약" 탭에 `MoneyFlowCard` 추가**

```
외국인/기관 수급 (최근 3일)
외국인  ▲ +2,340억  ✅ 패턴과 정렬
기관    ▼  -820억   ⚠️ 엇갈림
→ 종합: 외인 유입 긍정적, 기관 이탈 주의
```

20일 바 차트 (tiny sparkline): 외국인 순매수를 날짜별로 표시

**DashboardCard에 수급 한 줄 추가**
```
외인 ▲+2,340억 · 기관 ▼-820억  [혼조]
```

**ScreenerPage 필터 추가**
```
수급 필터: □ 외국인 3일 순매수  □ 기관 3일 순매수  □ 수급 정렬 종목만
```

---

## 서브프로젝트 C — Risk Engine (Position Sizing)

### 목표
"신호 발견 → 실제 주문" 사이의 마지막 단계를 자동화.  
계좌 규모와 리스크 허용 범위를 설정하면 "지금 몇 주 살 수 있나"를 즉시 알 수 있다.

### C-1. 사용자 설정 (localStorage via Zustand)

```typescript
interface RiskSettings {
  accountSize: number       // 계좌 총액 (원)
  riskPerTrade: number     // 1회 최대 리스크 % (0.01 = 1%)
  preferAtrStop: boolean   // ATR 손절 선호 여부 (vs 패턴 손절)
  atrMultiplier: number    // ATR 배수 (기본 2.0)
}
```

Zustand store에 추가, persist middleware로 localStorage 저장.  
초기값: accountSize=0 (미설정), riskPerTrade=0.02 (2%), atrMultiplier=2.0

### C-2. ATR 계산 (프론트엔드)

기존 `barsQ` 데이터(이미 프론트엔드에 있음)에서 ATR 계산:
```typescript
function calcATR(bars: OHLCVBar[], period = 14): number {
  // True Range = max(H-L, |H-prevC|, |L-prevC|)
  // ATR = 14일 평균 TR
}
```

백엔드 변경 없이 프론트엔드에서 계산.

### C-3. 포지션 사이징 계산기 UI

AnalysisPanel "진입 준비도" 탭 하단에 `PositionSizerCard` 추가:

```
─── 포지션 계산기 ───────────────────────────────────
계좌 규모     [      100,000,000 원]  ← 입력 (설정에서)
리스크 허용   [        2 %]           ← 입력 (설정에서)
최대 손실금액                2,000,000원

─── 손절 기준 선택 ─────────────────────────────────
● 패턴 기반   손절가 71,200원  (현재가 대비 -5.6%)
○ ATR 기반    손절가 73,800원  (ATR×2, 현재가 대비 -2.1%)

─── 결과 ───────────────────────────────────────────
매수 수량     238주  (투자금액 약 1,794만원 / 계좌 18%)
리스크 보상비  1 : 3.2   ✅ 적정 (기준: 1:2 이상)
포트폴리오 비중  18%      ⚠️ 집중도 주의 (기준: 20% 이하)
────────────────────────────────────────────────────
```

계좌 규모 미설정 시: "⚙️ 설정에서 계좌 규모를 입력하면 포지션 계산이 됩니다" 안내

### C-4. 설정 페이지 / 모달

헤더에 "설정" 아이콘 추가 → 드로어(모달):
- 계좌 규모 입력
- 1회 리스크 % 슬라이더 (0.5% ~ 5%)
- ATR 배수 설정 (1.5 / 2.0 / 2.5)
- 손절 기준 기본값 (패턴 / ATR / 둘 다 비교)

---

## 구현 파일 목록

### 서브프로젝트 A
| 파일 | 작업 |
|---|---|
| `backend/app/api/routes/dashboard.py` | `/market-regime`, `/sector-heatmap` 엔드포인트 추가 |
| `backend/app/services/market_regime_service.py` | 신규 — 지수 OHLCV + 체제 판정 로직 |
| `backend/app/services/sector_service.py` | 신규 — 섹터 맵핑 + 히트맵 집계 |
| `backend/app/api/schemas.py` | `MarketRegimeResponse`, `SectorHeatmapResponse` 스키마 추가 |
| `frontend/src/lib/api.ts` | `dashboardApi.marketRegime()`, `dashboardApi.sectorHeatmap()` 추가 |
| `frontend/src/components/dashboard/MarketRegimeBar.tsx` | 신규 컴포넌트 |
| `frontend/src/components/dashboard/SectorHeatmap.tsx` | 신규 컴포넌트 |
| `frontend/src/components/dashboard/DashboardCard.tsx` | 섹터 배지 추가 |
| `frontend/src/pages/DashboardPage.tsx` | MarketRegimeBar + SectorHeatmap 배치 |
| `frontend/src/types/api.ts` | MarketRegime, SectorHeatmap 타입 추가 |

### 서브프로젝트 B
| 파일 | 작업 |
|---|---|
| `backend/app/api/routes/symbols.py` | `/symbols/{symbol}/money-flow` 엔드포인트 추가 |
| `backend/app/services/money_flow_service.py` | 신규 — pykrx 수급 데이터 수집 + 정렬 판정 |
| `backend/app/api/schemas.py` | `MoneyFlowData` 스키마 추가 |
| `backend/app/services/analysis_service.py` | money_flow 비동기 수집 + AnalysisResult 포함 |
| `frontend/src/lib/api.ts` | `symbolsApi.getMoneyFlow()` 추가 |
| `frontend/src/components/chart/MoneyFlowCard.tsx` | 신규 컴포넌트 (바 차트 포함) |
| `frontend/src/components/chart/AnalysisPanel.tsx` | MoneyFlowCard를 핵심 요약 탭에 추가 |
| `frontend/src/components/dashboard/DashboardCard.tsx` | 수급 한 줄 추가 |
| `frontend/src/pages/ScreenerPage.tsx` | 수급 필터 추가 |
| `frontend/src/types/api.ts` | MoneyFlowData 타입 추가 |

### 서브프로젝트 C
| 파일 | 작업 |
|---|---|
| `frontend/src/store/app.ts` | RiskSettings 추가 (persist) |
| `frontend/src/lib/atr.ts` | 신규 — ATR 계산 유틸 |
| `frontend/src/components/chart/PositionSizerCard.tsx` | 신규 컴포넌트 |
| `frontend/src/components/chart/AnalysisPanel.tsx` | PositionSizerCard를 진입 준비도 탭 하단에 추가 |
| `frontend/src/components/RiskSettingsDrawer.tsx` | 신규 — 설정 드로어 |
| `frontend/src/components/layout/Header.tsx` (또는 해당 레이아웃) | 설정 아이콘 + 드로어 연결 |
| `frontend/src/types/api.ts` | 타입 변경 없음 (로컬만) |

---

## 범위 밖

- 실시간 알림 (웹소켓/푸시)
- 실제 증권사 계좌 연동 (KIS API 매매)
- 포트폴리오 전체 P&L 추적
- 외국인/기관 데이터 실시간 (T+0) — pykrx는 T+1만 지원
