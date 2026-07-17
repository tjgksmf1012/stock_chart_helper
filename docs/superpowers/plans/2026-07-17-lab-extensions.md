# 랩 확장 3종 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 드리프트 자동 강등(신호 게이트), marcap 가격 폴백(상폐 시세 보완 + 재검증), 횡단면 모멘텀 전략(패널 하네스 + 검증)을 PR 3개로 구현한다.

**Architecture:** 전부 기존 랩 스택 위의 확장. ①은 순수 함수 2개(services) + 라우트 배선 + LiveSignals 경고 박스, ②는 새 모듈 `lab/marcap_bars.py`(분할 보정 포함) + run_lab 폴백 병합, ③은 walkforward causal 경로에 `panel_signals` 훅 + 새 전략. 모든 로직은 순수 함수로 분리해 pytest TDD.

**Tech Stack:** Python(FastAPI/pandas/pytest), React+TS (①의 경고 박스만)

**공통 명령** (backend/에서): 테스트 `./.venv/Scripts/python.exe -m pytest tests/lab/ -q`, 전체 `-m pytest -q`. 프론트 (frontend/에서): `npx tsc --noEmit`.

**참조 코드:** 신호 게이트 `app/api/routes/lab.py:131-193` (_compute_live_signals), 드리프트 `app/services/lab_paper_trading.py:72-107`, causal 하네스 `app/lab/walkforward.py:141-183`, 시세 로딩 `scripts/run_lab.py:40-54`, bar 컬럼 규약 = date/open/high/low/close/volume (소문자).

---

## PR A — 드리프트 자동 강등 (브랜치 feat/lab-drift-demotion, 스펙 커밋 완료)

### Task A1: `effective_verdict` 순수 함수

**Files:** Modify `backend/app/services/lab_paper_trading.py` / Test `backend/tests/lab/test_paper_trading.py`

- [ ] **Step 1: 실패하는 테스트** — test_paper_trading.py에 클래스 추가:

```python
class TestEffectiveVerdict:
    def test_drifting_with_loss_becomes_fail(self):
        assert effective_verdict("pass", "drifting", -0.005) == ("fail", "실측 손실 — 신호 제외")

    def test_drifting_with_zero_ev_becomes_fail(self):
        assert effective_verdict("pass", "drifting", 0.0)[0] == "fail"

    def test_drifting_with_positive_ev_demotes_pass_to_watch(self):
        assert effective_verdict("pass", "drifting", 0.003) == ("watch", "실측 이탈 — 관찰 강등")

    def test_drifting_watch_stays_watch_with_note(self):
        assert effective_verdict("watch", "drifting", 0.003) == ("watch", "실측 이탈 — 관찰 강등")

    def test_ok_keeps_backtest_verdict(self):
        assert effective_verdict("pass", "ok", 0.01) == ("pass", None)

    def test_insufficient_keeps_backtest_verdict(self):
        assert effective_verdict("pass", "insufficient", None) == ("pass", None)
```
(import 줄에 effective_verdict 추가)

- [ ] **Step 2: 실패 확인** — Run: `./.venv/Scripts/python.exe -m pytest tests/lab/test_paper_trading.py -q` → ImportError
- [ ] **Step 3: 구현** — lab_paper_trading.py의 drift_status 아래:

```python
def effective_verdict(
    backtest_verdict: str, drift: str, realized_ev_pct: float | None
) -> tuple[str, str | None]:
    """실측 드리프트를 반영한 신호 게이트용 판정 (백테스트 리포트 자체는 불변).

    - drifting + 실측 EV<=0 → fail: 검증은 통과했지만 실전에서 잃는 중 — 신호 제외
    - drifting + 실측 EV>0 → watch 강등: 경고 라벨과 함께만 노출
    - ok/insufficient/unknown → 백테스트 판정 유지
    """
    if drift == "drifting":
        if realized_ev_pct is not None and realized_ev_pct <= 0:
            return "fail", "실측 손실 — 신호 제외"
        return ("watch" if backtest_verdict == "pass" else backtest_verdict), "실측 이탈 — 관찰 강등"
    return backtest_verdict, None
```

- [ ] **Step 4: 통과 확인** → PASS (6개)
- [ ] **Step 5: Commit** — `git commit -m "feat(lab): effective_verdict — 드리프트 반영 신호 게이트 판정"`

### Task A2: 리포트 조정 순수 함수 + 신호 게이트 배선

**Files:** Modify `backend/app/services/lab_signals.py`, `backend/app/api/routes/lab.py` / Test `backend/tests/lab/test_lab_signals.py`

- [ ] **Step 1: 실패하는 테스트** — test_lab_signals.py에:

```python
class TestApplyDriftDemotions:
    def _reports(self):
        return [
            {"strategy": "a", "label": "전략A", "verdict": "pass", "ev_pct": 0.05},
            {"strategy": "b", "label": "전략B", "verdict": "pass", "ev_pct": 0.03},
            {"strategy": "c", "label": "전략C", "verdict": "watch", "ev_pct": 0.01},
        ]

    def test_no_paper_state_changes_nothing(self):
        adjusted, demotions = apply_drift_demotions(self._reports(), {})
        assert [r["verdict"] for r in adjusted] == ["pass", "pass", "watch"]
        assert demotions == []

    def test_drifting_positive_demotes_to_watch(self):
        state = {"a": {"drift": "drifting", "realized_ev_pct": 0.004}}
        adjusted, demotions = apply_drift_demotions(self._reports(), state)
        assert adjusted[0]["verdict"] == "watch"
        assert demotions == [{
            "strategy_id": "a", "label": "전략A", "from": "pass", "to": "watch",
            "reason": "실측 이탈 — 관찰 강등",
        }]

    def test_drifting_loss_excludes_from_eligible(self):
        state = {"b": {"drift": "drifting", "realized_ev_pct": -0.002}}
        adjusted, demotions = apply_drift_demotions(self._reports(), state)
        assert demotions[0]["to"] == "fail"
        assert "b" not in eligible_strategy_ids(adjusted)

    def test_original_reports_not_mutated(self):
        reports = self._reports()
        apply_drift_demotions(reports, {"a": {"drift": "drifting", "realized_ev_pct": -1.0}})
        assert reports[0]["verdict"] == "pass"
```

- [ ] **Step 2: 실패 확인** → ImportError
- [ ] **Step 3: 구현** — lab_signals.py에 (effective_verdict를 lab_paper_trading에서 import):

```python
from .lab_paper_trading import effective_verdict


def apply_drift_demotions(
    reports: list[Mapping[str, Any]], paper_state: Mapping[str, Mapping[str, Any]]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """실측 드리프트로 판정을 조정한 리포트 사본과 강등 내역을 반환. 원본 불변."""
    adjusted: list[dict[str, Any]] = []
    demotions: list[dict[str, Any]] = []
    for report in reports:
        row = dict(report)
        state = paper_state.get(str(report.get("strategy")))
        if state:
            verdict, note = effective_verdict(
                str(report.get("verdict")), str(state.get("drift")), state.get("realized_ev_pct")
            )
            if note:
                demotions.append({
                    "strategy_id": str(report.get("strategy")),
                    "label": str(report.get("label", report.get("strategy"))),
                    "from": str(report.get("verdict")),
                    "to": verdict,
                    "reason": note,
                })
            row["verdict"] = verdict
        adjusted.append(row)
    return adjusted, demotions
```

- [ ] **Step 4: 통과 확인** — `pytest tests/lab/test_lab_signals.py -q` → PASS
- [ ] **Step 5: 라우트 배선** — routes/lab.py:
  - `_SIGNALS_CACHE_KEY`를 `"lab:live_signals:v2"`로 (응답 구조 변경).
  - 실측 상태 헬퍼 추가 (paper_trades_summary의 조회 로직 재사용 — DB 1회):

```python
async def _paper_state_by_id(reports: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """전략별 {drift, realized_ev_pct} — 신호 게이트의 자동 강등 재료."""
    ci_low_by_id = {
        r["strategy"]: (r["ci_95"][0] if isinstance(r.get("ci_95"), list) and r["ci_95"] else None)
        for r in reports if r.get("strategy")
    }
    async with AsyncSessionLocal() as session:
        rows = (await session.execute(select(LabPaperTrade))).scalars().all()
    closed = [
        {"strategy_id": t.strategy_id, "status": "closed", "net_return_pct": t.net_return_pct}
        for t in rows if t.status != "open"
    ]
    realized = realized_summary_by_strategy(closed)
    out: dict[str, dict[str, Any]] = {}
    for sid in set(realized) | set(ci_low_by_id):
        ev = realized.get(sid, {}).get("ev_pct")
        n = int(realized.get(sid, {}).get("n", 0))
        out[sid] = {"drift": drift_status(ev, n, ci_low_by_id.get(sid)), "realized_ev_pct": ev}
    return out
```
  - `_compute_live_signals()` 시작부를:

```python
    reports = load_latest_reports(_LAB_DIR)
    try:
        paper_state = await _paper_state_by_id(reports)
    except Exception as exc:  # 실측 조회 실패가 신호 게이트 전체를 죽이면 안 된다
        logger.warning("실측 상태 조회 실패 — 강등 없이 진행: %s", exc)
        paper_state = {}
    reports, demotions = apply_drift_demotions(reports, paper_state)
```
  - 이후 verdict_by_id/label_by_id/eligible은 조정된 reports 기준 그대로. 두 return dict에 `"demotions": demotions` 추가 (빈 목록 포함).
  - import 정리: `apply_drift_demotions`(lab_signals), `drift_status, realized_summary_by_strategy`(lab_paper_trading)는 이미 라우트 파일에서 쓰는 것과 합침.
- [ ] **Step 6: 전체 백엔드 테스트** — `pytest -q` → 전부 PASS
- [ ] **Step 7: Commit** — `git commit -m "feat(lab): 신호 게이트 드리프트 자동 강등 — 이탈=관찰, 실측 손실=제외"`

### Task A3: 프론트 경고 박스 + PR

**Files:** Modify `frontend/src/types/api.ts`, `frontend/src/components/lab/LiveSignals.tsx`, `frontend/src/pages/TodayPage.tsx`

- [ ] **Step 1: 타입** — api.ts의 LabSignalsResponse에:

```ts
export interface LabSignalDemotion {
  strategy_id: string
  label: string
  from: string
  to: string
  reason: string
}
// LabSignalsResponse에 추가: demotions?: LabSignalDemotion[]
```

- [ ] **Step 2: LiveSignals** — props에 `demotions?: LabSignalDemotion[]` 추가, 헤더 아래에:

```tsx
{demotions && demotions.length > 0 && (
  <div className="rounded-lg border border-amber-400/25 bg-amber-400/8 p-2.5 text-xs leading-relaxed text-amber-200/90">
    {demotions.map(d => (
      <div key={d.strategy_id}>
        <span className="font-medium">{d.label}</span> — {d.reason}
        {d.to === 'fail' ? ' (이 전략의 신호는 아래 목록에서 제외됐습니다)' : ' (신호는 관찰 등급으로 표시됩니다)'}
      </div>
    ))}
  </div>
)}
```

- [ ] **Step 3: TodayPage** — `<LiveSignals ... demotions={signalsQ.data?.demotions} />`
- [ ] **Step 4: 검증** — `npx tsc --noEmit` 클린. 브라우저 `/`에서 신호 카드 정상 렌더(강등 없으면 박스 없음).
- [ ] **Step 5: Commit + PR + 머지** — push, PR "드리프트 자동 강등", 자율 머지, main pull.

---

## PR B — marcap 가격 폴백 (브랜치 feat/lab-marcap-bars)

### Task B1: 분할 보정 `adjust_for_splits`

**Files:** Create `backend/app/lab/marcap_bars.py` / Test `backend/tests/lab/test_marcap_bars.py`

- [ ] **Step 1: 실패하는 테스트**

```python
import pandas as pd
from app.lab.marcap_bars import adjust_for_splits


def _df(closes, stocks):
    n = len(closes)
    return pd.DataFrame({
        "date": pd.date_range("2024-01-01", periods=n).date,
        "open": closes, "high": [c * 1.01 for c in closes],
        "low": [c * 0.99 for c in closes], "close": closes,
        "volume": [1000] * n, "stocks": stocks,
    })


class TestAdjustForSplits:
    def test_split_1_to_2_backadjusts_earlier_prices(self):
        # 3일째 1:2 분할 — 주식수 2배, 가격 절반. 보정 후 시계열이 연속이어야 한다.
        df = _df([10000, 10000, 5000, 5000], [100, 100, 200, 200])
        out = adjust_for_splits(df)
        assert out["close"].tolist() == [5000.0, 5000.0, 5000.0, 5000.0]
        assert out["open"].tolist()[0] == 5000.0  # 가격 4종 모두 보정

    def test_no_change_returns_same_prices(self):
        df = _df([10000, 10100], [100, 100])
        assert adjust_for_splits(df)["close"].tolist() == [10000, 10100]

    def test_small_share_change_ignored(self):
        # 자사주 소각 등 5% 미만 변동은 분할이 아니다 — 보정하지 않는다
        df = _df([10000, 10000], [100, 102])
        assert adjust_for_splits(df)["close"].tolist() == [10000, 10000]

    def test_volume_inversely_adjusted_on_split(self):
        df = _df([10000, 5000], [100, 200])
        out = adjust_for_splits(df)
        assert out["volume"].tolist() == [2000.0, 1000]
```

- [ ] **Step 2: 실패 확인** → ModuleNotFoundError
- [ ] **Step 3: 구현** — marcap_bars.py:

```python
"""marcap parquet을 상폐 종목 시세(bars) 폴백으로 쓰기 위한 로더.

marcap 가격은 무보정 원시가라 액면분할/병합일에 가짜 점프가 생긴다.
상장주식수(Stocks) 변동으로 분할을 감지해 back-adjust 한다.
한계: 배당락은 보정하지 않는다 (모멘텀에 소폭 불리한 왜곡 — 스펙에 명시).
유상증자도 주식수 점프로 잡히지만, 증자 시 권리락 가격 조정이 실제로
발생하므로 근사로는 분할과 같은 취급이 무보정보다 낫다.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

_SPLIT_THRESHOLD = 0.05  # 주식수가 하루 새 5% 넘게 변하면 분할/병합으로 판정
_PRICE_COLS = ("open", "high", "low", "close")


def adjust_for_splits(df: pd.DataFrame) -> pd.DataFrame:
    """date 오름차순 bars의 분할 back-adjust. stocks 컬럼 없으면 그대로 반환."""
    if df.empty or "stocks" not in df.columns:
        return df
    out = df.copy()
    stocks = out["stocks"].astype(float).tolist()
    factor = 1.0
    factors = [1.0] * len(out)
    # 뒤에서 앞으로: t일→t+1일 주식수 점프가 있으면 t 이하 전체에 비율 누적
    for i in range(len(out) - 2, -1, -1):
        prev_s, next_s = stocks[i], stocks[i + 1]
        if prev_s > 0 and next_s > 0 and abs(next_s / prev_s - 1) > _SPLIT_THRESHOLD:
            factor *= prev_s / next_s
        factors[i] = factor
    for col in _PRICE_COLS:
        out[col] = out[col].astype(float) * factors
    out["volume"] = out["volume"].astype(float) / factors
    return out
```

- [ ] **Step 4: 통과 확인** → PASS (4개)
- [ ] **Step 5: Commit** — `git commit -m "feat(lab): marcap 분할 보정 — 주식수 점프 기반 back-adjust"`

### Task B2: `load_marcap_bars`

**Files:** Modify `backend/app/lab/marcap_bars.py` / Test `backend/tests/lab/test_marcap_bars.py`

- [ ] **Step 1: 실패하는 테스트** (tmp_path에 parquet 픽스처):

```python
class TestLoadMarcapBars:
    def _write_parquet(self, tmp_path, year, rows):
        df = pd.DataFrame(rows)
        df.to_parquet(tmp_path / f"marcap-{year}.parquet")

    def test_loads_code_across_years_sorted(self, tmp_path):
        self._write_parquet(tmp_path, 2023, {
            "Date": ["2023-12-28"], "Code": ["005930"], "Open": [100.0], "High": [101.0],
            "Low": [99.0], "Close": [100.0], "Volume": [10], "Stocks": [50],
        })
        self._write_parquet(tmp_path, 2024, {
            "Date": ["2024-01-02", "2024-01-03"], "Code": ["005930", "999999"],
            "Open": [102.0, 1.0], "High": [103.0, 1.0], "Low": [101.0, 1.0],
            "Close": [102.0, 1.0], "Volume": [11, 1], "Stocks": [50, 1],
        })
        bars = load_marcap_bars("005930", data_dir=tmp_path)
        assert bars["date"].tolist() == [date(2023, 12, 28), date(2024, 1, 2)]
        assert list(bars.columns) == ["date", "open", "high", "low", "close", "volume"]

    def test_zero_price_rows_dropped(self, tmp_path):
        self._write_parquet(tmp_path, 2024, {
            "Date": ["2024-01-02", "2024-01-03"], "Code": ["000001", "000001"],
            "Open": [0.0, 100.0], "High": [0.0, 101.0], "Low": [0.0, 99.0],
            "Close": [0.0, 100.0], "Volume": [0, 5], "Stocks": [10, 10],
        })
        bars = load_marcap_bars("000001", data_dir=tmp_path)
        assert len(bars) == 1

    def test_missing_code_returns_none(self, tmp_path):
        self._write_parquet(tmp_path, 2024, {
            "Date": ["2024-01-02"], "Code": ["005930"], "Open": [1.0], "High": [1.0],
            "Low": [1.0], "Close": [1.0], "Volume": [1], "Stocks": [1],
        })
        assert load_marcap_bars("999999", data_dir=tmp_path) is None
```

- [ ] **Step 2: 실패 확인** → ImportError
- [ ] **Step 3: 구현**:

```python
_DEFAULT_DIR = Path(__file__).resolve().parents[2] / "data" / "marcap"
_RAW_COLS = ["Date", "Code", "Open", "High", "Low", "Close", "Volume", "Stocks"]


def load_marcap_bars(code: str, data_dir: Path | None = None) -> pd.DataFrame | None:
    """연도별 marcap parquet에서 한 종목의 일봉을 모아 분할 보정 후 반환. 없으면 None."""
    directory = data_dir or _DEFAULT_DIR
    frames: list[pd.DataFrame] = []
    for path in sorted(directory.glob("marcap-*.parquet")):
        try:
            df = pd.read_parquet(path, columns=_RAW_COLS)
        except Exception:
            continue
        part = df[df["Code"].astype(str).str.zfill(6) == code]
        if not part.empty:
            frames.append(part)
    if not frames:
        return None
    merged = pd.concat(frames, ignore_index=True)
    merged.columns = [c.lower() for c in merged.columns]
    merged["date"] = pd.to_datetime(merged["date"]).dt.date
    for col in ("open", "high", "low", "close", "volume", "stocks"):
        merged[col] = pd.to_numeric(merged[col], errors="coerce")
    merged = merged[(merged["close"] > 0) & (merged["open"] > 0)]
    if merged.empty:
        return None
    merged = merged.sort_values("date").drop_duplicates("date").reset_index(drop=True)
    adjusted = adjust_for_splits(merged)
    return adjusted[["date", "open", "high", "low", "close", "volume"]].reset_index(drop=True)
```

- [ ] **Step 4: 통과 확인** → PASS. (테스트 파일 상단 `from datetime import date` 필요)
- [ ] **Step 5: Commit** — `git commit -m "feat(lab): load_marcap_bars — 상폐 종목 일봉 폴백 로더"`

### Task B3: 폴백 병합 + run_lab 배선 + 재검증

**Files:** Modify `backend/app/lab/marcap_bars.py`, `backend/scripts/run_lab.py` / Test `backend/tests/lab/test_marcap_bars.py`

- [ ] **Step 1: 실패하는 테스트**:

```python
class TestMergeWithFallback:
    def test_fallback_fills_missing_codes_only(self):
        fetched = {"A": _df([1] * 200, [1] * 200)}
        def loader(code):
            return _df([2] * 200, [1] * 200) if code == "B" else None
        merged, n_fallback = merge_bars_with_fallback(fetched, ["A", "B", "C"], loader, min_bars=150)
        assert set(merged) == {"A", "B"} and n_fallback == 1
        assert merged["A"]["close"].iloc[0] == 1  # 원본 우선

    def test_short_fallback_rejected(self):
        merged, n = merge_bars_with_fallback({}, ["B"], lambda c: _df([2] * 10, [1] * 10), min_bars=150)
        assert merged == {} and n == 0
```

- [ ] **Step 2: 실패 확인** → ImportError
- [ ] **Step 3: 구현**:

```python
def merge_bars_with_fallback(
    fetched: dict[str, pd.DataFrame],
    codes: list[str],
    fallback_loader,
    min_bars: int = 150,
) -> tuple[dict[str, pd.DataFrame], int]:
    """fetcher가 못 채운 코드만 폴백으로 보완. (병합 결과, 폴백 사용 종목 수)."""
    merged = dict(fetched)
    n_fallback = 0
    for code in codes:
        if code in merged:
            continue
        try:
            bars = fallback_loader(code)
        except Exception:
            continue
        if bars is not None and len(bars) >= min_bars:
            merged[code] = bars.reset_index(drop=True)
            n_fallback += 1
    return merged, n_fallback
```

- [ ] **Step 4: 통과 + 전체 테스트** → PASS
- [ ] **Step 5: run_lab 배선** — main()의 커버리지 계산 직전에:

```python
    bars = await _load_bars(all_codes, lookback)
    fallback_count = 0
    if args.universe == "marcap":
        from app.lab.marcap_bars import load_marcap_bars, merge_bars_with_fallback
        bars, fallback_count = merge_bars_with_fallback(bars, all_codes, load_marcap_bars)
        if fallback_count:
            print(f"marcap 폴백: {fallback_count}종목 시세 보완 (분할 보정 적용)")
    coverage = len(bars) / max(1, len(all_codes))
```
report에 `"fallback_bars_count": fallback_count` 추가. universe_note 로직 뒤에:

```python
    if fallback_count and args.universe == "marcap":
        fallback_note = f"상폐 등 {fallback_count}종목은 marcap 시세(분할 보정, 배당락 무보정)로 보완했습니다."
        universe_note = f"{universe_note} {fallback_note}" if universe_note else fallback_note
```

- [ ] **Step 6: marcap 2020/2021 다운로드** — `curl -sL -o data/marcap/marcap-2020.parquet https://github.com/FinanceData/marcap/raw/master/data/marcap-2020.parquet` (2021 동일). 로드 확인.
- [ ] **Step 7: 4전략 재검증 실행** — 각: `./.venv/Scripts/python.exe scripts/run_lab.py --strategy <id> --start 2020-01-01 --end 2026-07-01 --top-n 80` (id: trend_tsmom, high52_breakout, legacy_patterns, vol_breakout). 커버리지·fallback_count·판정 변화를 기록.
- [ ] **Step 8: 스펙에 실측 결과 절 추가** + Commit + PR + 머지 — `git commit -m "feat(lab): marcap 가격 폴백 + 4전략 재검증"`. 판정이 바뀌면(예: pass→watch) 사실대로 기록.

---

## PR C — 횡단면 모멘텀 (브랜치 feat/lab-xs-momentum)

### Task C1: 하네스 panel_signals 경로

**Files:** Modify `backend/app/lab/walkforward.py:141-183` / Test `backend/tests/lab/test_walkforward.py`

- [ ] **Step 1: 실패하는 테스트** — test_walkforward.py에 (기존 픽스처 헬퍼 재사용 — 파일 열어 bars 생성 헬퍼 확인 후 맞춤):

```python
class _PanelEcho:
    """panel_signals 훅 검증용 — 패널 전체를 보고 코드별 고정 신호 방출."""
    id = "panel_echo"
    label = "패널 에코"
    causal_signals = True

    def fit(self, train_bars):
        return {}

    def signals(self, code, bars, params):
        return []

    def panel_signals(self, bars_by_code, params):
        out = []
        for code, bars in sorted(bars_by_code.items()):
            dates = pd.to_datetime(bars["date"]).dt.date.tolist()
            if len(dates) > 10:
                close = float(bars["close"].iloc[10])
                out.append(Signal(code=code, signal_date=dates[10], stop_price=close * 0.9))
        return out


class TestPanelSignalsPath:
    def test_panel_hook_called_and_universe_filtered(self):
        # 코드 A는 유니버스에 있고 B는 없음 → A의 신호만 트레이드가 된다
        bars = {c: make_bars(60) for c in ("A", "B")}  # make_bars: 기존 테스트 헬퍼
        windows = walk_forward_windows(bars_start_date, bars_end_date, 0, 1, 1)  # 실제 시그니처에 맞춤
        result = run_walk_forward(
            strategy=_PanelEcho(), bars_by_code=bars,
            universe_fn=lambda w: ["A"], cost_model=CostModel(), windows=windows,
        )
        assert all(t.code == "A" for t in result.trades)
        assert all(s.code == "A" for s in result.signals)
```
(테스트 작성 시 기존 test_walkforward.py의 bars/윈도우 헬퍼 컨벤션을 먼저 읽고 동일하게 맞춘다 — 날짜 상수·make_bars 이름이 다르면 그에 맞춰 조정. 단, 검증 대상 동작 자체는 위와 동일해야 한다.)

- [ ] **Step 2: 실패 확인** → panel_signals 미호출로 trades 빈 리스트 → FAIL
- [ ] **Step 3: 구현** — `_run_causal`에서 신호 수집부를 분기:

```python
    all_trades: list[Trade] = []
    used_signals: list[Signal] = []
    last_test_end = max(w.test_end for w in windows)

    visible_by_code = {
        code: _slice(bars_by_code[code], end=last_test_end) for code in ranges_by_code
    }
    visible_by_code = {c: df for c, df in visible_by_code.items() if not df.empty}

    if hasattr(strategy, "panel_signals"):
        # 횡단면 전략 — 패널 1회 호출 후 코드별로 나눠 기존 필터/시뮬레이션 재사용
        raw_by_code: dict[str, list[Signal]] = {}
        for s in strategy.panel_signals(visible_by_code, params):
            raw_by_code.setdefault(s.code, []).append(s)
    else:
        raw_by_code = None

    for code, code_windows in ranges_by_code.items():
        visible = visible_by_code.get(code)
        if visible is None:
            continue
        candidates = raw_by_code.get(code, []) if raw_by_code is not None \
            else strategy.signals(code, visible, params)
        signals = [
            s for s in candidates
            if any(w.test_start <= s.signal_date <= w.test_end for w in code_windows)
        ]
        used_signals.extend(signals)
        all_trades.extend(simulate_trades(visible, signals, cost_model, strategy.id))
```

- [ ] **Step 4: 통과 + 기존 walkforward 테스트 회귀 확인** → 전부 PASS
- [ ] **Step 5: Commit** — `git commit -m "feat(lab): 하네스 panel_signals 훅 — 횡단면 전략 지원"`

### Task C2: xs_momentum 전략

**Files:** Create `backend/app/strategies/xs_momentum.py` / Test `backend/tests/lab/test_xs_momentum.py`

- [ ] **Step 1: 실패하는 테스트**:

```python
from datetime import date

import pandas as pd

from app.lab.types import Signal
from app.strategies.xs_momentum import XsMomentumStrategy


def make_bars(daily_ret: float, n: int = 300, start: str = "2023-01-02") -> pd.DataFrame:
    dates = pd.bdate_range(start, periods=n)
    closes = [100.0]
    for _ in range(n - 1):
        closes.append(closes[-1] * (1 + daily_ret))
    return pd.DataFrame({
        "date": dates.date, "open": closes, "high": [c * 1.01 for c in closes],
        "low": [c * 0.99 for c in closes], "close": closes, "volume": [1000] * n,
    })


class TestXsMomentum:
    def test_picks_strongest_when_all_positive(self):
        strategy = XsMomentumStrategy()
        panel = {
            "STRONG": make_bars(0.004), "MID": make_bars(0.002),
            "WEAK": make_bars(0.0005), "FLAT": make_bars(0.0),
        }
        signals = strategy.panel_signals(panel, {})
        codes = {s.code for s in signals}
        assert "STRONG" in codes           # 최강 종목은 반드시 선정
        assert "FLAT" not in codes         # 모멘텀 0 이하는 제외
        for s in signals:
            assert s.max_holding_days == 21
            assert s.stop_price > 0

    def test_negative_momentum_universe_yields_nothing(self):
        strategy = XsMomentumStrategy()
        panel = {"D1": make_bars(-0.002), "D2": make_bars(-0.003)}
        assert strategy.panel_signals(panel, {}) == []

    def test_short_history_ignored(self):
        strategy = XsMomentumStrategy()
        panel = {"NEW": make_bars(0.005, n=100), "OLD": make_bars(0.003)}
        codes = {s.code for s in strategy.panel_signals(panel, {})}
        assert "NEW" not in codes and "OLD" in codes

    def test_causality_truncated_panel_is_subset(self):
        strategy = XsMomentumStrategy()
        panel = {"A": make_bars(0.004), "B": make_bars(0.002), "C": make_bars(0.001)}
        full = {(s.code, s.signal_date) for s in strategy.panel_signals(panel, {})}
        cutoff = date(2024, 1, 31)
        truncated_panel = {
            c: df[pd.to_datetime(df["date"]).dt.date <= cutoff].reset_index(drop=True)
            for c, df in panel.items()
        }
        truncated = {(s.code, s.signal_date) for s in strategy.panel_signals(truncated_panel, {})}
        assert truncated == {x for x in full if x[1] <= cutoff}
```

- [ ] **Step 2: 실패 확인** → ModuleNotFoundError
- [ ] **Step 3: 구현**:

```python
"""횡단면 모멘텀 (상대 강도) — 유니버스에서 상대적으로 강한 종목을 산다.

시계열 모멘텀(trend_tsmom: "이 종목이 자기 과거보다 강한가")과 독립적인,
가장 오래 검증된 팩터("남들보다 강한가"). 규칙 고정, 학습 없음:
- 월 첫 거래일 리밸런스, 12-1개월 모멘텀 (최근 1개월 제외 — 단기 반전 회피)
- 그 달 유효 종목(253봉 이상) 중 모멘텀 > 0 이면서 상위 10% (최소 5종목)
- 손절 15%, 목표 없음, 보유 21거래일 (다음 리밸런스까지 — 여전히 상위면 재신호)
"""
from __future__ import annotations

import math
from typing import Mapping

import pandas as pd

from ..lab.types import Signal

_MIN_BARS = 253
_SKIP_BARS = 21
_MOM_BARS = 252
_STOP_PCT = 0.15
_MAX_HOLDING = 21
_TOP_PCT = 0.10
_MIN_PICKS = 5


class XsMomentumStrategy:
    id = "xs_momentum"
    label = "횡단면 모멘텀 (상대 강도, 월 1회)"
    causal_signals = True

    def fit(self, train_bars: dict[str, pd.DataFrame]) -> dict:
        return {}

    def signals(self, code: str, bars: pd.DataFrame, params: dict) -> list[Signal]:
        # 단독 종목으로는 "상대 강도"가 정의되지 않는다 — 패널 경로 전용
        return []

    def panel_signals(self, bars_by_code: Mapping[str, pd.DataFrame], params: dict) -> list[Signal]:
        # (month_key) -> code -> (signal_date, momentum, close)
        by_month: dict[str, dict[str, tuple]] = {}
        for code, bars in bars_by_code.items():
            if bars is None or len(bars) < _MIN_BARS:
                continue
            dates = pd.to_datetime(bars["date"]).dt.date.tolist()
            closes = bars["close"].astype(float).tolist()
            for i in range(_MIN_BARS - 1, len(bars)):
                if i > 0 and dates[i].month == dates[i - 1].month:
                    continue  # 월 첫 거래일만
                base, recent, close = closes[i - _MOM_BARS], closes[i - _SKIP_BARS], closes[i]
                if base <= 0 or recent <= 0 or close <= 0:
                    continue
                month_key = f"{dates[i].year:04d}-{dates[i].month:02d}"
                by_month.setdefault(month_key, {})[code] = (dates[i], recent / base - 1, close)

        out: list[Signal] = []
        for month_key in sorted(by_month):
            entries = by_month[month_key]
            n_picks = max(_MIN_PICKS, math.ceil(len(entries) * _TOP_PCT))
            ranked = sorted(entries.items(), key=lambda kv: kv[1][1], reverse=True)
            for code, (signal_date, momentum, close) in ranked[:n_picks]:
                if momentum <= 0:
                    break  # 내림차순이므로 이후는 전부 0 이하
                out.append(Signal(
                    code=code, signal_date=signal_date,
                    stop_price=close * (1 - _STOP_PCT),
                    target_price=None, max_holding_days=_MAX_HOLDING,
                ))
        out.sort(key=lambda s: (s.signal_date, s.code))
        return out
```

- [ ] **Step 4: 통과 확인** → PASS (4개)
- [ ] **Step 5: 레지스트리 등록** — registry.py에 `from .xs_momentum import XsMomentumStrategy` + `"xs_momentum": XsMomentumStrategy,`
- [ ] **Step 6: 전체 백엔드 테스트** → PASS. Commit — `git commit -m "feat(lab): xs_momentum — 횡단면 모멘텀 전략 (패널 경로)"`

### Task C3: 검증 실행 + 마무리

- [ ] **Step 1: 판정 실행** — `./.venv/Scripts/python.exe scripts/run_lab.py --strategy xs_momentum --start 2020-01-01 --end 2026-07-01 --top-n 80` (marcap 유니버스 + PR B의 폴백 반영)
- [ ] **Step 2: 결과 기록** — 스펙 하단에 "실측 결과" 절 추가 (EV/CI/랜덤 대비/MDD/판정 그대로 — 탈락이면 탈락으로 기록)
- [ ] **Step 3: 브라우저 확인** — `/journal/strategies`에 새 판정 카드, 통과 시 `/`의 신호 게이트에 합류 (refresh 트리거)
- [ ] **Step 4: Commit + PR + 머지** — 자율 머지, 메모리(trading-lab-pivot.md) 갱신, 최종 보고
