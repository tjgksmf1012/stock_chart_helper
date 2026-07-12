# 트레이딩 랩 코어 (Phase 1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 비용·생존편향을 반영한 워크포워드 검증 엔진(`backend/app/lab/`)을 만들고, 기존 패턴 엔진을 첫 피검체로 돌려 "현 시스템의 비용 차감 후 성적"을 숫자로 낸다.

**Architecture:** 순수 함수 중심의 lab 모듈 4+2개(types/costs/simulate/metrics/walkforward/universe) + 랜덤 벤치마크 + 레거시 패턴 어댑터 + CLI 러너. IO(시세/유니버스 로딩)는 CLI에서 주입하고, 엔진은 전부 합성 데이터로 단위 테스트한다.

**Tech Stack:** Python 3.12, pandas, numpy, pytest (기존 backend 스택 그대로). 스펙: `docs/superpowers/specs/2026-07-12-evidence-first-trading-lab-design.md`

**실행 규칙:** 모든 명령은 `backend/` 디렉터리에서 `.venv/Scripts/python.exe -m pytest ...`로 실행한다 (Windows venv).

---

## File Structure

```
backend/app/lab/__init__.py        # 빈 패키지 마커
backend/app/lab/types.py           # Signal, Trade 데이터클래스
backend/app/lab/costs.py           # CostModel (수수료+세금+슬리피지)
backend/app/lab/simulate.py        # 신호 → 트레이드 시뮬레이션 (보수적 체결 규칙)
backend/app/lab/metrics.py         # Summary, bootstrap CI, 판정(verdict)
backend/app/lab/walkforward.py     # 워크포워드 윈도우 + 하네스
backend/app/lab/universe.py        # 시점 고정 유니버스 (순수 선택 + pykrx IO 래퍼)
backend/app/lab/baselines.py       # 랜덤 진입 벤치마크 (동일 청산 근사)
backend/app/strategies/__init__.py # 빈 패키지 마커
backend/app/strategies/legacy_patterns.py  # 기존 PatternEngine 어댑터 (첫 피검체)
backend/scripts/run_lab.py         # CLI 러너 (JSON 리포트 저장 + 콘솔 출력)
backend/tests/lab/__init__.py
backend/tests/lab/conftest.py      # 합성 시세 fixture
backend/tests/lab/test_costs.py
backend/tests/lab/test_simulate.py
backend/tests/lab/test_metrics.py
backend/tests/lab/test_walkforward.py
backend/tests/lab/test_universe.py
backend/tests/lab/test_baselines.py
backend/tests/lab/test_legacy_adapter.py
```

---

### Task 1: 패키지 골격 + 타입 정의

**Files:**
- Create: `backend/app/lab/__init__.py`, `backend/app/lab/types.py`
- Create: `backend/app/strategies/__init__.py`
- Create: `backend/tests/lab/__init__.py`

- [ ] **Step 1: 파일 생성**

`backend/app/lab/__init__.py` (빈 파일), `backend/app/strategies/__init__.py` (빈 파일), `backend/tests/lab/__init__.py` (빈 파일).

`backend/app/lab/types.py`:

```python
"""랩 공용 타입 — 신호와 시뮬레이션 트레이드.

Signal.signal_date는 "이 봉의 종가까지의 정보만으로 신호가 확정된 날"이다.
진입은 항상 다음 봉 시가로 시뮬레이션한다(신호 봉 종가 진입은 미래 참조).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class Signal:
    code: str
    signal_date: date
    stop_price: float
    target_price: float | None = None
    max_holding_days: int = 40  # 거래일 기준 시간 청산


@dataclass(frozen=True)
class Trade:
    code: str
    strategy_id: str
    entry_date: date
    entry_price: float
    exit_date: date
    exit_price: float
    exit_reason: str  # "stop" | "target" | "time" | "data_end"
    gross_return_pct: float  # 비용 차감 전 (참고용, 화면 노출 금지)
    net_return_pct: float    # 비용 차감 후 — 모든 지표는 이 값 기준
```

- [ ] **Step 2: import 확인**

Run: `cd backend && .venv/Scripts/python.exe -c "from app.lab.types import Signal, Trade; print('ok')"`
Expected: `ok`

- [ ] **Step 3: Commit**

```bash
git add backend/app/lab backend/app/strategies backend/tests/lab
git commit -m "lab: 패키지 골격 + Signal/Trade 타입"
```

---

### Task 2: 비용 모델 (costs.py)

**Files:**
- Create: `backend/app/lab/costs.py`
- Test: `backend/tests/lab/test_costs.py`

- [ ] **Step 1: 실패하는 테스트 작성**

`backend/tests/lab/test_costs.py`:

```python
from app.lab.costs import CostModel


class TestCostModel:
    def test_default_round_trip_is_conservative(self):
        # 기본값: 매수(수수료 0.015% + 슬리피지 0.1%) + 매도(수수료 + 거래세 0.15% + 슬리피지)
        cm = CostModel()
        assert 0.003 <= cm.round_trip_pct <= 0.005  # 왕복 0.3~0.5% 사이

    def test_net_return_flat_price_is_negative(self):
        # 같은 가격에 사고 팔면 비용만큼 손실
        cm = CostModel()
        net = cm.net_return_pct(entry_price=10_000, exit_price=10_000)
        assert net < 0
        assert abs(net + cm.round_trip_pct) < 0.0005  # 근사적으로 -왕복비용

    def test_net_return_math_is_multiplicative(self):
        # 체결가에 비용을 곱셈으로 반영: (매도가*(1-매도비용)) / (매수가*(1+매수비용)) - 1
        cm = CostModel(commission_pct=0.001, tax_pct=0.002, slippage_pct=0.0)
        net = cm.net_return_pct(entry_price=100.0, exit_price=110.0)
        expected = (110.0 * (1 - 0.003)) / (100.0 * (1 + 0.001)) - 1
        assert abs(net - expected) < 1e-12

    def test_zero_cost_model_returns_gross(self):
        cm = CostModel(commission_pct=0.0, tax_pct=0.0, slippage_pct=0.0)
        assert abs(cm.net_return_pct(100.0, 105.0) - 0.05) < 1e-12
```

- [ ] **Step 2: 실패 확인**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/lab/test_costs.py -q`
Expected: FAIL (`ModuleNotFoundError: app.lab.costs`)

- [ ] **Step 3: 구현**

`backend/app/lab/costs.py`:

```python
"""거래 비용 모델 — 모든 랩 수익률은 이 모델을 통과한 net 값만 쓴다.

기본값은 한국 주식 개인 기준 보수적 추정:
- 수수료 편도 0.015%, 매도 시 거래세 0.15%, 슬리피지 편도 0.1%
왕복 약 0.38%. 비용 차감 전 수치는 화면에 표시하지 않는다(스펙).
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CostModel:
    commission_pct: float = 0.00015
    tax_pct: float = 0.0015
    slippage_pct: float = 0.001

    @property
    def entry_cost_pct(self) -> float:
        return self.commission_pct + self.slippage_pct

    @property
    def exit_cost_pct(self) -> float:
        return self.commission_pct + self.tax_pct + self.slippage_pct

    @property
    def round_trip_pct(self) -> float:
        return self.entry_cost_pct + self.exit_cost_pct

    def net_return_pct(self, entry_price: float, exit_price: float) -> float:
        """실효 매수단가/매도단가 기준 순수익률."""
        buy = entry_price * (1 + self.entry_cost_pct)
        sell = exit_price * (1 - self.exit_cost_pct)
        return sell / buy - 1
```

- [ ] **Step 4: 통과 확인**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/lab/test_costs.py -q`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add backend/app/lab/costs.py backend/tests/lab/test_costs.py
git commit -m "lab: 거래 비용 모델 (왕복 ~0.38% 보수 기본값)"
```

---

### Task 3: 합성 시세 fixture (tests/lab/conftest.py)

**Files:**
- Create: `backend/tests/lab/conftest.py`

- [ ] **Step 1: fixture 작성**

`backend/tests/lab/conftest.py`:

```python
"""lab 테스트 공용 합성 시세 — 결정적(시드 고정)이고 날짜가 명시적이다."""
from __future__ import annotations

from datetime import date

import pandas as pd
import pytest


def make_bars(rows: list[tuple[str, float, float, float, float]]) -> pd.DataFrame:
    """(date_str, open, high, low, close) 목록으로 bars DataFrame 생성."""
    return pd.DataFrame(
        [
            {
                "date": pd.Timestamp(d),
                "open": o,
                "high": h,
                "low": lo,
                "close": c,
                "volume": 1_000_000,
            }
            for d, o, h, lo, c in rows
        ]
    )


@pytest.fixture
def flat_bars() -> pd.DataFrame:
    """10거래일 동안 100 부근 횡보 — 시간 청산 테스트용."""
    return make_bars(
        [(f"2025-01-{i:02d}", 100.0, 101.0, 99.0, 100.0) for i in range(2, 12)]
    )
```

- [ ] **Step 2: import 확인**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/lab -q --collect-only 2>&1 | tail -2`
Expected: 에러 없이 수집 완료

- [ ] **Step 3: Commit**

```bash
git add backend/tests/lab/conftest.py
git commit -m "lab: 테스트용 합성 시세 fixture"
```

---

### Task 4: 트레이드 시뮬레이터 (simulate.py)

**Files:**
- Create: `backend/app/lab/simulate.py`
- Test: `backend/tests/lab/test_simulate.py`

- [ ] **Step 1: 실패하는 테스트 작성**

`backend/tests/lab/test_simulate.py`:

```python
from datetime import date

from app.lab.costs import CostModel
from app.lab.simulate import simulate_trades
from app.lab.types import Signal

from .conftest import make_bars

NO_COST = CostModel(commission_pct=0.0, tax_pct=0.0, slippage_pct=0.0)


class TestEntryRule:
    def test_entry_is_next_bar_open(self):
        bars = make_bars([
            ("2025-01-02", 100, 101, 99, 100),   # 신호 봉
            ("2025-01-03", 102, 103, 101, 102),  # 진입 봉 (시가 102)
            ("2025-01-06", 102, 120, 101, 118),  # 목표 도달
        ])
        sig = Signal(code="A", signal_date=date(2025, 1, 2), stop_price=95.0, target_price=110.0)
        trades = simulate_trades(bars, [sig], NO_COST, strategy_id="t")
        assert len(trades) == 1
        assert trades[0].entry_price == 102.0
        assert trades[0].entry_date == date(2025, 1, 3)

    def test_signal_on_last_bar_is_skipped(self):
        bars = make_bars([("2025-01-02", 100, 101, 99, 100)])
        sig = Signal(code="A", signal_date=date(2025, 1, 2), stop_price=95.0)
        assert simulate_trades(bars, [sig], NO_COST, strategy_id="t") == []


class TestExitRules:
    def test_stop_checked_before_target_same_bar(self):
        # 한 봉에서 손절/목표 둘 다 스치면 보수적으로 손절 우선 (기존 백테스트 관행)
        bars = make_bars([
            ("2025-01-02", 100, 101, 99, 100),
            ("2025-01-03", 100, 115, 94, 96),  # low가 stop(95) 아래, high가 target(110) 위
        ])
        sig = Signal(code="A", signal_date=date(2025, 1, 2), stop_price=95.0, target_price=110.0)
        trades = simulate_trades(bars, [sig], NO_COST, strategy_id="t")
        assert trades[0].exit_reason == "stop"
        assert trades[0].exit_price == 95.0

    def test_gap_down_open_below_stop_exits_at_open(self):
        bars = make_bars([
            ("2025-01-02", 100, 101, 99, 100),
            ("2025-01-03", 90, 92, 88, 91),  # 시가부터 stop(95) 아래 갭
        ])
        sig = Signal(code="A", signal_date=date(2025, 1, 2), stop_price=95.0)
        trades = simulate_trades(bars, [sig], NO_COST, strategy_id="t")
        assert trades[0].exit_reason == "stop"
        assert trades[0].exit_price == 90.0  # stop가 아니라 실제 체결 가능한 시가

    def test_target_hit_exits_at_target(self):
        bars = make_bars([
            ("2025-01-02", 100, 101, 99, 100),
            ("2025-01-03", 101, 112, 100, 111),
        ])
        sig = Signal(code="A", signal_date=date(2025, 1, 2), stop_price=95.0, target_price=110.0)
        trades = simulate_trades(bars, [sig], NO_COST, strategy_id="t")
        assert trades[0].exit_reason == "target"
        assert trades[0].exit_price == 110.0
        assert abs(trades[0].gross_return_pct - (110.0 / 101.0 - 1)) < 1e-12

    def test_time_exit_at_close_after_max_holding(self, flat_bars):
        sig = Signal(code="A", signal_date=date(2025, 1, 2), stop_price=90.0, max_holding_days=3)
        trades = simulate_trades(flat_bars, [sig], NO_COST, strategy_id="t")
        assert trades[0].exit_reason == "time"
        # 진입 봉(01-03) 포함 3거래일 보유 → 01-07 종가 청산
        assert trades[0].exit_date == date(2025, 1, 7)

    def test_data_end_exit_at_last_close(self):
        bars = make_bars([
            ("2025-01-02", 100, 101, 99, 100),
            ("2025-01-03", 100, 101, 99, 100),
            ("2025-01-06", 100, 101, 99, 101),
        ])
        sig = Signal(code="A", signal_date=date(2025, 1, 2), stop_price=90.0, max_holding_days=40)
        trades = simulate_trades(bars, [sig], NO_COST, strategy_id="t")
        assert trades[0].exit_reason == "data_end"
        assert trades[0].exit_price == 101.0


class TestOverlap:
    def test_second_signal_during_open_position_is_skipped(self, flat_bars):
        s1 = Signal(code="A", signal_date=date(2025, 1, 2), stop_price=90.0, max_holding_days=5)
        s2 = Signal(code="A", signal_date=date(2025, 1, 3), stop_price=90.0, max_holding_days=5)
        trades = simulate_trades(flat_bars, [s1, s2], NO_COST, strategy_id="t")
        assert len(trades) == 1  # 1종목 1포지션


class TestCostsApplied:
    def test_net_return_uses_cost_model(self):
        bars = make_bars([
            ("2025-01-02", 100, 101, 99, 100),
            ("2025-01-03", 100, 112, 100, 111),
        ])
        cm = CostModel(commission_pct=0.001, tax_pct=0.002, slippage_pct=0.0)
        sig = Signal(code="A", signal_date=date(2025, 1, 2), stop_price=95.0, target_price=110.0)
        trades = simulate_trades(bars, [sig], cm, strategy_id="t")
        assert abs(trades[0].net_return_pct - cm.net_return_pct(100.0, 110.0)) < 1e-12
        assert trades[0].net_return_pct < trades[0].gross_return_pct
```

- [ ] **Step 2: 실패 확인**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/lab/test_simulate.py -q`
Expected: FAIL (`ModuleNotFoundError: app.lab.simulate`)

- [ ] **Step 3: 구현**

`backend/app/lab/simulate.py`:

```python
"""신호 → 트레이드 시뮬레이션 (롱 온리, 보수적 체결 규칙).

규칙 (스펙 §2, deep_analysis/backtest_engine의 보수 관행 계승):
- 진입: 신호 다음 봉 시가. 다음 봉이 없으면 신호 폐기.
- 청산 우선순위 (봉 단위): ① 손절 (같은 봉에서 목표와 겹치면 손절 우선,
  갭다운으로 시가가 이미 손절 아래면 시가 체결) ② 목표 (갭업이면 시가)
  ③ 시간 청산 (진입 봉 포함 max_holding_days 거래일째 종가)
  ④ 데이터 끝 (마지막 종가, exit_reason="data_end")
- 1종목 1포지션: 보유 중 발생한 신호는 버린다.
"""
from __future__ import annotations

import pandas as pd

from .costs import CostModel
from .types import Signal, Trade


def simulate_trades(
    bars: pd.DataFrame,
    signals: list[Signal],
    cost_model: CostModel,
    strategy_id: str,
) -> list[Trade]:
    if bars.empty or not signals:
        return []

    dates = pd.to_datetime(bars["date"]).dt.date.tolist()
    index_by_date = {d: i for i, d in enumerate(dates)}
    trades: list[Trade] = []
    blocked_until = -1  # 이 인덱스(포함)까지 포지션 보유 중

    for signal in sorted(signals, key=lambda s: s.signal_date):
        signal_idx = index_by_date.get(signal.signal_date)
        if signal_idx is None or signal_idx + 1 >= len(bars):
            continue
        entry_idx = signal_idx + 1
        if entry_idx <= blocked_until:
            continue  # 1종목 1포지션

        entry_price = float(bars.iloc[entry_idx]["open"])
        exit_idx, exit_price, exit_reason = _resolve_exit(bars, entry_idx, entry_price, signal)
        gross = exit_price / entry_price - 1
        trades.append(
            Trade(
                code=signal.code,
                strategy_id=strategy_id,
                entry_date=dates[entry_idx],
                entry_price=entry_price,
                exit_date=dates[exit_idx],
                exit_price=exit_price,
                exit_reason=exit_reason,
                gross_return_pct=round(gross, 6),
                net_return_pct=round(cost_model.net_return_pct(entry_price, exit_price), 6),
            )
        )
        blocked_until = exit_idx

    return trades


def _resolve_exit(
    bars: pd.DataFrame, entry_idx: int, entry_price: float, signal: Signal
) -> tuple[int, float, str]:
    last_idx = len(bars) - 1
    time_exit_idx = min(entry_idx + signal.max_holding_days - 1, last_idx)

    for idx in range(entry_idx, time_exit_idx + 1):
        bar = bars.iloc[idx]
        open_, high, low = float(bar["open"]), float(bar["high"]), float(bar["low"])
        # ① 손절 우선 (보수적) — 갭다운이면 실제 체결 가능한 시가로
        if low <= signal.stop_price:
            return idx, min(open_, signal.stop_price), "stop"
        # ② 목표 — 갭업이면 시가로 (더 유리한 체결을 가정하지 않는다)
        if signal.target_price is not None and high >= signal.target_price:
            return idx, max(open_, signal.target_price), "target"

    close = float(bars.iloc[time_exit_idx]["close"])
    # 보유 일수를 다 채우기 전에 데이터가 끝났으면 time이 아니라 data_end
    reached_full_holding = (entry_idx + signal.max_holding_days - 1) <= last_idx
    return time_exit_idx, close, ("time" if reached_full_holding else "data_end")
```

- [ ] **Step 4: 통과 확인**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/lab/test_simulate.py -q`
Expected: 9 passed

- [ ] **Step 5: Commit**

```bash
git add backend/app/lab/simulate.py backend/tests/lab/test_simulate.py
git commit -m "lab: 보수적 체결 규칙의 트레이드 시뮬레이터"
```

---

### Task 5: 지표 + 부트스트랩 + 판정 (metrics.py)

**Files:**
- Create: `backend/app/lab/metrics.py`
- Test: `backend/tests/lab/test_metrics.py`

- [ ] **Step 1: 실패하는 테스트 작성**

`backend/tests/lab/test_metrics.py`:

```python
from datetime import date

import pytest

from app.lab.metrics import Summary, bootstrap_ci, decide_verdict, summarize
from app.lab.types import Trade


def _trade(net: float, exit_day: int = 1) -> Trade:
    return Trade(
        code="A", strategy_id="t",
        entry_date=date(2025, 1, 1), entry_price=100.0,
        exit_date=date(2025, 1, 1 + exit_day), exit_price=100.0 * (1 + net),
        exit_reason="time", gross_return_pct=net, net_return_pct=net,
    )


class TestSummarize:
    def test_empty_trades(self):
        s = summarize([])
        assert s.n == 0 and s.ev_pct == 0.0

    def test_ev_win_rate_payoff(self):
        trades = [_trade(0.10), _trade(0.10), _trade(-0.05), _trade(-0.05)]
        s = summarize(trades)
        assert s.n == 4
        assert abs(s.ev_pct - 0.025) < 1e-12
        assert abs(s.win_rate - 0.5) < 1e-12
        assert abs(s.payoff_ratio - 2.0) < 1e-12  # 평균이익 0.10 / 평균손실 0.05

    def test_mdd_from_sequential_equity(self):
        # +10% → -20% → +5%: 고점 1.10에서 0.88까지 → MDD = 20%
        trades = [_trade(0.10, 1), _trade(-0.20, 2), _trade(0.05, 3)]
        s = summarize(trades)
        assert abs(s.mdd_pct - 0.20) < 1e-9


class TestBootstrap:
    def test_deterministic_with_seed(self):
        values = [0.01, -0.02, 0.03, 0.01, -0.01] * 10
        assert bootstrap_ci(values, seed=42) == bootstrap_ci(values, seed=42)

    def test_ci_contains_mean_for_reasonable_sample(self):
        values = [0.01] * 50 + [-0.005] * 50
        lo, hi = bootstrap_ci(values, seed=1)
        mean = sum(values) / len(values)
        assert lo <= mean <= hi

    def test_tight_positive_sample_excludes_zero(self):
        lo, _ = bootstrap_ci([0.01] * 100, seed=1)
        assert lo > 0


class TestVerdict:
    def test_fail_when_ev_not_positive(self):
        assert decide_verdict(ev_pct=-0.001, ci_low=-0.01, random_ev_pct=0.0) == "fail"
        assert decide_verdict(ev_pct=0.0, ci_low=-0.01, random_ev_pct=0.0) == "fail"

    def test_pass_needs_ci_above_zero_and_beats_random(self):
        assert decide_verdict(ev_pct=0.01, ci_low=0.002, random_ev_pct=0.001) == "pass"

    def test_watch_when_ci_includes_zero(self):
        assert decide_verdict(ev_pct=0.01, ci_low=-0.001, random_ev_pct=0.0) == "watch"

    def test_watch_when_random_not_beaten(self):
        assert decide_verdict(ev_pct=0.01, ci_low=0.002, random_ev_pct=0.02) == "watch"

    def test_random_none_means_only_ci_gate(self):
        assert decide_verdict(ev_pct=0.01, ci_low=0.002, random_ev_pct=None) == "pass"
```

- [ ] **Step 2: 실패 확인**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/lab/test_metrics.py -q`
Expected: FAIL (`ModuleNotFoundError`)

- [ ] **Step 3: 구현**

`backend/app/lab/metrics.py`:

```python
"""검증 지표와 판정 — 스펙 §2 metrics.py.

판정 3등급:
- pass: EV > 0, 부트스트랩 95% CI 하한 > 0, 랜덤 벤치마크 EV 초과
- watch: EV > 0이지만 CI에 0 포함 또는 랜덤 벤치마크 못 넘음
- fail: EV <= 0
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .types import Trade


@dataclass(frozen=True)
class Summary:
    n: int
    ev_pct: float          # 거래당 순기대값 (비용 차감)
    win_rate: float
    payoff_ratio: float    # 평균이익 / 평균손실 (손실 없으면 inf 대신 0으로)
    mdd_pct: float         # 청산일 순서 단일 포지션 복리 곡선 기준
    avg_holding_days: float


def summarize(trades: list[Trade]) -> Summary:
    if not trades:
        return Summary(n=0, ev_pct=0.0, win_rate=0.0, payoff_ratio=0.0, mdd_pct=0.0, avg_holding_days=0.0)

    returns = [t.net_return_pct for t in trades]
    wins = [r for r in returns if r > 0]
    losses = [-r for r in returns if r < 0]
    payoff = (float(np.mean(wins)) / float(np.mean(losses))) if wins and losses else 0.0

    ordered = sorted(trades, key=lambda t: t.exit_date)
    equity = np.cumprod([1 + t.net_return_pct for t in ordered])
    peak = np.maximum.accumulate(equity)
    mdd = float(np.max(1 - equity / peak)) if len(equity) else 0.0

    holding = [max(1, (t.exit_date - t.entry_date).days) for t in trades]
    return Summary(
        n=len(trades),
        ev_pct=float(np.mean(returns)),
        win_rate=len(wins) / len(trades),
        payoff_ratio=payoff,
        mdd_pct=mdd,
        avg_holding_days=float(np.mean(holding)),
    )


def bootstrap_ci(
    values: list[float], n_boot: int = 2000, alpha: float = 0.05, seed: int = 42
) -> tuple[float, float]:
    """트레이드 수익률 리샘플링으로 평균의 (1-alpha) 신뢰구간."""
    if not values:
        return (0.0, 0.0)
    rng = np.random.default_rng(seed)
    arr = np.asarray(values, dtype=float)
    means = rng.choice(arr, size=(n_boot, len(arr)), replace=True).mean(axis=1)
    lo, hi = np.quantile(means, [alpha / 2, 1 - alpha / 2])
    return (float(lo), float(hi))


def decide_verdict(ev_pct: float, ci_low: float, random_ev_pct: float | None) -> str:
    if ev_pct <= 0:
        return "fail"
    if ci_low > 0 and (random_ev_pct is None or ev_pct > random_ev_pct):
        return "pass"
    return "watch"
```

- [ ] **Step 4: 통과 확인**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/lab/test_metrics.py -q`
Expected: 11 passed

- [ ] **Step 5: Commit**

```bash
git add backend/app/lab/metrics.py backend/tests/lab/test_metrics.py
git commit -m "lab: 지표 요약 + 부트스트랩 CI + 3등급 판정"
```

---

### Task 6: 워크포워드 하네스 (walkforward.py)

**Files:**
- Create: `backend/app/lab/walkforward.py`
- Test: `backend/tests/lab/test_walkforward.py`

- [ ] **Step 1: 실패하는 테스트 작성**

`backend/tests/lab/test_walkforward.py`:

```python
from datetime import date

import pandas as pd

from app.lab.costs import CostModel
from app.lab.types import Signal
from app.lab.walkforward import Window, run_walk_forward, walk_forward_windows

from .conftest import make_bars

NO_COST = CostModel(commission_pct=0.0, tax_pct=0.0, slippage_pct=0.0)


class TestWindows:
    def test_rolling_windows(self):
        windows = walk_forward_windows(
            start=date(2020, 1, 1), end=date(2022, 12, 31),
            train_years=1, test_months=6, step_months=6,
        )
        assert windows[0] == Window(
            train_start=date(2020, 1, 1), train_end=date(2020, 12, 31),
            test_start=date(2021, 1, 1), test_end=date(2021, 6, 30),
        )
        assert windows[1].test_start == date(2021, 7, 1)
        # 검증 구간이 end를 넘는 윈도우는 만들지 않는다
        assert all(w.test_end <= date(2022, 12, 31) for w in windows)

    def test_no_window_when_period_too_short(self):
        assert walk_forward_windows(
            start=date(2022, 1, 1), end=date(2022, 6, 30),
            train_years=1, test_months=6, step_months=6,
        ) == []


class _FixedStrategy:
    """fit은 학습 구간 마지막 종가를 기억하고, signals는 매월 첫 봉에 신호를 낸다."""
    id = "fixed"
    label = "테스트 고정 전략"

    def __init__(self):
        self.seen_train_end: list[pd.Timestamp] = []

    def fit(self, train_bars: dict[str, pd.DataFrame]) -> dict:
        last = max(df["date"].max() for df in train_bars.values())
        self.seen_train_end.append(last)
        return {"stop_pct": 0.05}

    def signals(self, code: str, bars: pd.DataFrame, params: dict) -> list[Signal]:
        out = []
        months = set()
        for _, row in bars.iterrows():
            d = row["date"].date()
            key = (d.year, d.month)
            if key not in months:
                months.add(key)
                out.append(Signal(code=code, signal_date=d,
                                  stop_price=float(row["close"]) * (1 - params["stop_pct"]),
                                  max_holding_days=5))
        return out


def _monotone_bars(start: str, periods: int) -> pd.DataFrame:
    dates = pd.bdate_range(start=start, periods=periods)
    rows = [(str(d.date()), 100 + i, 101 + i, 99 + i, 100.5 + i) for i, d in enumerate(dates)]
    return make_bars(rows)


class TestHarness:
    def test_trades_only_in_test_ranges_and_fit_sees_only_train(self):
        bars = {"A": _monotone_bars("2020-01-01", 700)}
        strategy = _FixedStrategy()
        result = run_walk_forward(
            strategy=strategy,
            bars_by_code=bars,
            universe_fn=lambda window: ["A"],
            cost_model=NO_COST,
            windows=walk_forward_windows(
                start=date(2020, 1, 1), end=date(2022, 6, 30),
                train_years=1, test_months=6, step_months=6,
            ),
        )
        assert result.strategy_id == "fixed"
        assert result.summary.n > 0
        windows = walk_forward_windows(
            start=date(2020, 1, 1), end=date(2022, 6, 30),
            train_years=1, test_months=6, step_months=6,
        )
        # 진입일은 반드시 어떤 검증 구간 안에 있다
        for t in result.trades:
            assert any(w.test_start <= t.entry_date <= w.test_end for w in windows)
        # 미래 데이터 누출 방지: fit이 본 마지막 날짜는 각 학습 구간 종료일 이하
        for seen, w in zip(strategy.seen_train_end, windows):
            assert seen.date() <= w.train_end

    def test_verdict_present(self):
        bars = {"A": _monotone_bars("2020-01-01", 700)}
        result = run_walk_forward(
            strategy=_FixedStrategy(), bars_by_code=bars,
            universe_fn=lambda window: ["A"], cost_model=NO_COST,
            windows=walk_forward_windows(
                start=date(2020, 1, 1), end=date(2022, 6, 30),
                train_years=1, test_months=6, step_months=6,
            ),
        )
        assert result.verdict in {"pass", "watch", "fail"}
```

- [ ] **Step 2: 실패 확인**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/lab/test_walkforward.py -q`
Expected: FAIL (`ModuleNotFoundError`)

- [ ] **Step 3: 구현**

`backend/app/lab/walkforward.py`:

```python
"""워크포워드 하네스 — 파라미터는 학습 구간에서만, 검증 구간은 한 번만.

인샘플(학습 구간) 성적은 계산하지 않는다. 검증 구간 트레이드만 모아
summarize/bootstrap/verdict로 판정한다 (스펙 §2).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Callable, Mapping, Protocol

import pandas as pd

from .costs import CostModel
from .metrics import Summary, bootstrap_ci, decide_verdict, summarize
from .simulate import simulate_trades
from .types import Signal, Trade


class Strategy(Protocol):
    id: str
    label: str

    def fit(self, train_bars: dict[str, pd.DataFrame]) -> dict: ...
    def signals(self, code: str, bars: pd.DataFrame, params: dict) -> list[Signal]: ...


@dataclass(frozen=True)
class Window:
    train_start: date
    train_end: date
    test_start: date
    test_end: date


@dataclass
class LabRunResult:
    strategy_id: str
    strategy_label: str
    trades: list[Trade]
    summary: Summary
    ci: tuple[float, float]
    random_ev_pct: float | None
    verdict: str
    windows: list[Window] = field(default_factory=list)
    data_coverage: float = 1.0  # 유니버스 중 시세 확보 종목 비율 (CLI에서 채움)


def walk_forward_windows(
    start: date, end: date, train_years: int = 2, test_months: int = 6, step_months: int = 6
) -> list[Window]:
    windows: list[Window] = []
    cursor = pd.Timestamp(start)
    while True:
        train_end = cursor + pd.DateOffset(years=train_years) - pd.Timedelta(days=1)
        test_start = train_end + pd.Timedelta(days=1)
        test_end = test_start + pd.DateOffset(months=test_months) - pd.Timedelta(days=1)
        if test_end.date() > end:
            break
        windows.append(
            Window(
                train_start=cursor.date(), train_end=train_end.date(),
                test_start=test_start.date(), test_end=test_end.date(),
            )
        )
        cursor = cursor + pd.DateOffset(months=step_months)
    return windows


def run_walk_forward(
    strategy: Strategy,
    bars_by_code: Mapping[str, pd.DataFrame],
    universe_fn: Callable[[Window], list[str]],
    cost_model: CostModel,
    windows: list[Window],
    random_ev_pct: float | None = None,
) -> LabRunResult:
    all_trades: list[Trade] = []

    for window in windows:
        codes = [c for c in universe_fn(window) if c in bars_by_code]
        train = {
            code: _slice(bars_by_code[code], end=window.train_end)
            for code in codes
        }
        train = {c: df for c, df in train.items() if not df.empty}
        if not train:
            continue
        params = strategy.fit(train)

        for code in codes:
            # 지표 워밍업을 위해 학습 구간 포함, 검증 종료일까지만 노출 (그 뒤는 하네스가 차단)
            visible = _slice(bars_by_code[code], end=window.test_end)
            if visible.empty:
                continue
            signals = [
                s for s in strategy.signals(code, visible, params)
                if window.test_start <= s.signal_date <= window.test_end
            ]
            all_trades.extend(simulate_trades(visible, signals, cost_model, strategy.id))

    summary = summarize(all_trades)
    ci = bootstrap_ci([t.net_return_pct for t in all_trades])
    verdict = decide_verdict(summary.ev_pct, ci[0], random_ev_pct) if summary.n else "fail"
    return LabRunResult(
        strategy_id=strategy.id,
        strategy_label=strategy.label,
        trades=all_trades,
        summary=summary,
        ci=ci,
        random_ev_pct=random_ev_pct,
        verdict=verdict,
        windows=windows,
    )


def _slice(bars: pd.DataFrame, end: date) -> pd.DataFrame:
    mask = pd.to_datetime(bars["date"]).dt.date <= end
    return bars.loc[mask].reset_index(drop=True)
```

- [ ] **Step 4: 통과 확인**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/lab/test_walkforward.py -q`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add backend/app/lab/walkforward.py backend/tests/lab/test_walkforward.py
git commit -m "lab: 워크포워드 하네스 (학습/검증 분리, 누출 방지 테스트 포함)"
```

---

### Task 7: 시점 고정 유니버스 (universe.py)

**Files:**
- Create: `backend/app/lab/universe.py`
- Test: `backend/tests/lab/test_universe.py`

- [ ] **Step 1: 실패하는 테스트 작성**

`backend/tests/lab/test_universe.py`:

```python
import pandas as pd

from app.lab.universe import select_top_by_market_cap


class TestSelectTop:
    def test_orders_by_cap_and_limits(self):
        caps = pd.Series({"A": 300.0, "B": 100.0, "C": 200.0})
        assert select_top_by_market_cap(caps, top_n=2) == ["A", "C"]

    def test_drops_nan_and_nonpositive(self):
        caps = pd.Series({"A": 100.0, "B": float("nan"), "C": 0.0, "D": -5.0})
        assert select_top_by_market_cap(caps, top_n=10) == ["A"]

    def test_empty(self):
        assert select_top_by_market_cap(pd.Series(dtype=float), top_n=5) == []
```

- [ ] **Step 2: 실패 확인**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/lab/test_universe.py -q`
Expected: FAIL

- [ ] **Step 3: 구현**

`backend/app/lab/universe.py`:

```python
"""시점 고정(point-in-time) 유니버스 — 생존 편향 제거의 핵심 (스펙 §2).

현재 시총 상위를 과거로 돌려보면 "지금까지 살아남아 커진 종목"만 보게 된다.
리밸런스 시점마다 그 날짜 기준의 시총 상위를 pykrx로 다시 뽑는다.
순수 선택 로직과 pykrx IO를 분리해 선택 로직만 단위 테스트한다.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import date, timedelta

import pandas as pd

logger = logging.getLogger(__name__)


def select_top_by_market_cap(cap_by_code: pd.Series, top_n: int) -> list[str]:
    """시가총액 Series(index=종목코드)에서 유효값만 정렬해 상위 top_n 코드 반환."""
    if cap_by_code.empty:
        return []
    valid = cap_by_code.dropna()
    valid = valid[valid > 0]
    return valid.sort_values(ascending=False).head(top_n).index.tolist()


async def fetch_point_in_time_universe(asof: date, top_n: int, max_back_days: int = 10) -> list[str]:
    """asof 시점의 KOSPI+KOSDAQ 시총 상위 top_n. 휴장일이면 며칠 거슬러 재시도.

    pykrx 실패 시 빈 목록 반환 — 호출부(CLI)가 커버리지에 기록하고 해당
    윈도우를 건너뛴다 (조용히 현재 유니버스로 대체하지 않는다).
    """
    from pykrx import stock as krx

    for back in range(max_back_days + 1):
        day = asof - timedelta(days=back)
        stamp = day.strftime("%Y%m%d")
        try:
            frames = await asyncio.gather(
                asyncio.to_thread(krx.get_market_cap_by_ticker, stamp, "KOSPI"),
                asyncio.to_thread(krx.get_market_cap_by_ticker, stamp, "KOSDAQ"),
            )
            merged = pd.concat(frames)
            if merged.empty or "시가총액" not in merged.columns:
                continue
            return select_top_by_market_cap(merged["시가총액"].astype(float), top_n)
        except Exception as exc:
            logger.warning("point-in-time universe fetch failed for %s: %s", stamp, exc)
    return []
```

- [ ] **Step 4: 통과 확인**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/lab/test_universe.py -q`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add backend/app/lab/universe.py backend/tests/lab/test_universe.py
git commit -m "lab: 시점 고정 유니버스 (순수 선택 + pykrx IO 분리)"
```

---

### Task 8: 랜덤 진입 벤치마크 (baselines.py)

**Files:**
- Create: `backend/app/lab/baselines.py`
- Test: `backend/tests/lab/test_baselines.py`

- [ ] **Step 1: 실패하는 테스트 작성**

`backend/tests/lab/test_baselines.py`:

```python
from datetime import date

from app.lab.baselines import random_benchmark_signals
from app.lab.types import Signal

from .conftest import make_bars


def _bars():
    return make_bars(
        [(f"2025-01-{i:02d}", 100.0, 101.0, 99.0, 100.0) for i in range(2, 30) if i % 7 not in (4, 5)]
    )


def _subject_signals():
    return [
        Signal(code="A", signal_date=date(2025, 1, 2), stop_price=95.0, target_price=110.0, max_holding_days=10),
        Signal(code="A", signal_date=date(2025, 1, 9), stop_price=96.0, target_price=108.0, max_holding_days=10),
    ]


class TestRandomBenchmark:
    def test_deterministic_with_seed(self):
        a = random_benchmark_signals({"A": _bars()}, _subject_signals(), n_signals=5, seed=7)
        b = random_benchmark_signals({"A": _bars()}, _subject_signals(), n_signals=5, seed=7)
        assert a == b

    def test_copies_subject_exit_geometry(self):
        # 손절/목표 % 거리와 보유일은 피검체 신호의 중앙값을 따른다 (동일 청산 근사)
        signals = random_benchmark_signals({"A": _bars()}, _subject_signals(), n_signals=3, seed=1)
        assert len(signals) == 3
        for s in signals:
            close = 100.0  # 합성 시세 종가
            assert 0.01 <= (close - s.stop_price) / close <= 0.10
            assert s.target_price is not None and s.target_price > close
            assert s.max_holding_days == 10

    def test_empty_subject_means_no_benchmark(self):
        assert random_benchmark_signals({"A": _bars()}, [], n_signals=5, seed=1) == []
```

- [ ] **Step 2: 실패 확인**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/lab/test_baselines.py -q`
Expected: FAIL

- [ ] **Step 3: 구현**

`backend/app/lab/baselines.py`:

```python
"""랜덤 진입 벤치마크 — 귀무가설 (스펙 §2 피검체 표의 random_entry).

피검체 전략과 "동일 청산" 조건을 근사하기 위해, 피검체 신호들의 손절/목표
% 거리와 보유일의 중앙값을 그대로 쓰고 진입 시점만 무작위로 뽑는다.
이 벤치마크를 못 넘는 전략은 진입 타이밍에 엣지가 없는 것이다.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .types import Signal


def random_benchmark_signals(
    bars_by_code: dict[str, pd.DataFrame],
    subject_signals: list[Signal],
    n_signals: int,
    seed: int = 42,
) -> list[Signal]:
    if not subject_signals or not bars_by_code:
        return []

    stop_dists: list[float] = []
    target_dists: list[float] = []
    holdings: list[int] = []
    by_code_date = {
        code: {pd.Timestamp(r["date"]).date(): float(r["close"]) for _, r in df.iterrows()}
        for code, df in bars_by_code.items()
    }
    for s in subject_signals:
        close = by_code_date.get(s.code, {}).get(s.signal_date)
        if not close:
            continue
        stop_dists.append((close - s.stop_price) / close)
        if s.target_price is not None:
            target_dists.append((s.target_price - close) / close)
        holdings.append(s.max_holding_days)
    if not stop_dists:
        return []

    stop_pct = float(np.median(stop_dists))
    target_pct = float(np.median(target_dists)) if target_dists else None
    holding = int(np.median(holdings))

    rng = np.random.default_rng(seed)
    codes = sorted(bars_by_code.keys())
    out: list[Signal] = []
    for _ in range(n_signals):
        code = codes[int(rng.integers(0, len(codes)))]
        df = bars_by_code[code]
        if len(df) < 2:
            continue
        idx = int(rng.integers(0, len(df) - 1))  # 마지막 봉 제외 (다음 봉 진입 필요)
        row = df.iloc[idx]
        close = float(row["close"])
        out.append(
            Signal(
                code=code,
                signal_date=pd.Timestamp(row["date"]).date(),
                stop_price=close * (1 - stop_pct),
                target_price=(close * (1 + target_pct)) if target_pct is not None else None,
                max_holding_days=holding,
            )
        )
    return out
```

- [ ] **Step 4: 통과 확인**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/lab/test_baselines.py -q`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add backend/app/lab/baselines.py backend/tests/lab/test_baselines.py
git commit -m "lab: 랜덤 진입 벤치마크 (피검체 동일 청산 근사)"
```

---

### Task 9: 레거시 패턴 어댑터 (strategies/legacy_patterns.py)

**Files:**
- Create: `backend/app/strategies/legacy_patterns.py`
- Test: `backend/tests/lab/test_legacy_adapter.py`
- 참고: `backend/app/services/pattern_engine.py` (PatternEngine.detect_all, pattern_direction_is_bullish), `backend/app/services/deep_analysis_service.py`의 슬라이딩 윈도우/퇴화 케이스 가드 관행

- [ ] **Step 1: 실패하는 테스트 작성**

`backend/tests/lab/test_legacy_adapter.py`:

```python
from datetime import date

import pandas as pd

from app.strategies.legacy_patterns import LegacyPatternStrategy


def _trending_bars(periods: int = 300) -> pd.DataFrame:
    """패턴이 나올 수 있는 변동 있는 합성 시세 (결정적)."""
    import numpy as np

    rng = np.random.default_rng(3)
    dates = pd.bdate_range("2023-01-02", periods=periods)
    close = 10_000 * np.cumprod(1 + rng.normal(0.0005, 0.015, periods))
    rows = []
    for i, d in enumerate(dates):
        c = float(close[i])
        rows.append({
            "date": d, "open": c * 0.995, "high": c * 1.01, "low": c * 0.985,
            "close": c, "volume": 1_000_000,
        })
    return pd.DataFrame(rows)


class TestLegacyAdapter:
    def test_interface(self):
        s = LegacyPatternStrategy()
        assert s.id == "legacy_patterns"
        assert s.fit({"A": _trending_bars(150)}) == {}  # 파라미터 학습 없음 (고정 규칙)

    def test_signals_are_long_only_with_valid_geometry(self):
        s = LegacyPatternStrategy()
        signals = s.signals("A", _trending_bars(), params={})
        closes = {pd.Timestamp(r["date"]).date(): float(r["close"]) for _, r in _trending_bars().iterrows()}
        for sig in signals:
            close = closes[sig.signal_date]
            assert sig.stop_price < close  # 롱: 손절은 아래
            if sig.target_price is not None:
                assert sig.target_price > close  # 목표는 위 (퇴화 케이스 없음)

    def test_no_lookahead_truncation_consistency(self):
        # 시계열을 앞부분만 잘라 넣어도, 그 구간의 신호는 전체 넣었을 때와 같아야 한다
        s = LegacyPatternStrategy()
        full = _trending_bars(300)
        cut = full.iloc[:200].reset_index(drop=True)
        cutoff = pd.Timestamp(cut["date"].max()).date()
        sig_cut = {(x.signal_date, round(x.stop_price, 2)) for x in s.signals("A", cut, {})}
        sig_full = {
            (x.signal_date, round(x.stop_price, 2))
            for x in s.signals("A", full, {})
            if x.signal_date <= cutoff
        }
        assert sig_cut == sig_full
```

- [ ] **Step 2: 실패 확인**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/lab/test_legacy_adapter.py -q`
Expected: FAIL

- [ ] **Step 3: 구현**

`backend/app/strategies/legacy_patterns.py`:

```python
"""기존 패턴 엔진을 랩의 첫 피검체로 감싸는 어댑터 (스펙 §2 legacy_patterns).

기존 앱이 추천하던 방식과 같은 조건을 재현한다:
- confirmed 상태의 강세(롱) 패턴만
- 손절 = invalidation_level, 목표 = target_level, 시간 청산 40거래일
- 신호일 종가가 (손절, 목표) 사이에 없으면 퇴화 케이스로 폐기
  (deep_analysis_service의 가드와 동일)

슬라이딩 윈도우 탐지는 각 윈도우의 마지막 봉 정보까지만 쓰므로 미래 참조가
없다 — test_no_lookahead_truncation_consistency가 이를 회귀 테스트한다.
"""
from __future__ import annotations

import pandas as pd

from ..lab.types import Signal
from ..services.pattern_engine import PatternEngine, pattern_direction_is_bullish

_WINDOW = 120
_STEP = 5
_MAX_HOLDING = 40


class LegacyPatternStrategy:
    id = "legacy_patterns"
    label = "기존 패턴 엔진 (confirmed 롱)"

    def fit(self, train_bars: dict[str, pd.DataFrame]) -> dict:
        return {}  # 고정 규칙 — 학습 파라미터 없음

    def signals(self, code: str, bars: pd.DataFrame, params: dict) -> list[Signal]:
        engine = PatternEngine()
        out: list[Signal] = []
        seen: set[tuple[str, object]] = set()
        n = len(bars)

        for start in range(0, max(0, n - _WINDOW) + 1, _STEP):
            window = bars.iloc[start:start + _WINDOW]
            if len(window) < _WINDOW:
                break
            window = window.copy().reset_index(drop=True)
            try:
                patterns = engine.detect_all(window, timeframe="1d")
            except Exception:
                continue
            signal_date = pd.Timestamp(window.iloc[-1]["date"]).date()
            close = float(window.iloc[-1]["close"])

            for pattern in patterns:
                if pattern.state != "confirmed":
                    continue
                if pattern.target_level is None or pattern.invalidation_level is None:
                    continue
                if not pattern_direction_is_bullish(pattern):
                    continue  # 롱 온리 (숏은 개인 실행 불가 — 스펙)
                if not (pattern.invalidation_level < close < pattern.target_level):
                    continue  # 퇴화 케이스 가드
                key = (pattern.pattern_type, signal_date)
                if key in seen:
                    continue
                seen.add(key)
                out.append(
                    Signal(
                        code=code,
                        signal_date=signal_date,
                        stop_price=float(pattern.invalidation_level),
                        target_price=float(pattern.target_level),
                        max_holding_days=_MAX_HOLDING,
                    )
                )
        return out
```

- [ ] **Step 4: 통과 확인**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/lab/test_legacy_adapter.py -q`
Expected: 3 passed. `test_no_lookahead_truncation_consistency`가 실패하면 윈도우 오프셋 정렬 문제다 — 슬라이딩 시작점을 "끝에서부터" 정렬하도록 바꾼다:

```python
        # 시계열 길이가 달라도 같은 날짜의 윈도우가 같은 위치에서 잘리도록 끝 기준 정렬
        offsets = range((n - _WINDOW) % _STEP, max(0, n - _WINDOW) + 1, _STEP)
        for start in offsets:
```

주의: 위 교체를 적용하면 윈도우 시작점이 데이터 길이에 따라 달라져 오히려 신호가 어긋날 수 있다. 그 경우 어댑터를 "매 봉 평가"(_STEP=1)로 바꾸는 것이 정공법이다 (느리지만 결정적). 성능이 문제면 탐지 결과를 (패턴 종류, end_dt) 기준으로 dedupe한다.

- [ ] **Step 5: Commit**

```bash
git add backend/app/strategies/legacy_patterns.py backend/tests/lab/test_legacy_adapter.py
git commit -m "strategies: 기존 패턴 엔진 어댑터 — 랩 첫 피검체"
```

---

### Task 10: CLI 러너 (scripts/run_lab.py)

**Files:**
- Create: `backend/scripts/run_lab.py`
- 참고: `backend/app/services/data_fetcher.py`의 `get_data_fetcher().get_stock_ohlcv_by_timeframe(code, "1d", lookback_days=...)`

- [ ] **Step 1: 러너 작성**

`backend/scripts/run_lab.py`:

```python
"""랩 CLI — 전략을 워크포워드로 검증하고 JSON 리포트를 저장한다.

사용 (backend/에서):
  .venv/Scripts/python.exe scripts/run_lab.py --strategy legacy_patterns \
      --start 2019-01-01 --end 2026-07-01 --top-n 100

네트워크 필요 (pykrx/FDR). 결과: backend/data/lab/<strategy>_<ts>.json
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import asdict
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.lab.baselines import random_benchmark_signals  # noqa: E402
from app.lab.costs import CostModel  # noqa: E402
from app.lab.metrics import bootstrap_ci, summarize  # noqa: E402
from app.lab.simulate import simulate_trades  # noqa: E402
from app.lab.universe import fetch_point_in_time_universe  # noqa: E402
from app.lab.walkforward import run_walk_forward, walk_forward_windows  # noqa: E402

STRATEGIES = {}


def _register_strategies() -> None:
    from app.strategies.legacy_patterns import LegacyPatternStrategy

    STRATEGIES["legacy_patterns"] = LegacyPatternStrategy


async def _load_bars(codes: list[str], lookback_days: int) -> dict:
    from app.services.data_fetcher import get_data_fetcher

    fetcher = get_data_fetcher()
    bars = {}
    for i, code in enumerate(codes, 1):
        try:
            df = await fetcher.get_stock_ohlcv_by_timeframe(code, "1d", lookback_days=lookback_days)
            if df is not None and len(df) >= 150:
                bars[code] = df.reset_index(drop=True)
        except Exception as exc:
            print(f"  [{i}/{len(codes)}] {code} 시세 실패: {exc}")
        if i % 20 == 0:
            print(f"  시세 로딩 {i}/{len(codes)}...")
    return bars


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strategy", required=True, choices=["legacy_patterns"])
    parser.add_argument("--start", type=date.fromisoformat, default=date(2019, 1, 1))
    parser.add_argument("--end", type=date.fromisoformat, default=date.today())
    parser.add_argument("--top-n", type=int, default=100)
    parser.add_argument("--train-years", type=int, default=2)
    parser.add_argument("--test-months", type=int, default=6)
    args = parser.parse_args()

    _register_strategies()
    strategy = STRATEGIES[args.strategy]()
    windows = walk_forward_windows(args.start, args.end, args.train_years, args.test_months, args.test_months)
    if not windows:
        print("검증 윈도우를 만들 수 없습니다 (기간이 너무 짧음).")
        return

    # 시점 고정 유니버스: 각 검증 시작일 기준. 실패한 윈도우는 커버리지에 기록.
    universes: dict = {}
    for w in windows:
        codes = await fetch_point_in_time_universe(w.test_start, args.top_n)
        universes[w] = codes
        print(f"유니버스 {w.test_start}: {len(codes)}종목")

    all_codes = sorted({c for codes in universes.values() for c in codes})
    lookback = (args.end - args.start).days + 800  # 학습 워밍업 여유
    print(f"시세 로딩: {len(all_codes)}종목, lookback {lookback}일")
    bars = await _load_bars(all_codes, lookback)
    coverage = len(bars) / max(1, len(all_codes))
    print(f"데이터 커버리지: {coverage:.0%} ({len(bars)}/{len(all_codes)})")

    cost_model = CostModel()
    result = run_walk_forward(
        strategy=strategy, bars_by_code=bars,
        universe_fn=lambda w: universes.get(w, []),
        cost_model=cost_model, windows=windows,
    )

    # 랜덤 벤치마크: 피검체와 같은 신호 수, 동일 청산 근사
    subject_signals = []
    for w in windows:
        for code in universes.get(w, []):
            if code in bars:
                subject_signals.extend(
                    s for s in strategy.signals(code, bars[code], {})
                    if w.test_start <= s.signal_date <= w.test_end
                )
    random_evs = []
    for seed in range(5):  # 5회 평균으로 랜덤 노이즈 완화
        rnd_signals = random_benchmark_signals(bars, subject_signals, n_signals=len(subject_signals), seed=seed)
        by_code: dict = {}
        for s in rnd_signals:
            by_code.setdefault(s.code, []).append(s)
        rnd_trades = []
        for code, sigs in by_code.items():
            rnd_trades.extend(simulate_trades(bars[code], sigs, cost_model, "random"))
        if rnd_trades:
            random_evs.append(summarize(rnd_trades).ev_pct)
    random_ev = sum(random_evs) / len(random_evs) if random_evs else None

    # 랜덤 벤치마크 반영해 판정 재계산
    from app.lab.metrics import decide_verdict
    verdict = decide_verdict(result.summary.ev_pct, result.ci[0], random_ev) if result.summary.n else "fail"

    report = {
        "strategy": strategy.id,
        "label": strategy.label,
        "period": {"start": args.start.isoformat(), "end": args.end.isoformat()},
        "config": {"top_n": args.top_n, "train_years": args.train_years,
                   "test_months": args.test_months, "round_trip_cost_pct": cost_model.round_trip_pct},
        "data_coverage": round(coverage, 3),
        "n_trades": result.summary.n,
        "ev_pct": round(result.summary.ev_pct, 5),
        "ci_95": [round(result.ci[0], 5), round(result.ci[1], 5)],
        "win_rate": round(result.summary.win_rate, 3),
        "payoff_ratio": round(result.summary.payoff_ratio, 2),
        "mdd_pct": round(result.summary.mdd_pct, 3),
        "random_benchmark_ev_pct": round(random_ev, 5) if random_ev is not None else None,
        "verdict": verdict,
        "generated_at": datetime.now().isoformat(),
        "trades": [
            {**asdict(t), "entry_date": t.entry_date.isoformat(), "exit_date": t.exit_date.isoformat()}
            for t in result.trades
        ],
    }
    out_dir = Path(__file__).resolve().parents[1] / "data" / "lab"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{strategy.id}_{datetime.now():%Y%m%d_%H%M%S}.json"
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n===== 검증 리포트 =====")
    print(f"전략: {strategy.label}")
    print(f"트레이드: {report['n_trades']}건, 커버리지 {coverage:.0%}")
    print(f"거래당 EV(비용 차감): {report['ev_pct']:+.3%}  (95% CI {report['ci_95'][0]:+.3%} ~ {report['ci_95'][1]:+.3%})")
    print(f"승률 {report['win_rate']:.0%}, 손익비 {report['payoff_ratio']}, MDD {report['mdd_pct']:.0%}")
    print(f"랜덤 벤치마크 EV: {report['random_benchmark_ev_pct']}")
    print(f"판정: {verdict.upper()}")
    print(f"저장: {out_path}")


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 2: 문법/import 확인 (네트워크 없이)**

Run: `cd backend && .venv/Scripts/python.exe -c "import scripts.run_lab" 2>&1 || .venv/Scripts/python.exe -c "import ast; ast.parse(open('scripts/run_lab.py', encoding='utf-8').read()); print('syntax ok')"`
Expected: `syntax ok` (data_fetcher import는 지연 로딩이므로 네트워크 불필요)

- [ ] **Step 3: 전체 lab 테스트 통과 확인**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/lab tests/ -q 2>&1 | tail -3`
Expected: 전부 통과 (기존 402+ 신규)

- [ ] **Step 4: Commit**

```bash
git add backend/scripts/run_lab.py
git commit -m "lab: CLI 러너 — 워크포워드 검증 리포트 JSON 출력"
```

---

### Task 11: 실데이터 검증 실행 (수동, 네트워크 필요)

- [ ] **Step 1: 레거시 패턴 판정 실행**

Run (backend/에서, 수 분~수십 분 소요):
```bash
.venv/Scripts/python.exe scripts/run_lab.py --strategy legacy_patterns --start 2020-01-01 --top-n 100
```
Expected: `data/lab/legacy_patterns_*.json` 생성 + 콘솔에 판정(PASS/WATCH/FAIL) 출력.
KRX 쿨다운으로 유니버스가 비면 시간을 두고 재시도한다.

- [ ] **Step 2: 결과 해석 기록**

리포트의 verdict와 EV/CI를 `docs/superpowers/specs/2026-07-12-evidence-first-trading-lab-design.md` 하단에 "Phase 1 실측 결과" 섹션으로 추가하고 커밋한다. FAIL이 나와도 그것이 Phase 1의 정상적인 산출물이다 — Phase 3에서 이 판정이 대시보드 신호 게이트의 근거가 된다.

```bash
git add docs/superpowers/specs/2026-07-12-evidence-first-trading-lab-design.md
git commit -m "lab: 레거시 패턴 전략 Phase 1 실측 판정 기록"
```
