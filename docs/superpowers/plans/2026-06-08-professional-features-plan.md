# Professional Features Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 펀드매니저 관점에서 필요한 3가지 기능 추가 — 시장 체제 지표(A), 외국인/기관 수급(B), 포지션 사이징(C)

**Architecture:**
- A: 신규 backend 서비스 2개(market_regime, sector) + dashboard 엔드포인트 2개 + frontend 컴포넌트 2개
- B: 신규 backend 서비스(money_flow) + AnalysisResult에 money_flow 필드 포함 + frontend MoneyFlowCard
- C: 프론트엔드 전용 (Zustand store + ATR 유틸 + PositionSizerCard + RiskSettingsDrawer). 백엔드 변경 없음.

**Tech Stack:** FastAPI, pykrx (asyncio.to_thread 패턴), React 18, Zustand (persist), TypeScript, Tailwind

---

## 파일 구조

### 신규 생성
- `backend/app/services/market_regime_service.py` — KOSPI/KOSDAQ 체제 판정
- `backend/app/services/sector_service.py` — 섹터 분류 캐시 + 히트맵 집계
- `backend/app/services/money_flow_service.py` — 외국인/기관 순매수 + 정렬 판정
- `frontend/src/components/dashboard/MarketRegimeBar.tsx` — 대시보드 최상단 지수/체제 표시
- `frontend/src/components/dashboard/SectorHeatmap.tsx` — 섹터별 패턴 분포 히트맵
- `frontend/src/components/chart/MoneyFlowCard.tsx` — 외국인/기관 수급 카드
- `frontend/src/lib/atr.ts` — ATR 계산 유틸
- `frontend/src/components/chart/PositionSizerCard.tsx` — 포지션 사이징 계산기
- `frontend/src/components/RiskSettingsDrawer.tsx` — 리스크 설정 드로어

### 수정
- `backend/app/api/schemas.py` — MoneyFlowData, MarketRegimeResponse, SectorHeatmapResponse 추가
- `backend/app/api/routes/dashboard.py` — market-regime, sector-heatmap 엔드포인트
- `backend/app/api/routes/symbols.py` — money-flow 엔드포인트
- `backend/app/services/analysis_service.py` — money_flow 비동기 수집 통합
- `frontend/src/types/api.ts` — MoneyFlowData, MarketRegime, SectorHeatmap 타입
- `frontend/src/lib/api.ts` — dashboardApi, symbolsApi 메서드 추가
- `frontend/src/store/app.ts` — RiskSettings 추가
- `frontend/src/components/chart/AnalysisPanel.tsx` — MoneyFlowCard, PositionSizerCard 추가
- `frontend/src/pages/DashboardPage.tsx` — MarketRegimeBar, SectorHeatmap 배치
- `frontend/src/components/dashboard/DashboardCard.tsx` — 섹터 배지 추가

---

## ── Sub-project A: Market Intelligence ──

---

### Task 1: Backend 스키마 + market_regime_service.py

**Files:**
- Create: `backend/app/services/market_regime_service.py`
- Modify: `backend/app/api/schemas.py`

- [ ] **Step 1: schemas.py에 MarketRegimeResponse, SectorHeatmapResponse 추가**

`backend/app/api/schemas.py` 의 `AnalysisResult` 클래스 이후에 추가:

```python
class IndexRegime(BaseModel):
    regime: str  # "bull" | "correction" | "bear" | "sideways" | "unknown"
    current: float = 0.0
    change_pct: float = 0.0
    ma20: float | None = None
    ma60: float | None = None
    ma120: float | None = None
    distance_from_ma120_pct: float = 0.0


class MarketRegimeResponse(BaseModel):
    kospi: IndexRegime
    kosdaq: IndexRegime
    overall_regime: str  # "bull" | "correction" | "bear" | "sideways" | "unknown"
    generated_at: str


class SectorEntry(BaseModel):
    sector_name: str
    bullish_count: int
    bearish_count: int
    net_score: int  # bullish_count - bearish_count
    top_symbols: list[str]


class SectorHeatmapResponse(BaseModel):
    sectors: list[SectorEntry]
    code_to_sector: dict[str, str]  # {종목코드: 섹터명} 전체 맵
    generated_at: str
```

- [ ] **Step 2: market_regime_service.py 생성**

```python
"""
Market regime detection for KOSPI and KOSDAQ.
Uses pykrx index OHLCV with the same asyncio.to_thread pattern as data_fetcher.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, timedelta

import pandas as pd

from ..core.redis import cache_get, cache_set
from ..api.schemas import IndexRegime, MarketRegimeResponse

logger = logging.getLogger(__name__)

KOSPI_TICKER = "1001"
KOSDAQ_TICKER = "2001"
_CACHE_KEY = "market:regime:v1"
_CACHE_TTL = 1800  # 30분


def _classify(df: pd.DataFrame) -> IndexRegime:
    if df is None or df.empty or len(df) < 20:
        return IndexRegime(regime="unknown")

    # pykrx index columns: 시가, 고가, 저가, 종가, 거래량, 거래대금
    close_col = "종가" if "종가" in df.columns else df.columns[3]
    close = df[close_col].dropna()
    if len(close) < 20:
        return IndexRegime(regime="unknown")

    current = float(close.iloc[-1])
    prev = float(close.iloc[-2]) if len(close) >= 2 else current
    ma20 = float(close.rolling(20).mean().iloc[-1])
    ma60 = float(close.rolling(60).mean().iloc[-1]) if len(close) >= 60 else ma20
    ma120 = float(close.rolling(120).mean().iloc[-1]) if len(close) >= 120 else ma60

    distance_pct = round((current - ma120) / ma120 * 100, 2) if ma120 else 0.0
    change_pct = round((current - prev) / prev * 100, 2) if prev else 0.0

    ma_max = max(ma20, ma60, ma120)
    ma_min = min(ma20, ma60, ma120)
    ma_spread_pct = (ma_max - ma_min) / current * 100 if current else 0

    if ma_spread_pct < 3.0 and abs(current - ma60) / current * 100 < 3.0:
        regime = "sideways"
    elif current > ma20 and ma20 > ma60:
        regime = "bull"
    elif current < ma60:
        regime = "bear"
    else:
        regime = "correction"

    return IndexRegime(
        regime=regime,
        current=round(current, 2),
        change_pct=change_pct,
        ma20=round(ma20, 2),
        ma60=round(ma60, 2),
        ma120=round(ma120, 2),
        distance_from_ma120_pct=distance_pct,
    )


async def _fetch_index_df(ticker: str, days: int = 160) -> pd.DataFrame:
    from pykrx import stock as krx
    end = date.today()
    start = end - timedelta(days=days)
    df = await asyncio.wait_for(
        asyncio.to_thread(
            krx.get_index_ohlcv_by_date,
            start.strftime("%Y%m%d"),
            end.strftime("%Y%m%d"),
            ticker,
        ),
        timeout=15.0,
    )
    return df


async def get_market_regime() -> MarketRegimeResponse:
    cached = await cache_get(_CACHE_KEY)
    if cached:
        return MarketRegimeResponse(**cached)

    try:
        kospi_df, kosdaq_df = await asyncio.gather(
            _fetch_index_df(KOSPI_TICKER),
            _fetch_index_df(KOSDAQ_TICKER),
            return_exceptions=True,
        )
        kospi = _classify(kospi_df if not isinstance(kospi_df, Exception) else pd.DataFrame())
        kosdaq = _classify(kosdaq_df if not isinstance(kosdaq_df, Exception) else pd.DataFrame())

        # Overall: 두 지수 중 더 약한 쪽 기준 (보수적)
        regime_rank = {"bull": 3, "sideways": 2, "correction": 1, "bear": 0, "unknown": -1}
        overall = min(
            [kospi.regime, kosdaq.regime],
            key=lambda r: regime_rank.get(r, -1),
        )

        result = MarketRegimeResponse(
            kospi=kospi,
            kosdaq=kosdaq,
            overall_regime=overall,
            generated_at=datetime.utcnow().isoformat(),
        )
        await cache_set(_CACHE_KEY, result.model_dump(), ttl=_CACHE_TTL)
        return result
    except Exception as exc:
        logger.warning("market regime fetch failed: %s", exc)
        return MarketRegimeResponse(
            kospi=IndexRegime(regime="unknown"),
            kosdaq=IndexRegime(regime="unknown"),
            overall_regime="unknown",
            generated_at=datetime.utcnow().isoformat(),
        )
```

- [ ] **Step 3: 문법 검증**

```bash
cd backend && python -c "
import ast, sys
files = ['app/services/market_regime_service.py', 'app/api/schemas.py']
for f in files:
    ast.parse(open(f, encoding='utf-8').read())
    print('OK:', f)
"
```

Expected: `OK: app/services/market_regime_service.py` + `OK: app/api/schemas.py`

- [ ] **Step 4: 커밋**

```bash
git add backend/app/services/market_regime_service.py backend/app/api/schemas.py
git commit -m "feat(A): add market regime service + schemas"
```

---

### Task 2: sector_service.py

**Files:**
- Create: `backend/app/services/sector_service.py`

- [ ] **Step 1: sector_service.py 생성**

```python
"""
Sector classification service.
Fetches WICS sector → stock code mapping via pykrx.
Used by sector-heatmap endpoint to aggregate pattern counts per sector.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime
from typing import Any

import pandas as pd

from ..core.redis import cache_get, cache_set

logger = logging.getLogger(__name__)

_SECTOR_MAP_CACHE_KEY = "market:sector-map:v1"
_SECTOR_MAP_TTL = 86400  # 하루 (섹터 분류는 거의 안 바뀜)

# KOSPI WICS 섹터 인덱스 티커 → 한국어 섹터명
_KOSPI_SECTOR_TICKERS: dict[str, str] = {
    "1001": "전체",  # skip
    "1002": "대형주",  # skip
    "1028": "운수장비",
    "1034": "비금속광물",
    "1003": "건설업",
    "1044": "IT",
    "1017": "금융업",
    "1010": "음식료품",
    "1022": "화학",
    "1005": "기계",
    "1007": "철강금속",
    "1008": "전기가스업",
    "1015": "전기전자",
    "1016": "의약품",
    "1006": "종이목재",
    "1009": "섬유의복",
    "1011": "유통업",
    "1014": "운수창고",
    "1021": "통신업",
    "1024": "서비스업",
}
_SKIP_TICKERS = {"1001", "1002"}


async def _fetch_sector_constituents(ticker: str, today: str) -> tuple[str, list[str]]:
    """단일 섹터 구성 종목 코드 리스트 반환."""
    from pykrx import stock as krx
    sector_name = _KOSPI_SECTOR_TICKERS.get(ticker, ticker)
    try:
        df = await asyncio.wait_for(
            asyncio.to_thread(krx.get_index_portfolio_deposit_file, ticker, today),
            timeout=10.0,
        )
        if df is None or (hasattr(df, "empty") and df.empty):
            return sector_name, []
        # pykrx returns DataFrame with '티커' or similar column, or the index IS the ticker
        if isinstance(df.index, pd.Index) and df.index.dtype == object:
            codes = list(df.index.astype(str))
        elif "티커" in df.columns:
            codes = list(df["티커"].astype(str))
        elif "종목코드" in df.columns:
            codes = list(df["종목코드"].astype(str))
        else:
            codes = [str(c) for c in df.iloc[:, 0]]
        return sector_name, [c.zfill(6) for c in codes if c.strip()]
    except Exception as exc:
        logger.debug("sector %s (%s) fetch failed: %s", sector_name, ticker, exc)
        return sector_name, []


async def get_sector_map() -> dict[str, str]:
    """Returns {stock_code: sector_name} for all KOSPI sector constituents."""
    cached = await cache_get(_SECTOR_MAP_CACHE_KEY)
    if cached:
        return cached  # already a dict

    today = date.today().strftime("%Y%m%d")
    active_tickers = [t for t in _KOSPI_SECTOR_TICKERS if t not in _SKIP_TICKERS]

    results = await asyncio.gather(
        *[_fetch_sector_constituents(t, today) for t in active_tickers],
        return_exceptions=True,
    )

    code_to_sector: dict[str, str] = {}
    for r in results:
        if isinstance(r, Exception):
            continue
        sector_name, codes = r
        for code in codes:
            code_to_sector[code] = sector_name

    if code_to_sector:
        await cache_set(_SECTOR_MAP_CACHE_KEY, code_to_sector, ttl=_SECTOR_MAP_TTL)
    return code_to_sector


def build_sector_heatmap(
    scan_rows: list[dict],
    code_to_sector: dict[str, str],
) -> list[dict]:
    """
    scan_rows: list of scanner result rows (each has 'code', 'pattern_type', p_up, p_down)
    Returns sorted list of sector aggregation dicts.
    """
    from ..services.analysis_service import _BULLISH_PATTERNS, _BEARISH_PATTERNS

    aggregation: dict[str, dict[str, Any]] = {}

    for row in scan_rows:
        code = row.get("code", "")
        sector = code_to_sector.get(code, "기타")
        pattern = row.get("pattern_type") or ""
        if not pattern:
            continue

        if sector not in aggregation:
            aggregation[sector] = {"bullish": 0, "bearish": 0, "symbols": []}

        if pattern in _BULLISH_PATTERNS:
            aggregation[sector]["bullish"] += 1
            aggregation[sector]["symbols"].append(row.get("name", code))
        elif pattern in _BEARISH_PATTERNS:
            aggregation[sector]["bearish"] += 1

    sectors = [
        {
            "sector_name": name,
            "bullish_count": v["bullish"],
            "bearish_count": v["bearish"],
            "net_score": v["bullish"] - v["bearish"],
            "top_symbols": v["symbols"][:3],
        }
        for name, v in aggregation.items()
    ]
    sectors.sort(key=lambda s: abs(s["net_score"]), reverse=True)
    return sectors
```

- [ ] **Step 2: 문법 검증**

```bash
cd backend && python -c "
import ast
ast.parse(open('app/services/sector_service.py', encoding='utf-8').read())
print('OK')
"
```

Expected: `OK`

- [ ] **Step 3: 커밋**

```bash
git add backend/app/services/sector_service.py
git commit -m "feat(A): add sector classification service"
```

---

### Task 3: dashboard.py — market-regime, sector-heatmap 엔드포인트

**Files:**
- Modify: `backend/app/api/routes/dashboard.py`

- [ ] **Step 1: 상단 import 추가**

`dashboard.py` 상단의 import 블록에 추가:

```python
from ...services.market_regime_service import get_market_regime
from ...services.sector_service import build_sector_heatmap, get_sector_map
from ..schemas import MarketRegimeResponse, SectorHeatmapResponse, SectorEntry
```

- [ ] **Step 2: 파일 하단(scan-refresh 엔드포인트 뒤)에 새 엔드포인트 추가**

```python
@router.get("/market-regime", response_model=MarketRegimeResponse)
async def dashboard_market_regime() -> MarketRegimeResponse:
    return await get_market_regime()


@router.get("/sector-heatmap", response_model=SectorHeatmapResponse)
async def dashboard_sector_heatmap(
    timeframe: str = Query(default=DEFAULT_TIMEFRAME),
) -> SectorHeatmapResponse:
    from ...services.scanner import get_scan_results
    from datetime import datetime

    code_to_sector, scan_data = await asyncio.gather(
        get_sector_map(),
        get_scan_results(timeframe),
        return_exceptions=True,
    )
    if isinstance(code_to_sector, Exception):
        code_to_sector = {}
    if isinstance(scan_data, Exception):
        scan_data = []

    raw_rows = scan_data if isinstance(scan_data, list) else []
    sectors = build_sector_heatmap(raw_rows, code_to_sector)

    return SectorHeatmapResponse(
        sectors=[SectorEntry(**s) for s in sectors],
        code_to_sector=code_to_sector,
        generated_at=datetime.utcnow().isoformat(),
    )
```

- [ ] **Step 3: `asyncio` import 확인 (없으면 추가)**

`dashboard.py` 상단에 `import asyncio` 가 없으면 추가. 기존에 있으면 스킵.

- [ ] **Step 4: 문법 검증**

```bash
cd backend && python -c "
import ast
ast.parse(open('app/api/routes/dashboard.py', encoding='utf-8').read())
print('OK')
"
```

Expected: `OK`

- [ ] **Step 5: scanner.py에 get_scan_results 헬퍼 존재 여부 확인**

```bash
cd backend && grep -n "^async def get_scan_results\|^def get_scan_results" app/services/scanner.py | head -5
```

없으면 scanner.py 하단에 추가:

```python
async def get_scan_results(timeframe: str) -> list[dict]:
    """Return the latest cached scan rows for heatmap aggregation."""
    raw = await cache_get(_full_results_key(timeframe))
    if isinstance(raw, list):
        return raw
    return []
```

- [ ] **Step 6: 커밋**

```bash
git add backend/app/api/routes/dashboard.py backend/app/services/scanner.py
git commit -m "feat(A): add market-regime + sector-heatmap dashboard endpoints"
```

---

### Task 4: Frontend 타입 + api.ts 추가

**Files:**
- Modify: `frontend/src/types/api.ts`
- Modify: `frontend/src/lib/api.ts`

- [ ] **Step 1: types/api.ts 하단에 타입 추가**

```typescript
export interface IndexRegime {
  regime: 'bull' | 'correction' | 'bear' | 'sideways' | 'unknown'
  current: number
  change_pct: number
  ma20: number | null
  ma60: number | null
  ma120: number | null
  distance_from_ma120_pct: number
}

export interface MarketRegimeResponse {
  kospi: IndexRegime
  kosdaq: IndexRegime
  overall_regime: 'bull' | 'correction' | 'bear' | 'sideways' | 'unknown'
  generated_at: string
}

export interface SectorEntry {
  sector_name: string
  bullish_count: number
  bearish_count: number
  net_score: number
  top_symbols: string[]
}

export interface SectorHeatmapResponse {
  sectors: SectorEntry[]
  code_to_sector: Record<string, string>
  generated_at: string
}

export interface MoneyFlowData {
  foreign_net_3d: number   // 억원
  foreign_net_10d: number
  institution_net_3d: number
  institution_net_10d: number
  alignment: 'aligned' | 'diverged' | 'mixed' | 'neutral'
  alignment_label: string
  alignment_note: string
  daily: Array<{ date: string; foreign: number; institution: number }>
}
```

- [ ] **Step 2: AnalysisResult 타입에 money_flow 필드 추가**

`types/api.ts`의 `AnalysisResult` 인터페이스 마지막 `available_bars` 필드 이후에:

```typescript
  money_flow?: MoneyFlowData | null
```

- [ ] **Step 3: api.ts에 새 메서드 추가**

`api.ts`의 `dashboardApi` 객체에 추가:

```typescript
  marketRegime: () =>
    api.get<MarketRegimeResponse>('/dashboard/market-regime').then(r => r.data),
  sectorHeatmap: (timeframe: Timeframe) =>
    api.get<SectorHeatmapResponse>('/dashboard/sector-heatmap', { params: { timeframe } }).then(r => r.data),
```

`api.ts`의 `symbolsApi` 객체에 추가:

```typescript
  getMoneyFlow: (symbol: string) =>
    api.get<MoneyFlowData>(`/symbols/${symbol}/money-flow`).then(r => r.data),
```

`api.ts` 상단 import에 `MarketRegimeResponse, SectorHeatmapResponse, MoneyFlowData` 추가.

- [ ] **Step 4: TypeScript 타입 검증**

```bash
cd frontend && npx tsc --noEmit 2>&1 | head -20
```

Expected: 오류 없음 (빈 출력)

- [ ] **Step 5: 커밋**

```bash
git add frontend/src/types/api.ts frontend/src/lib/api.ts
git commit -m "feat(A/B): add market regime + money flow types and API methods"
```

---

### Task 5: MarketRegimeBar + SectorHeatmap 컴포넌트

**Files:**
- Create: `frontend/src/components/dashboard/MarketRegimeBar.tsx`
- Create: `frontend/src/components/dashboard/SectorHeatmap.tsx`

- [ ] **Step 1: MarketRegimeBar.tsx 생성**

```tsx
import { TrendingDown, TrendingUp, Minus } from 'lucide-react'
import { cn } from '@/lib/utils'
import type { MarketRegimeResponse } from '@/types/api'

interface MarketRegimeBarProps {
  data: MarketRegimeResponse
}

const REGIME_CONFIG = {
  bull: { label: '상승 추세', color: 'text-emerald-400', bg: 'bg-emerald-400/10 border-emerald-400/20' },
  correction: { label: '조정 구간', color: 'text-amber-400', bg: 'bg-amber-400/10 border-amber-400/20' },
  bear: { label: '하락 추세', color: 'text-rose-400', bg: 'bg-rose-400/10 border-rose-400/20' },
  sideways: { label: '횡보', color: 'text-slate-400', bg: 'bg-slate-400/10 border-slate-400/20' },
  unknown: { label: '정보 없음', color: 'text-muted-foreground', bg: 'bg-muted/10 border-border' },
} as const

function IndexChip({ name, regime }: { name: string; regime: MarketRegimeResponse['kospi'] }) {
  const cfg = REGIME_CONFIG[regime.regime] ?? REGIME_CONFIG.unknown
  const isUp = regime.change_pct >= 0
  return (
    <div className={cn('flex items-center gap-3 rounded-lg border px-3 py-2', cfg.bg)}>
      <span className="text-xs font-semibold text-muted-foreground">{name}</span>
      {regime.current > 0 && (
        <span className="font-mono text-sm font-semibold">{regime.current.toLocaleString()}</span>
      )}
      {regime.change_pct !== 0 && (
        <span className={cn('flex items-center gap-0.5 text-xs font-medium', isUp ? 'text-emerald-400' : 'text-rose-400')}>
          {isUp ? <TrendingUp size={11} /> : <TrendingDown size={11} />}
          {isUp ? '+' : ''}{regime.change_pct.toFixed(2)}%
        </span>
      )}
      <span className={cn('rounded px-1.5 py-0.5 text-xs font-medium border', cfg.bg, cfg.color)}>
        {cfg.label}
      </span>
      {regime.distance_from_ma120_pct !== 0 && (
        <span className="text-xs text-muted-foreground">
          120일선 대비 {regime.distance_from_ma120_pct > 0 ? '+' : ''}{regime.distance_from_ma120_pct.toFixed(1)}%
        </span>
      )}
    </div>
  )
}

export function MarketRegimeBar({ data }: MarketRegimeBarProps) {
  const overallCfg = REGIME_CONFIG[data.overall_regime] ?? REGIME_CONFIG.unknown
  return (
    <div className="flex flex-wrap items-center gap-2 rounded-lg border border-border bg-background/60 px-3 py-2">
      <span className="text-xs font-medium text-muted-foreground">시장 체제</span>
      <span className={cn('text-xs font-semibold', overallCfg.color)}>{overallCfg.label}</span>
      <div className="mx-1 h-3 w-px bg-border" />
      <IndexChip name="KOSPI" regime={data.kospi} />
      <IndexChip name="KOSDAQ" regime={data.kosdaq} />
    </div>
  )
}

export function getRegimeBearWarning(overall: string): string | null {
  if (overall === 'bear') return '⚠️ 시장 하락 추세 — 매수 신호 신뢰도 저하'
  if (overall === 'correction') return '⚠️ 시장 조정 구간 — 손절 기준 엄격히 적용'
  return null
}
```

- [ ] **Step 2: SectorHeatmap.tsx 생성**

```tsx
import { useState } from 'react'
import { ChevronDown, ChevronUp } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Card } from '@/components/ui/Card'
import type { SectorEntry } from '@/types/api'

interface SectorHeatmapProps {
  sectors: SectorEntry[]
}

function SectorBar({ sector }: { sector: SectorEntry }) {
  const total = sector.bullish_count + sector.bearish_count
  const bullPct = total > 0 ? (sector.bullish_count / total) * 100 : 50
  const net = sector.net_score
  const tone = net > 0 ? 'emerald' : net < 0 ? 'rose' : 'slate'
  const toneClass = { emerald: 'text-emerald-400', rose: 'text-rose-400', slate: 'text-muted-foreground' }[tone]

  return (
    <div className="flex items-center gap-3">
      <span className="w-20 shrink-0 text-xs text-muted-foreground">{sector.sector_name}</span>
      <div className="relative h-1.5 flex-1 overflow-hidden rounded-full bg-muted/30">
        <div
          className="absolute left-0 top-0 h-full rounded-full bg-emerald-400/60"
          style={{ width: `${bullPct}%` }}
        />
      </div>
      <span className={cn('w-12 shrink-0 text-right text-xs font-medium', toneClass)}>
        {net > 0 ? `+${net}` : net}
      </span>
      <div className="hidden text-xs text-muted-foreground sm:block">
        {sector.top_symbols.slice(0, 2).join(', ')}
      </div>
    </div>
  )
}

export function SectorHeatmap({ sectors }: SectorHeatmapProps) {
  const [open, setOpen] = useState(false)
  if (!sectors.length) return null
  const bullSectors = sectors.filter(s => s.net_score > 0).slice(0, 4)
  const bearSectors = sectors.filter(s => s.net_score < 0).slice(0, 4)

  return (
    <Card className="space-y-3">
      <button
        onClick={() => setOpen(v => !v)}
        className="flex w-full items-center justify-between"
      >
        <div className="flex items-center gap-2">
          <span className="text-sm font-semibold">섹터 패턴 분포</span>
          {bullSectors.length > 0 && (
            <span className="rounded bg-emerald-400/15 px-1.5 py-0.5 text-xs text-emerald-400">
              강세 {bullSectors.length}개
            </span>
          )}
          {bearSectors.length > 0 && (
            <span className="rounded bg-rose-400/15 px-1.5 py-0.5 text-xs text-rose-400">
              약세 {bearSectors.length}개
            </span>
          )}
        </div>
        {open ? <ChevronUp size={14} className="text-muted-foreground" /> : <ChevronDown size={14} className="text-muted-foreground" />}
      </button>

      {open && (
        <div className="space-y-2">
          <div className="flex justify-between text-xs text-muted-foreground">
            <span>섹터</span>
            <span>매수↑ / 매도↓ 순</span>
          </div>
          {sectors.slice(0, 10).map(sector => (
            <SectorBar key={sector.sector_name} sector={sector} />
          ))}
        </div>
      )}
    </Card>
  )
}
```

- [ ] **Step 3: TypeScript 검증**

```bash
cd frontend && npx tsc --noEmit 2>&1 | head -20
```

Expected: 오류 없음

- [ ] **Step 4: 커밋**

```bash
git add frontend/src/components/dashboard/MarketRegimeBar.tsx frontend/src/components/dashboard/SectorHeatmap.tsx
git commit -m "feat(A): add MarketRegimeBar + SectorHeatmap components"
```

---

### Task 6: DashboardPage + DashboardCard 통합

**Files:**
- Modify: `frontend/src/pages/DashboardPage.tsx`
- Modify: `frontend/src/components/dashboard/DashboardCard.tsx`

- [ ] **Step 1: DashboardPage.tsx — import 추가**

파일 상단 import 블록에 추가:

```tsx
import { useQuery } from '@tanstack/react-query'  // 이미 있음
import { MarketRegimeBar, getRegimeBearWarning } from '@/components/dashboard/MarketRegimeBar'
import { SectorHeatmap } from '@/components/dashboard/SectorHeatmap'
```

- [ ] **Step 2: DashboardPage — 쿼리 추가**

`DashboardPage` 함수 내부, `overviewQ` 정의 이후에:

```tsx
const regimeQ = useQuery({
  queryKey: ['dashboard', 'market-regime'],
  queryFn: () => dashboardApi.marketRegime(),
  staleTime: 1_800_000,   // 30분
  refetchInterval: 1_800_000,
})

const sectorQ = useQuery({
  queryKey: ['dashboard', timeframe, 'sector-heatmap'],
  queryFn: () => dashboardApi.sectorHeatmap(timeframe),
  staleTime: 1_800_000,
})
```

- [ ] **Step 3: DashboardPage — 렌더링에 추가**

DashboardPage 렌더링 부분에서 대시보드 최상단(스캔 상태 바 바로 위)에 추가:

```tsx
{regimeQ.data && <MarketRegimeBar data={regimeQ.data} />}
{sectorQ.data && <SectorHeatmap sectors={sectorQ.data.sectors} />}
```

- [ ] **Step 4: DashboardCard — 섹터 배지 추가**

`DashboardCard.tsx`에서 `DashboardCardProps` 인터페이스에 추가:
```tsx
interface DashboardCardProps {
  item: DashboardItem
  intradayPreset?: string
  sectorName?: string      // 추가
  sectorNetScore?: number  // 추가 (양수=강세, 음수=약세)
}
```

`DashboardCard` 함수 시그니처 수정:
```tsx
export function DashboardCard({ item, sectorName, sectorNetScore }: DashboardCardProps) {
```

`DashboardCard` 내부, 한 줄 요약 텍스트(기존 `item.pattern_type && item.state` 블록) 아래에 섹터 배지 추가:

```tsx
{sectorName && (
  <p className={cn('text-xs', sectorNetScore !== undefined && sectorNetScore > 0
    ? 'text-emerald-400'
    : sectorNetScore !== undefined && sectorNetScore < 0
    ? 'text-rose-400'
    : 'text-muted-foreground'
  )}>
    섹터: {sectorName}
    {sectorNetScore !== undefined && sectorNetScore !== 0 && (
      <span className="ml-1">
        {sectorNetScore > 0 ? '🟢 강세' : '🔴 약세'}
      </span>
    )}
  </p>
)}
```

- [ ] **Step 5: DashboardPage에서 DashboardCard 호출 시 sectorName 전달**

DashboardPage에서 `sectorQ.data?.code_to_sector`를 사용해 DashboardCard 호출 시 섹터 정보를 전달하도록 수정. DashboardSection과 DashboardCard를 렌더링하는 코드를 찾아서 해당 위치에서:

```tsx
// DashboardSection이 DashboardCard를 렌더링할 때 sectorMap을 prop으로 내려야 함
// DashboardSection.tsx에 sectorMap?: Record<string, string> prop 추가 필요 여부 확인
// 또는 DashboardPage에서 직접 DashboardCard를 wrapping하는 경우 해당 위치에서 처리
```

DashboardSection.tsx를 확인해서 DashboardCard에 prop을 어떻게 전달하는지 확인 후 sectorMap prop 체인을 추가.

실제 DashboardSection.tsx 파일 경로: `frontend/src/components/dashboard/DashboardSection.tsx`

- [ ] **Step 6: TypeScript 검증**

```bash
cd frontend && npx tsc --noEmit 2>&1 | head -30
```

Expected: 오류 없음

- [ ] **Step 7: 커밋**

```bash
git add frontend/src/pages/DashboardPage.tsx frontend/src/components/dashboard/DashboardCard.tsx
git commit -m "feat(A): integrate market regime bar + sector heatmap into dashboard"
```

---

## ── Sub-project B: Smart Money Flow ──

---

### Task 7: money_flow_service.py

**Files:**
- Create: `backend/app/services/money_flow_service.py`

- [ ] **Step 1: money_flow_service.py 생성**

```python
"""
Foreign investor / institution net buying data via pykrx.
Data is T+1 (previous day). Cached for 4 hours.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, timedelta

import pandas as pd

from ..core.redis import cache_get, cache_set

logger = logging.getLogger(__name__)

_CACHE_PREFIX = "moneyflow:v1"
_CACHE_TTL = 14400  # 4시간

_BULLISH_PATTERNS = {
    "double_bottom", "inverse_head_and_shoulders", "ascending_triangle",
    "rectangle", "cup_and_handle", "rounding_bottom", "vcp",
}
_BEARISH_PATTERNS = {
    "double_top", "head_and_shoulders", "descending_triangle",
}

# 수급 방향성 유의미 임계치: 50억원
_FLOW_THRESHOLD_BILLION = 50.0


def _to_billion(krw: float) -> float:
    return round(krw / 1e8, 1)


async def _fetch_trading_value(code: str, start: str, end: str) -> pd.DataFrame:
    from pykrx import stock as krx
    df = await asyncio.wait_for(
        asyncio.to_thread(krx.get_market_trading_value_by_date, start, end, code),
        timeout=15.0,
    )
    return df


def _parse_flow(df: pd.DataFrame) -> dict:
    """외국인합계, 기관합계 컬럼 파싱 (컬럼명이 버전마다 다름)."""
    if df is None or df.empty:
        return {"foreign_daily": [], "institution_daily": []}

    foreign_col = next(
        (c for c in df.columns if "외국인" in c), None
    )
    institution_col = next(
        (c for c in df.columns if "기관" in c and "합계" in c), None
    ) or next(
        (c for c in df.columns if "기관" in c), None
    )

    foreign_series = pd.to_numeric(df[foreign_col], errors="coerce") if foreign_col else pd.Series(dtype=float)
    institution_series = pd.to_numeric(df[institution_col], errors="coerce") if institution_col else pd.Series(dtype=float)

    daily = []
    for idx in df.index[-20:]:  # 최근 20일
        date_str = idx.strftime("%Y-%m-%d") if hasattr(idx, "strftime") else str(idx)
        daily.append({
            "date": date_str,
            "foreign": _to_billion(float(foreign_series.get(idx, 0) or 0)),
            "institution": _to_billion(float(institution_series.get(idx, 0) or 0)),
        })

    return {"foreign_daily": foreign_series, "institution_daily": institution_series, "daily": daily}


def _compute_alignment(foreign_3d: float, institution_3d: float, pattern_type: str | None) -> tuple[str, str, str]:
    """Returns (alignment, alignment_label, alignment_note)"""
    if pattern_type in _BULLISH_PATTERNS:
        pattern_bias = "bullish"
    elif pattern_type in _BEARISH_PATTERNS:
        pattern_bias = "bearish"
    else:
        return "neutral", "수급 중립", "패턴 없음"

    combined = foreign_3d * 0.6 + institution_3d * 0.4

    if abs(combined) < _FLOW_THRESHOLD_BILLION:
        return "neutral", "수급 뚜렷하지 않음", "외인+기관 합산 순매수 규모 미미"

    flow_is_bullish = combined > 0
    pattern_is_bullish = pattern_bias == "bullish"
    foreign_is_bullish = foreign_3d > _FLOW_THRESHOLD_BILLION
    institution_is_bullish = institution_3d > _FLOW_THRESHOLD_BILLION

    if foreign_is_bullish != institution_is_bullish and abs(foreign_3d) > _FLOW_THRESHOLD_BILLION and abs(institution_3d) > _FLOW_THRESHOLD_BILLION:
        label = f"외국인 {'순매수' if foreign_is_bullish else '순매도'} / 기관 {'순매수' if institution_is_bullish else '순매도'}"
        return "mixed", label, "외국인·기관 방향 엇갈림 — 신중한 접근 필요"

    if flow_is_bullish == pattern_is_bullish:
        label = "패턴과 수급 방향 일치"
        note = "외인+기관 자금이 패턴 방향을 지지"
        return "aligned", label, note
    else:
        label = "패턴과 수급 방향 반대"
        note = "외인+기관 자금이 패턴 방향과 반대 — 주의 필요"
        return "diverged", label, note


async def get_money_flow(code: str, pattern_type: str | None = None) -> dict | None:
    cache_key = f"{_CACHE_PREFIX}:{code}"
    cached = await cache_get(cache_key)
    if cached:
        # Re-compute alignment based on current pattern (alignment depends on pattern)
        alignment, alignment_label, alignment_note = _compute_alignment(
            cached.get("foreign_net_3d", 0),
            cached.get("institution_net_3d", 0),
            pattern_type,
        )
        cached.update({"alignment": alignment, "alignment_label": alignment_label, "alignment_note": alignment_note})
        return cached

    try:
        end = date.today()
        start = end - timedelta(days=30)
        df = await _fetch_trading_value(code, start.strftime("%Y%m%d"), end.strftime("%Y%m%d"))

        parsed = _parse_flow(df)
        foreign_s: pd.Series = parsed.get("foreign_daily", pd.Series(dtype=float))
        inst_s: pd.Series = parsed.get("institution_daily", pd.Series(dtype=float))
        daily: list[dict] = parsed.get("daily", [])

        foreign_3d = _to_billion(float(foreign_s.iloc[-3:].sum())) if len(foreign_s) >= 3 else 0.0
        foreign_10d = _to_billion(float(foreign_s.iloc[-10:].sum())) if len(foreign_s) >= 10 else 0.0
        institution_3d = _to_billion(float(inst_s.iloc[-3:].sum())) if len(inst_s) >= 3 else 0.0
        institution_10d = _to_billion(float(inst_s.iloc[-10:].sum())) if len(inst_s) >= 10 else 0.0

        alignment, alignment_label, alignment_note = _compute_alignment(foreign_3d, institution_3d, pattern_type)

        result = {
            "foreign_net_3d": foreign_3d,
            "foreign_net_10d": foreign_10d,
            "institution_net_3d": institution_3d,
            "institution_net_10d": institution_10d,
            "alignment": alignment,
            "alignment_label": alignment_label,
            "alignment_note": alignment_note,
            "daily": daily[-20:],
        }
        await cache_set(cache_key, result, ttl=_CACHE_TTL)
        return result
    except Exception as exc:
        logger.warning("money flow fetch failed for %s: %s", code, exc)
        return None
```

- [ ] **Step 2: 문법 검증**

```bash
cd backend && python -c "
import ast
ast.parse(open('app/services/money_flow_service.py', encoding='utf-8').read())
print('OK')
"
```

Expected: `OK`

- [ ] **Step 3: 커밋**

```bash
git add backend/app/services/money_flow_service.py
git commit -m "feat(B): add money flow service (foreign/institution net buying)"
```

---

### Task 8: schemas + symbols.py endpoint + analysis_service.py 통합

**Files:**
- Modify: `backend/app/api/schemas.py`
- Modify: `backend/app/api/routes/symbols.py`
- Modify: `backend/app/services/analysis_service.py`

- [ ] **Step 1: schemas.py에 MoneyFlowData 추가 + AnalysisResult에 money_flow 필드 추가**

`schemas.py`의 `AnalysisResult` 클래스 위에:

```python
class MoneyFlowDailyEntry(BaseModel):
    date: str
    foreign: float  # 억원
    institution: float


class MoneyFlowData(BaseModel):
    foreign_net_3d: float = 0.0
    foreign_net_10d: float = 0.0
    institution_net_3d: float = 0.0
    institution_net_10d: float = 0.0
    alignment: str = "neutral"
    alignment_label: str = ""
    alignment_note: str = ""
    daily: list[MoneyFlowDailyEntry] = Field(default_factory=list)
```

`AnalysisResult` 클래스의 `available_bars` 필드 이후에:
```python
    money_flow: MoneyFlowData | None = None
```

- [ ] **Step 2: symbols.py에 money-flow 엔드포인트 추가**

`symbols.py`의 기존 `/analysis` 엔드포인트 뒤에 추가:

```python
@router.get("/{symbol}/money-flow")
async def get_money_flow_endpoint(
    symbol: str,
    timeframe: str = Query(default=DEFAULT_TIMEFRAME),
) -> dict:
    from ...services.money_flow_service import get_money_flow
    # Get pattern_type from cached analysis if available
    cached_analysis = await cache_get(f"analysis:v9:{symbol}:{timeframe}")
    pattern_type = None
    if cached_analysis and cached_analysis.get("patterns"):
        pattern_type = cached_analysis["patterns"][0].get("pattern_type")
    result = await get_money_flow(symbol, pattern_type)
    if result is None:
        return {"alignment": "neutral", "alignment_label": "수급 데이터 없음", "alignment_note": "", "daily": [], "foreign_net_3d": 0, "foreign_net_10d": 0, "institution_net_3d": 0, "institution_net_10d": 0}
    return result
```

- [ ] **Step 3: analysis_service.py — analyze_symbol_dataframe에 money_flow 통합**

`analysis_service.py`에서 `analyze_symbol_dataframe` 함수를 찾아 반환 직전(return result 이전)에 money_flow 비동기 수집 추가:

```python
    # Money flow (non-blocking: skip if slow)
    try:
        from .money_flow_service import get_money_flow
        from ..api.schemas import MoneyFlowData, MoneyFlowDailyEntry
        primary_pattern_type = best_pattern.pattern_type if best_pattern else None
        mf_raw = await asyncio.wait_for(
            get_money_flow(symbol_info.code, primary_pattern_type),
            timeout=8.0,
        )
        if mf_raw:
            result.money_flow = MoneyFlowData(
                foreign_net_3d=mf_raw.get("foreign_net_3d", 0.0),
                foreign_net_10d=mf_raw.get("foreign_net_10d", 0.0),
                institution_net_3d=mf_raw.get("institution_net_3d", 0.0),
                institution_net_10d=mf_raw.get("institution_net_10d", 0.0),
                alignment=mf_raw.get("alignment", "neutral"),
                alignment_label=mf_raw.get("alignment_label", ""),
                alignment_note=mf_raw.get("alignment_note", ""),
                daily=[MoneyFlowDailyEntry(**d) for d in mf_raw.get("daily", [])],
            )
    except (asyncio.TimeoutError, Exception) as exc:
        logger.debug("money flow skipped for %s: %s", symbol_info.code, exc)
```

주의: `analyze_symbol_dataframe`이 `result`를 반환하는 위치를 먼저 `grep`으로 확인 후 정확한 위치에 삽입.

```bash
cd backend && grep -n "return result" app/services/analysis_service.py | tail -5
```

- [ ] **Step 4: 문법 검증**

```bash
cd backend && python -c "
import ast, sys
for f in ['app/api/schemas.py', 'app/api/routes/symbols.py', 'app/services/analysis_service.py']:
    ast.parse(open(f, encoding='utf-8').read())
    print('OK:', f)
"
```

Expected: 세 파일 모두 OK

- [ ] **Step 5: 캐시 키 버전 bump (money_flow 포함 결과이므로)**

`symbols.py`에서 이미 `analysis:v9`이므로 그대로 유지. money_flow는 별도 캐시 키 사용.

- [ ] **Step 6: 커밋**

```bash
git add backend/app/api/schemas.py backend/app/api/routes/symbols.py backend/app/services/analysis_service.py
git commit -m "feat(B): add money flow endpoint + embed money_flow in AnalysisResult"
```

---

### Task 9: MoneyFlowCard 컴포넌트

**Files:**
- Create: `frontend/src/components/chart/MoneyFlowCard.tsx`

- [ ] **Step 1: MoneyFlowCard.tsx 생성**

```tsx
import { TrendingDown, TrendingUp, Minus } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Card } from '@/components/ui/Card'
import type { MoneyFlowData } from '@/types/api'

interface MoneyFlowCardProps {
  data: MoneyFlowData
}

function FlowRow({ label, value3d, value10d }: { label: string; value3d: number; value10d: number }) {
  const is3dUp = value3d > 0
  const is10dUp = value10d > 0
  return (
    <div className="flex items-center gap-3">
      <span className="w-16 shrink-0 text-xs text-muted-foreground">{label}</span>
      <div className="flex items-center gap-1">
        {value3d === 0 ? (
          <Minus size={11} className="text-muted-foreground" />
        ) : is3dUp ? (
          <TrendingUp size={11} className="text-emerald-400" />
        ) : (
          <TrendingDown size={11} className="text-rose-400" />
        )}
        <span className={cn('text-xs font-semibold', value3d === 0 ? 'text-muted-foreground' : is3dUp ? 'text-emerald-400' : 'text-rose-400')}>
          {value3d > 0 ? '+' : ''}{value3d.toFixed(0)}억
        </span>
        <span className="text-xs text-muted-foreground">(3일)</span>
      </div>
      <div className="flex items-center gap-1">
        <span className={cn('text-xs', value10d === 0 ? 'text-muted-foreground' : is10dUp ? 'text-emerald-400/70' : 'text-rose-400/70')}>
          {value10d > 0 ? '+' : ''}{value10d.toFixed(0)}억
        </span>
        <span className="text-xs text-muted-foreground">(10일)</span>
      </div>
    </div>
  )
}

function MiniSparkline({ daily }: { daily: MoneyFlowData['daily'] }) {
  if (!daily.length) return null
  const values = daily.map(d => d.foreign)
  const max = Math.max(...values.map(Math.abs), 1)
  return (
    <div className="flex h-8 items-end gap-px">
      {values.slice(-15).map((v, i) => (
        <div
          key={i}
          className={cn('flex-1 rounded-sm', v >= 0 ? 'bg-emerald-400/50' : 'bg-rose-400/50')}
          style={{ height: `${Math.max(15, (Math.abs(v) / max) * 100)}%` }}
        />
      ))}
    </div>
  )
}

const ALIGNMENT_CONFIG = {
  aligned: { label: '패턴과 정렬', color: 'text-emerald-400', bg: 'border-emerald-400/20 bg-emerald-400/6' },
  diverged: { label: '패턴과 반대', color: 'text-rose-400', bg: 'border-rose-400/20 bg-rose-400/6' },
  mixed: { label: '외인/기관 혼조', color: 'text-amber-400', bg: 'border-amber-400/20 bg-amber-400/6' },
  neutral: { label: '수급 중립', color: 'text-muted-foreground', bg: 'border-border bg-background/55' },
} as const

export function MoneyFlowCard({ data }: MoneyFlowCardProps) {
  const alignCfg = ALIGNMENT_CONFIG[data.alignment as keyof typeof ALIGNMENT_CONFIG] ?? ALIGNMENT_CONFIG.neutral
  return (
    <Card className="space-y-3">
      <div className="flex items-center justify-between">
        <span className="text-sm font-semibold">외국인 / 기관 수급</span>
        <span className={cn('rounded border px-2 py-0.5 text-xs font-medium', alignCfg.bg, alignCfg.color)}>
          {alignCfg.label}
        </span>
      </div>

      <div className="space-y-2">
        <FlowRow label="외국인" value3d={data.foreign_net_3d} value10d={data.foreign_net_10d} />
        <FlowRow label="기관" value3d={data.institution_net_3d} value10d={data.institution_net_10d} />
      </div>

      {data.daily.length > 0 && (
        <div className="space-y-1">
          <p className="text-xs text-muted-foreground">외국인 순매수 추이 (최근 15일)</p>
          <MiniSparkline daily={data.daily} />
        </div>
      )}

      {data.alignment_note && (
        <p className="text-xs leading-relaxed text-muted-foreground">{data.alignment_note}</p>
      )}
    </Card>
  )
}
```

- [ ] **Step 2: 커밋**

```bash
git add frontend/src/components/chart/MoneyFlowCard.tsx
git commit -m "feat(B): add MoneyFlowCard component"
```

---

### Task 10: AnalysisPanel에 MoneyFlowCard 통합

**Files:**
- Modify: `frontend/src/components/chart/AnalysisPanel.tsx`

- [ ] **Step 1: import 추가**

`AnalysisPanel.tsx` 상단 import 블록에:

```tsx
import { MoneyFlowCard } from '@/components/chart/MoneyFlowCard'
```

- [ ] **Step 2: overview 탭에 MoneyFlowCard 추가**

`AnalysisPanel.tsx`의 `{activeTab === 'overview' && (` 블록에서 `PatternSummaryCard` 이후에 추가:

```tsx
{activeTab === 'overview' && (
  <div className="space-y-3">
    {!analysis.no_signal_flag && bestPattern && <PatternSummaryCard pattern={bestPattern} analysis={analysis} />}
    {analysis.money_flow && <MoneyFlowCard data={analysis.money_flow} />}
    <ActionPlanCard analysis={analysis} />
    <DecisionSummaryGrid analysis={analysis} />
    <DecisionSupportCard analysis={analysis} />
    <ProjectionCard analysis={analysis} />
  </div>
)}
```

- [ ] **Step 3: TypeScript 검증**

```bash
cd frontend && npx tsc --noEmit 2>&1 | head -20
```

Expected: 오류 없음

- [ ] **Step 4: 커밋**

```bash
git add frontend/src/components/chart/AnalysisPanel.tsx
git commit -m "feat(B): integrate MoneyFlowCard into AnalysisPanel overview tab"
```

---

## ── Sub-project C: Risk Engine ──

---

### Task 11: Zustand store에 RiskSettings 추가

**Files:**
- Modify: `frontend/src/store/app.ts`

- [ ] **Step 1: RiskSettings 인터페이스 + store 필드 추가**

`app.ts`의 `AppStore` 인터페이스에 추가:

```typescript
// 기존 인터페이스에 추가
interface RiskSettings {
  accountSize: number       // 계좌 총액 (원), 0 = 미설정
  riskPerTrade: number      // 1회 최대 리스크 비율 (0.02 = 2%)
  atrMultiplier: number     // ATR 손절 배수 (기본 2.0)
  preferAtrStop: boolean    // true=ATR 기준, false=패턴 기준
}

interface AppStore {
  // ... 기존 필드 ...
  riskSettings: RiskSettings
  setRiskSettings: (settings: Partial<RiskSettings>) => void
}
```

`create` 호출 내부 초기값에 추가:

```typescript
riskSettings: {
  accountSize: 0,
  riskPerTrade: 0.02,
  atrMultiplier: 2.0,
  preferAtrStop: false,
},
setRiskSettings: (settings) => set(state => ({
  riskSettings: { ...state.riskSettings, ...settings },
})),
```

`partialize`에 `riskSettings` 추가:

```typescript
partialize: state => ({
  watchlist: state.watchlist,
  selectedTimeframe: state.selectedTimeframe,
  riskSettings: state.riskSettings,  // 추가
}),
```

- [ ] **Step 2: TypeScript 검증**

```bash
cd frontend && npx tsc --noEmit 2>&1 | head -20
```

Expected: 오류 없음

- [ ] **Step 3: 커밋**

```bash
git add frontend/src/store/app.ts
git commit -m "feat(C): add RiskSettings to Zustand store"
```

---

### Task 12: ATR 계산 유틸 + PositionSizerCard

**Files:**
- Create: `frontend/src/lib/atr.ts`
- Create: `frontend/src/components/chart/PositionSizerCard.tsx`

- [ ] **Step 1: atr.ts 생성**

```typescript
import type { OHLCVBar } from '@/types/api'

/**
 * Calculate Average True Range (ATR) over `period` bars.
 * True Range = max(High-Low, |High-PrevClose|, |Low-PrevClose|)
 */
export function calcATR(bars: OHLCVBar[], period = 14): number {
  if (bars.length < period + 1) return 0

  const trueRanges: number[] = []
  for (let i = 1; i < bars.length; i++) {
    const curr = bars[i]
    const prev = bars[i - 1]
    const tr = Math.max(
      curr.high - curr.low,
      Math.abs(curr.high - prev.close),
      Math.abs(curr.low - prev.close),
    )
    trueRanges.push(tr)
  }

  // Simple moving average of last `period` TRs
  const recent = trueRanges.slice(-period)
  return recent.reduce((sum, v) => sum + v, 0) / recent.length
}

export interface StopInfo {
  price: number
  label: string
  distancePct: number
}

export function atrStop(currentPrice: number, atr: number, multiplier: number, bullish: boolean): StopInfo {
  const price = bullish
    ? currentPrice - atr * multiplier
    : currentPrice + atr * multiplier
  const distancePct = Math.abs(currentPrice - price) / currentPrice * 100
  return { price, label: `ATR×${multiplier}`, distancePct }
}

export interface PositionCalc {
  maxLossKrw: number          // 최대 손실 금액
  stopPrice: number           // 손절가
  stopDistancePct: number     // 손절 거리 %
  shares: number              // 매수 수량
  positionValue: number       // 투자 금액
  positionPct: number         // 계좌 대비 비중 %
  rewardRisk: number          // R:R 비율
  rewardRiskOk: boolean       // R:R 1:2 이상 여부
}

export function calcPosition(
  accountSize: number,
  riskPct: number,
  currentPrice: number,
  stopPrice: number,
  targetPrice: number | null,
): PositionCalc | null {
  if (!accountSize || !currentPrice || !stopPrice) return null
  const stopDistance = Math.abs(currentPrice - stopPrice)
  if (stopDistance <= 0) return null

  const maxLossKrw = accountSize * riskPct
  const shares = Math.floor(maxLossKrw / stopDistance)
  const positionValue = shares * currentPrice
  const positionPct = (positionValue / accountSize) * 100
  const stopDistancePct = (stopDistance / currentPrice) * 100

  let rewardRisk = 0
  if (targetPrice) {
    const reward = Math.abs(targetPrice - currentPrice)
    rewardRisk = reward / stopDistance
  }

  return {
    maxLossKrw,
    stopPrice,
    stopDistancePct,
    shares,
    positionValue,
    positionPct,
    rewardRisk,
    rewardRiskOk: rewardRisk >= 2.0,
  }
}
```

- [ ] **Step 2: PositionSizerCard.tsx 생성**

```tsx
import { useState } from 'react'
import { Calculator, Settings } from 'lucide-react'
import { cn, fmtPrice } from '@/lib/utils'
import { Card } from '@/components/ui/Card'
import { useAppStore } from '@/store/app'
import type { AnalysisResult, OHLCVBar } from '@/types/api'
import { calcATR, atrStop, calcPosition } from '@/lib/atr'

interface PositionSizerCardProps {
  analysis: AnalysisResult
  bars: OHLCVBar[]
  currentPrice?: number
  onOpenSettings: () => void
}

export function PositionSizerCard({ analysis, bars, currentPrice, onOpenSettings }: PositionSizerCardProps) {
  const { riskSettings } = useAppStore()
  const { accountSize, riskPerTrade, atrMultiplier, preferAtrStop } = riskSettings
  const [useAtr, setUseAtr] = useState(preferAtrStop)

  const bestPattern = analysis.patterns[0]
  const price = currentPrice ?? 0
  const atr = calcATR(bars)
  const bullish = analysis.p_up > analysis.p_down

  const patternStop = bestPattern?.invalidation_level ?? null
  const targetPrice = bestPattern?.target_level ?? null
  const atrStopInfo = price && atr ? atrStop(price, atr, atrMultiplier, bullish) : null
  const stopPrice = useAtr ? (atrStopInfo?.price ?? patternStop) : (patternStop ?? atrStopInfo?.price)

  const calc = accountSize && price && stopPrice
    ? calcPosition(accountSize, riskPerTrade, price, stopPrice, targetPrice)
    : null

  const notConfigured = !accountSize

  return (
    <Card className="space-y-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Calculator size={14} className="text-primary" />
          <span className="text-sm font-semibold">포지션 계산기</span>
        </div>
        <button
          onClick={onOpenSettings}
          className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
        >
          <Settings size={12} />
          설정
        </button>
      </div>

      {notConfigured ? (
        <p className="text-xs leading-relaxed text-muted-foreground">
          ⚙️ 설정에서 계좌 규모를 입력하면 포지션 계산이 됩니다.
        </p>
      ) : (
        <>
          {/* 손절 기준 선택 */}
          <div className="space-y-2">
            <p className="text-xs font-medium text-muted-foreground">손절 기준</p>
            <div className="flex gap-2">
              {[false, true].map(isAtr => {
                const label = isAtr ? `ATR×${atrMultiplier}` : '패턴 기준'
                const stopInfo = isAtr ? atrStopInfo : (patternStop ? { price: patternStop, distancePct: Math.abs(price - patternStop) / price * 100 } : null)
                const active = useAtr === isAtr
                return (
                  <button
                    key={String(isAtr)}
                    onClick={() => setUseAtr(isAtr)}
                    disabled={!stopInfo}
                    className={cn(
                      'flex-1 rounded-lg border px-2 py-2 text-left text-xs transition-colors',
                      active ? 'border-primary/40 bg-primary/10 text-foreground' : 'border-border bg-background/55 text-muted-foreground',
                      !stopInfo && 'cursor-not-allowed opacity-40',
                    )}
                  >
                    <div className="font-medium">{label}</div>
                    {stopInfo && (
                      <div className="mt-0.5 text-muted-foreground">
                        {fmtPrice(stopInfo.price)} ({stopInfo.distancePct.toFixed(1)}% 거리)
                      </div>
                    )}
                  </button>
                )
              })}
            </div>
          </div>

          {/* 계산 결과 */}
          {calc ? (
            <div className="space-y-2">
              <div className="grid grid-cols-2 gap-2">
                <ResultRow label="최대 손실" value={`${(calc.maxLossKrw / 1e4).toFixed(0)}만원`} />
                <ResultRow label="매수 수량" value={`${calc.shares.toLocaleString()}주`} />
                <ResultRow label="투자 금액" value={`${(calc.positionValue / 1e4).toFixed(0)}만원`} />
                <ResultRow
                  label="계좌 비중"
                  value={`${calc.positionPct.toFixed(1)}%`}
                  warn={calc.positionPct > 20}
                />
              </div>
              {calc.rewardRisk > 0 && (
                <div className={cn(
                  'rounded-lg border p-2 text-xs',
                  calc.rewardRiskOk
                    ? 'border-emerald-400/20 bg-emerald-400/6 text-emerald-400'
                    : 'border-amber-400/20 bg-amber-400/6 text-amber-400',
                )}>
                  리스크 보상비 1 : {calc.rewardRisk.toFixed(1)}
                  {calc.rewardRiskOk ? '  ✅ 적정' : '  ⚠️ 낮음 (기준: 1:2 이상)'}
                </div>
              )}
            </div>
          ) : (
            <p className="text-xs text-muted-foreground">
              패턴 손절가 또는 현재가 정보가 없어 계산이 어렵습니다.
            </p>
          )}

          <div className="text-xs text-muted-foreground">
            계좌 {(accountSize / 1e4).toFixed(0)}만원 · 리스크 {(riskPerTrade * 100).toFixed(1)}%
          </div>
        </>
      )}
    </Card>
  )
}

function ResultRow({ label, value, warn }: { label: string; value: string; warn?: boolean }) {
  return (
    <div className="rounded border border-border bg-background/55 px-2.5 py-2">
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className={cn('mt-0.5 text-sm font-semibold', warn ? 'text-amber-400' : 'text-foreground')}>
        {value}
        {warn && <span className="ml-1 text-xs">⚠️</span>}
      </div>
    </div>
  )
}
```

- [ ] **Step 3: TypeScript 검증**

```bash
cd frontend && npx tsc --noEmit 2>&1 | head -20
```

Expected: 오류 없음

- [ ] **Step 4: 커밋**

```bash
git add frontend/src/lib/atr.ts frontend/src/components/chart/PositionSizerCard.tsx
git commit -m "feat(C): add ATR utility + PositionSizerCard component"
```

---

### Task 13: RiskSettingsDrawer + AnalysisPanel + Header 통합

**Files:**
- Create: `frontend/src/components/RiskSettingsDrawer.tsx`
- Modify: `frontend/src/components/chart/AnalysisPanel.tsx`

- [ ] **Step 1: RiskSettingsDrawer.tsx 생성**

```tsx
import { useState } from 'react'
import { X } from 'lucide-react'
import { Card } from '@/components/ui/Card'
import { useAppStore } from '@/store/app'

interface RiskSettingsDrawerProps {
  open: boolean
  onClose: () => void
}

export function RiskSettingsDrawer({ open, onClose }: RiskSettingsDrawerProps) {
  const { riskSettings, setRiskSettings } = useAppStore()
  const [accountSize, setAccountSize] = useState(
    riskSettings.accountSize > 0 ? String(Math.round(riskSettings.accountSize / 1e4)) : '',
  )
  const [riskPct, setRiskPct] = useState(String(riskSettings.riskPerTrade * 100))
  const [atrMult, setAtrMult] = useState(String(riskSettings.atrMultiplier))

  if (!open) return null

  const handleSave = () => {
    const size = parseFloat(accountSize) * 1e4
    const pct = parseFloat(riskPct) / 100
    const mult = parseFloat(atrMult)
    if (!isNaN(size) && !isNaN(pct) && !isNaN(mult)) {
      setRiskSettings({ accountSize: size, riskPerTrade: pct, atrMultiplier: mult })
    }
    onClose()
  }

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center sm:items-center">
      <div className="absolute inset-0 bg-black/50" onClick={onClose} />
      <Card className="relative z-10 w-full max-w-md space-y-4 p-5">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold">리스크 설정</h2>
          <button onClick={onClose} className="text-muted-foreground hover:text-foreground">
            <X size={16} />
          </button>
        </div>

        <div className="space-y-3">
          <div>
            <label className="text-xs font-medium text-muted-foreground">계좌 규모 (만원)</label>
            <input
              type="number"
              value={accountSize}
              onChange={e => setAccountSize(e.target.value)}
              placeholder="예: 10000 (1억)"
              className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-primary"
            />
          </div>

          <div>
            <label className="text-xs font-medium text-muted-foreground">
              1회 최대 리스크 (%) — 현재: {riskPct}%
            </label>
            <input
              type="range"
              min="0.5"
              max="5"
              step="0.5"
              value={riskPct}
              onChange={e => setRiskPct(e.target.value)}
              className="mt-1 w-full"
            />
            <div className="flex justify-between text-xs text-muted-foreground">
              <span>0.5%</span><span>5%</span>
            </div>
          </div>

          <div>
            <label className="text-xs font-medium text-muted-foreground">ATR 손절 배수</label>
            <div className="mt-1 flex gap-2">
              {['1.5', '2.0', '2.5', '3.0'].map(v => (
                <button
                  key={v}
                  onClick={() => setAtrMult(v)}
                  className={`flex-1 rounded-lg border py-1.5 text-xs ${
                    atrMult === v
                      ? 'border-primary bg-primary/10 text-foreground'
                      : 'border-border text-muted-foreground hover:text-foreground'
                  }`}
                >
                  ×{v}
                </button>
              ))}
            </div>
          </div>
        </div>

        <div className="flex gap-2">
          <button
            onClick={handleSave}
            className="flex-1 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground"
          >
            저장
          </button>
          <button
            onClick={onClose}
            className="rounded-lg border border-border px-4 py-2 text-sm text-muted-foreground"
          >
            취소
          </button>
        </div>
      </Card>
    </div>
  )
}
```

- [ ] **Step 2: AnalysisPanel.tsx — props + import + PositionSizerCard 추가**

`AnalysisPanel.tsx`의 `AnalysisPanelProps` 인터페이스 수정:

```tsx
interface AnalysisPanelProps {
  analysis: AnalysisResult
  symbol?: string
  timeframe?: string
  bars?: OHLCVBar[]         // ATR 계산용 (ChartPage에서 내려줌)
  currentPrice?: number     // 현재가 (ChartPage에서 내려줌)
}
```

`AnalysisPanel.tsx` 상단 import에 추가:

```tsx
import { useState } from 'react'  // 이미 있으면 스킵
import { PositionSizerCard } from '@/components/chart/PositionSizerCard'
import { RiskSettingsDrawer } from '@/components/RiskSettingsDrawer'
import type { OHLCVBar } from '@/types/api'
```

`AnalysisPanel` 함수 시그니처 수정:
```tsx
export function AnalysisPanel({ analysis, symbol, timeframe, bars = [], currentPrice }: AnalysisPanelProps) {
```

함수 내부 `const bestPattern = analysis.patterns[0]` 이후에:
```tsx
  const [settingsOpen, setSettingsOpen] = useState(false)
```

`setup` 탭 렌더링 블록 마지막 `ActiveSetupCard` 이후에:
```tsx
<PositionSizerCard
  analysis={analysis}
  bars={bars}
  currentPrice={currentPrice}
  onOpenSettings={() => setSettingsOpen(true)}
/>
```

반환 JSX 최하단 `</div>` 닫기 직전에:
```tsx
<RiskSettingsDrawer open={settingsOpen} onClose={() => setSettingsOpen(false)} />
```

- [ ] **Step 3: ChartPage.tsx — bars + currentPrice를 AnalysisPanel에 전달**

`ChartPage.tsx`에서 `<AnalysisPanel>` 호출 위치를 찾아 props 추가:

```tsx
<AnalysisPanel
  analysis={analysisQ.data}
  symbol={symbol}
  timeframe={timeframe}
  bars={barsQ.data ?? []}
  currentPrice={priceQ.data?.close}
/>
```

`priceQ`가 없다면 barsQ 마지막 bar의 close 사용:

```tsx
currentPrice={barsQ.data?.at(-1)?.close}
```

- [ ] **Step 4: TypeScript 검증**

```bash
cd frontend && npx tsc --noEmit 2>&1 | head -30
```

Expected: 오류 없음

- [ ] **Step 5: 커밋**

```bash
git add frontend/src/components/RiskSettingsDrawer.tsx frontend/src/components/chart/AnalysisPanel.tsx frontend/src/pages/ChartPage.tsx
git commit -m "feat(C): add PositionSizerCard + RiskSettingsDrawer + integrate into AnalysisPanel"
```

---

### Task 14: 최종 빌드 검증 + GitHub push + 배포

**Files:** 없음 (검증 + 배포만)

- [ ] **Step 1: 전체 TypeScript 타입 검증**

```bash
cd frontend && npx tsc --noEmit 2>&1
```

Expected: 오류 없음

- [ ] **Step 2: 백엔드 전 파일 문법 검증**

```bash
cd backend && python -c "
import ast, os
errors = []
for root, _, files in os.walk('app'):
    for f in files:
        if f.endswith('.py') and '__pycache__' not in root:
            path = os.path.join(root, f)
            try:
                ast.parse(open(path, encoding='utf-8').read())
            except SyntaxError as e:
                errors.append(f'{path}: {e}')
if errors:
    print('\n'.join(errors))
    exit(1)
else:
    print(f'All OK')
"
```

Expected: `All OK`

- [ ] **Step 3: GitHub push**

```bash
git push origin main
```

Expected: 커밋들이 origin/main에 push됨

- [ ] **Step 4: Vercel 배포 확인 (1~2분 대기)**

Vercel 대시보드 또는 MCP로 최신 배포 상태 READY 확인

- [ ] **Step 5: Render 백엔드 헬스체크**

```bash
curl -s -o /dev/null -w "%{http_code}" --max-time 30 https://stock-chart-helper-api.onrender.com/health
```

Expected: `200`

---

## 실행 체크리스트

### Sub-project A (Market Intelligence)
- [ ] Task 1: schemas + market_regime_service
- [ ] Task 2: sector_service
- [ ] Task 3: dashboard endpoints
- [ ] Task 4: Frontend types + api
- [ ] Task 5: MarketRegimeBar + SectorHeatmap
- [ ] Task 6: DashboardPage + DashboardCard

### Sub-project B (Smart Money Flow)
- [ ] Task 7: money_flow_service
- [ ] Task 8: schemas + endpoint + analysis 통합
- [ ] Task 9: MoneyFlowCard
- [ ] Task 10: AnalysisPanel 통합

### Sub-project C (Risk Engine)
- [ ] Task 11: Zustand RiskSettings
- [ ] Task 12: atr.ts + PositionSizerCard
- [ ] Task 13: RiskSettingsDrawer + AnalysisPanel + ChartPage
- [ ] Task 14: 최종 빌드 + 배포
