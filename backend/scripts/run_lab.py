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

# Windows 콘솔(cp949)에서 한글/유니코드 출력이 깨지지 않게
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from app.lab.baselines import random_benchmark_signals  # noqa: E402
from app.lab.costs import CostModel  # noqa: E402
from app.lab.metrics import decide_verdict, summarize  # noqa: E402
from app.lab.portfolio import portfolio_equity_metrics  # noqa: E402
from app.lab.simulate import simulate_trades  # noqa: E402
from app.lab.universe import fetch_current_universe_biased, fetch_point_in_time_universe  # noqa: E402
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
    parser.add_argument(
        "--universe", choices=["pit", "current"], default="pit",
        help="pit=시점 고정(KRX 로그인 필요할 수 있음), current=현재 상장 목록(생존 편향 — pass 불가)",
    )
    args = parser.parse_args()

    _register_strategies()
    strategy = STRATEGIES[args.strategy]()
    windows = walk_forward_windows(args.start, args.end, args.train_years, args.test_months, args.test_months)
    if not windows:
        print("검증 윈도우를 만들 수 없습니다 (기간이 너무 짧음).")
        return

    # 유니버스 구성 — pit(시점 고정)이 원칙, current는 명시적 편향 모드
    universes: dict = {}
    if args.universe == "pit":
        for w in windows:
            codes = await fetch_point_in_time_universe(w.test_start, args.top_n)
            universes[w] = codes
            print(f"유니버스 {w.test_start}: {len(codes)}종목")
        if not any(universes.values()):
            print(
                "\n[중단] 시점 고정 유니버스를 한 윈도우도 못 만들었습니다.\n"
                "  - KRX 로그인(.env의 KRX_ID/KRX_PW)을 설정하면 pit 모드를 쓸 수 있습니다.\n"
                "  - 당장 파이프라인을 돌려보려면 --universe current (생존 편향 명시 모드)를 쓰세요.\n"
                "    이 모드의 결과는 pass 판정이 불가능하며 리포트에 편향이 기록됩니다."
            )
            return
    else:
        codes = await fetch_current_universe_biased(args.top_n)
        print(f"유니버스(현재 목록, 생존 편향): {len(codes)}종목 — 모든 윈도우에 동일 적용")
        for w in windows:
            universes[w] = codes

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
    # (하네스가 실제 사용한 신호를 그대로 재사용 — 재계산 없음)
    subject_signals = result.signals
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
    verdict = decide_verdict(result.summary.ev_pct, result.ci[0], random_ev) if result.summary.n else "fail"
    universe_note = None
    if args.universe == "current" and verdict == "pass":
        # 생존 편향 유니버스로는 통과 자격이 없다 — 성적이 실제보다 좋게 나오는 편향
        verdict = "watch"
        universe_note = "현재 상장 목록(생존 편향) 기준이라 pass를 watch로 강등했습니다. KRX_ID/KRX_PW 설정 후 pit 모드로 재검증하세요."
    elif args.universe == "current":
        universe_note = "현재 상장 목록(생존 편향) 기준 — 실제 성적은 이보다 나쁠 수 있습니다."

    report = {
        "strategy": strategy.id,
        "label": strategy.label,
        "period": {"start": args.start.isoformat(), "end": args.end.isoformat()},
        "config": {"top_n": args.top_n, "train_years": args.train_years,
                   "test_months": args.test_months, "round_trip_cost_pct": cost_model.round_trip_pct},
        "universe_mode": args.universe,
        "universe_note": universe_note,
        "data_coverage": round(coverage, 3),
        "n_trades": result.summary.n,
        "ev_pct": round(result.summary.ev_pct, 5),
        "ci_95": [round(result.ci[0], 5), round(result.ci[1], 5)],
        "win_rate": round(result.summary.win_rate, 3),
        "payoff_ratio": round(result.summary.payoff_ratio, 2),
        # 순차 복리 MDD는 다종목에서 과장되므로 참고용, 대표 지표는 포트폴리오 기준
        "sequential_mdd_pct": round(result.summary.mdd_pct, 3),
        **{k: round(v, 4) for k, v in portfolio_equity_metrics(result.trades, bars, slots=10).items()},
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
    print(f"승률 {report['win_rate']:.0%}, 손익비 {report['payoff_ratio']}")
    print(f"포트폴리오(10슬롯): 누적 {report['portfolio_total_return_pct']:+.1%}, MDD {report['portfolio_mdd_pct']:.1%}")
    print(f"랜덤 벤치마크 EV: {report['random_benchmark_ev_pct']}")
    print(f"판정: {verdict.upper()}")
    if universe_note:
        print(f"주의: {universe_note}")
    print(f"저장: {out_path}")


if __name__ == "__main__":
    asyncio.run(main())
