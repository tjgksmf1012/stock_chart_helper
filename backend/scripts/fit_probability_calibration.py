#!/usr/bin/env python3
"""probability_engine.py의 규칙 기반 확률을 실제 승률에 맞춰 재보정한다.

과거 백테스트 유니버스 전체를 실제 운영 파이프라인(analyze_symbol_dataframe)으로
다시 돌려서 (예측 확률, 실제 승/패) 쌍을 모으고, isotonic regression으로
"이 모델이 X%라고 할 때 실제 승률은 몇 %였나" 매핑을 학습해 저장한다.

실제 KRX 데이터가 있는 환경(사용자 로컬 컴퓨터)에서 실행해야 의미가 있다 —
KRX/Naver 접근이 막힌 샌드박스에서 돌리면 표본이 모이지 않아 아무 매핑도
저장되지 않는다(기존 동작 유지, 즉 무보정).

기본적으로 손으로 고른 79종목 대신, 실제 KRX 전체 유니버스(스캔에도 쓰는 검증된
데이터)에서 골고루 뽑은 최대 --target-size개 종목으로 학습 표본을 늘린다
(get_expanded_backtest_universe — 라이브 유니버스를 못 가져오면 79종목으로 폴백).

사용법:
    cd backend && source .venv/bin/activate
    python scripts/fit_probability_calibration.py
    python scripts/fit_probability_calibration.py --timeframe 1d --target-size 300
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.api.schemas import SymbolInfo  # noqa: E402
from app.services.backtest_engine import get_backtest_config, get_expanded_backtest_universe  # noqa: E402
from app.services.calibration_service import build_calibration_report  # noqa: E402
from app.services.offline_calibration import collect_symbol_pairs  # noqa: E402
from app.services.probability_calibration import (  # noqa: E402
    MIN_FIT_SAMPLES,
    fit_calibration_mapping,
    save_calibration_mapping,
)


async def _collect_all_pairs(timeframe: str, target_size: int) -> tuple[list[tuple[str, float, bool]], dict[str, int]]:
    from app.services.data_fetcher import get_data_fetcher

    cfg = get_backtest_config(timeframe)
    codes = await get_expanded_backtest_universe(target_size)
    fetcher = get_data_fetcher()

    all_pairs: list[tuple[str, float, bool]] = []
    totals = {"windows": 0, "signals": 0, "unresolved": 0}
    for i, code in enumerate(codes, start=1):
        try:
            df = await fetcher.get_stock_ohlcv_by_timeframe(code, timeframe, lookback_days=int(cfg["lookback_days"]))
            if df.empty or len(df) < int(cfg["min_bars"]):
                print(f"  [{i}/{len(codes)}] {code}: skipped (insufficient bars)")
                continue
            symbol = SymbolInfo(code=code, name=code, market="KOSPI", sector=None, market_cap=None, is_in_universe=True)
            pairs, meta = await collect_symbol_pairs(
                symbol, timeframe, df,
                window=int(cfg["window"]), step=int(cfg["step"]), max_forward=int(cfg["max_forward"]),
            )
            all_pairs.extend(pairs)
            totals["windows"] += meta["windows"]
            totals["signals"] += meta["signals"]
            totals["unresolved"] += meta["unresolved"]
            print(
                f"  [{i}/{len(codes)}] {code}: {len(pairs)} pairs "
                f"({meta['signals']} signals / {meta['windows']} windows / {meta['unresolved']} unresolved→loss)"
            )
        except Exception as exc:
            print(f"  [{i}/{len(codes)}] {code}: failed ({exc})")
    return all_pairs, totals


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--timeframe", default="1d")
    parser.add_argument(
        "--target-size", type=int, default=200,
        help="학습에 쓸 목표 종목 수 (기본 200 — 라이브 유니버스를 못 가져오면 79종목 고정 리스트로 폴백)",
    )
    args = parser.parse_args()

    print(f"수집 시작: timeframe={args.timeframe}, target_size={args.target_size}")
    tagged_pairs, totals = await _collect_all_pairs(args.timeframe, args.target_size)
    print(f"\n총 {len(tagged_pairs)}개 (예측, 결과) 쌍 수집 완료.")
    unresolved_rate = totals["unresolved"] / max(totals["signals"], 1)
    print(
        f"  windows={totals['windows']}, signals={totals['signals']}, "
        f"unresolved(→loss로 계산)={totals['unresolved']} ({unresolved_rate:.0%})"
    )

    if len(tagged_pairs) < MIN_FIT_SAMPLES:
        print(
            f"표본 부족({len(tagged_pairs)} < {MIN_FIT_SAMPLES}) — 과적합 위험이 커서 저장하지 않습니다.\n"
            "샌드박스/네트워크 제한으로 KRX 데이터를 못 받아온 경우 이 결과가 나옵니다. "
            "실제 인터넷이 되는 환경에서 다시 실행해주세요."
        )
        return

    pairs = [(p, w) for _, p, w in tagged_pairs]
    report = build_calibration_report(pairs)
    # "그냥 base_rate를 항상 예측"했을 때의 brier score -- 이보다 나쁘면 이 휴리스틱은
    # 개별 신호를 구분하는 능력이 전혀 없고 오히려 잡음을 더하고 있다는 뜻이다.
    baseline_brier = report.base_rate * (1 - report.base_rate)
    print(
        f"\n보정 전 리포트: base_rate={report.base_rate:.3f}, mean_predicted={report.mean_predicted:.3f}, "
        f"mean_gap={report.mean_gap:+.3f}, brier={report.brier_score:.3f} (base_rate만 항상 예측 시 {baseline_brier:.3f}), "
        f"ece={report.ece:.3f}\n"
        f"  reliability: {report.reliability}"
    )
    if report.brier_score >= baseline_brier:
        print(
            "  ⚠ brier score가 base_rate 고정 예측보다 나쁘거나 같습니다 — 지금 휴리스틱이 "
            "개별 신호를 구분하는 능력이 거의 없다는 뜻입니다. isotonic 보정은 과신만 고칠 뿐,\n"
            "    이 문제 자체는 못 고칩니다."
        )
    print("  구간별(하한-상한 | 표본수 | 예측 | 실제 | 격차):")
    for b in report.bins:
        flag = " (표본부족)" if b.low_confidence else ""
        print(f"    {b.lower:.2f}-{b.upper:.2f} | n={b.count:<4d} | pred={b.predicted:.3f} | obs={b.observed:.3f} | gap={b.gap:+.3f}{flag}")

    print("\n패턴 타입별 분석 (표본 30건 이상만 표시):")
    by_pattern: dict[str, list[tuple[float, bool]]] = {}
    for pattern_type, predicted, won in tagged_pairs:
        by_pattern.setdefault(pattern_type, []).append((predicted, won))
    for pattern_type, sub_pairs in sorted(by_pattern.items(), key=lambda kv: -len(kv[1])):
        if len(sub_pairs) < 30:
            continue
        sub_report = build_calibration_report(sub_pairs)
        sub_baseline = sub_report.base_rate * (1 - sub_report.base_rate)
        skill_flag = "" if sub_report.brier_score < sub_baseline else "  ⚠ base_rate 고정보다 안 좋음"
        print(
            f"  {pattern_type:<28s} n={len(sub_pairs):<5d} base_rate={sub_report.base_rate:.3f} "
            f"brier={sub_report.brier_score:.3f} (baseline {sub_baseline:.3f}){skill_flag}"
        )

    mapping = fit_calibration_mapping(pairs)
    if mapping is None:
        print("학습 실패 — 저장하지 않습니다.")
        return

    save_calibration_mapping(mapping)
    print(f"저장 완료: sample_size={mapping.sample_size}, fitted_at={mapping.fitted_at}")


if __name__ == "__main__":
    asyncio.run(main())
