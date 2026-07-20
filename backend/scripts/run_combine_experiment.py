"""사전 등록 실험 ③ — 전략 결합 포트폴리오의 분산 효과 측정.

공식 리포트(data/lab, 체제 게이트 구성)에서 통과(pass) 전략들의 트레이드를 모아,
개별과 동일한 자(risk_based_metrics, 트레이드당 리스크 1%)로 합산 자본곡선을 잰다.
전략 간 월별 R 상관도 함께 — "분산 효과"의 근거인 낮은 상관이 실재하는지 확인.

사용 (backend/에서): python scripts/run_combine_experiment.py
결과: data/lab_experiments/combined_portfolio_<ts>.json + 콘솔 요약
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from itertools import combinations
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from app.api.routes.lab import load_latest_reports  # noqa: E402
from app.lab.combine import (  # noqa: E402
    combine_series,
    monthly_r_series,
    monthly_sharpe,
    pairwise_correlation,
    trades_from_report_dicts,
)
from app.lab.sizing import risk_based_metrics  # noqa: E402

_LAB_DIR = Path(__file__).resolve().parents[1] / "data" / "lab"
_OUT_DIR = Path(__file__).resolve().parents[1] / "data" / "lab_experiments"
_RISK = 0.01


def main() -> None:
    reports = [r for r in load_latest_reports(_LAB_DIR) if r.get("verdict") == "pass" and r.get("trades")]
    if len(reports) < 2:
        print("[중단] 트레이드가 실린 통과 리포트가 2개 미만 — 결합할 것이 없습니다.")
        sys.exit(1)

    trades_by_id = {r["strategy"]: trades_from_report_dicts(r["trades"]) for r in reports}
    label_by_id = {r["strategy"]: r["label"] for r in reports}

    print("== 개별 (리스크 1%/트레이드) ==")
    individual = {}
    for sid, trades in trades_by_id.items():
        m = risk_based_metrics(trades, risk_pct=_RISK)
        individual[sid] = m
        print(f"  {label_by_id[sid]}: n={m['n_used']} 누적 {m['total_return_pct']:+.1%} MDD {m['mdd_pct']:.1%} avg {m['avg_r']:.2f}R")

    pooled = [t for trades in trades_by_id.values() for t in trades]
    combined = risk_based_metrics(pooled, risk_pct=_RISK)
    print("== 합산 (같은 규칙) ==")
    print(f"  n={combined['n_used']} 누적 {combined['total_return_pct']:+.1%} MDD {combined['mdd_pct']:.1%} avg {combined['avg_r']:.2f}R")

    print("== 월별 R 상관 ==")
    series = {sid: monthly_r_series(trades) for sid, trades in trades_by_id.items()}
    correlations = {}
    for a, b in combinations(sorted(series), 2):
        corr = pairwise_correlation(series[a], series[b])
        correlations[f"{a}~{b}"] = corr
        print(f"  {a} ~ {b}: {corr:+.2f}" if corr is not None else f"  {a} ~ {b}: 측정 불가")

    # 실험 ③-b: 월별 R 샤프 (리스크 크기 불변 지표) — 공통 월축, 거래 없는 달 = 0
    all_months = sorted({m for s in series.values() for m in s})
    aligned = {sid: {m: s.get(m, 0.0) for m in all_months} for sid, s in series.items()}
    sharpes = {sid: monthly_sharpe(s) for sid, s in aligned.items()}
    combined_sharpe = monthly_sharpe(combine_series(aligned.values()))
    print("== 월별 R 샤프 (③-b) ==")
    for sid, sharpe in sorted(sharpes.items(), key=lambda kv: -(kv[1] or -9)):
        print(f"  {sid}: {sharpe:.3f}" if sharpe is not None else f"  {sid}: 측정 불가")
    print(f"  합산: {combined_sharpe:.3f}" if combined_sharpe is not None else "  합산: 측정 불가")

    result = {
        "experiment": "combined_portfolio",
        "monthly_sharpe": {"individual": sharpes, "combined": combined_sharpe},
        "risk_pct": _RISK,
        "strategies": sorted(trades_by_id),
        "individual": {sid: {k: v for k, v in m.items()} for sid, m in individual.items()},
        "combined": combined,
        "monthly_r_correlations": correlations,
        "generated_at": datetime.now().isoformat(),
    }
    _OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = _OUT_DIR / f"combined_portfolio_{datetime.now():%Y%m%d_%H%M%S}.json"
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"저장: {out_path}")


if __name__ == "__main__":
    main()
