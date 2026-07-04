#!/usr/bin/env python3
"""probability_engine.py의 손으로 정한 9개 하위 점수 가중치를 실제 데이터로 학습한다.

fit_probability_calibration.py가 이미 확인한 바로는, 지금 감으로 정한 가중치 합
(0.27 * rule + 0.25 * empirical + ...)은 base_rate만 항상 예측하는 것보다도
brier score가 나쁘다 -- 즉 개별 신호를 구분하는 능력이 사실상 없다. 이 스크립트는
같은 과거 백테스트 유니버스를 실제 운영 파이프라인(analyze_symbol_dataframe)으로
다시 돌려서 9개 방향정렬 특징(own-direction feature) + 실제 승패 표본을 모으고,
로지스틱 회귀로 진짜 가중치를 학습해 저장한다.

fit_probability_calibration.py와 마찬가지로:
  - 실제 KRX 데이터가 있는 환경(사용자 로컬 컴퓨터)에서 실행해야 의미가 있다.
  - 수집 전에 run_backtest()를 먼저 기다려서 get_pattern_stats_map()이 패턴 타입별
    실제 승률을 갖고 있도록 한다 (안 그러면 empirical 컴포넌트가 범용 기본값만 씀).
  - fit_probability_model()은 저장을 자동으로 하지 않는다 -- MIN_FIT_SAMPLES 미만이면
    None을 반환하고, 이 스크립트가 그 경우 저장하지 않고 이유를 출력한다.

사용법:
    cd backend && source .venv/bin/activate
    python scripts/fit_probability_model.py
    python scripts/fit_probability_model.py --timeframe 1d --target-size 300
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.api.schemas import SymbolInfo  # noqa: E402
from app.services.backtest_engine import get_backtest_config, get_expanded_backtest_universe, run_backtest  # noqa: E402
from app.services.calibration_service import build_calibration_report  # noqa: E402
from app.services.offline_calibration import collect_symbol_pairs  # noqa: E402
from app.services.probability_model import (  # noqa: E402
    MIN_FIT_SAMPLES,
    fit_probability_model,
    predict_directional_probability,
    save_probability_model,
)


async def _collect_all_rows(
    timeframe: str, target_size: int
) -> tuple[list[tuple[dict[str, float], bool]], list[tuple[str, float, bool]], dict[str, int]]:
    from app.services.data_fetcher import get_data_fetcher

    cfg = get_backtest_config(timeframe)
    codes = await get_expanded_backtest_universe(target_size)
    fetcher = get_data_fetcher()

    all_rows: list[tuple[dict[str, float], bool]] = []
    all_pairs: list[tuple[str, float, bool]] = []
    totals = {"windows": 0, "signals": 0, "unresolved": 0}
    for i, code in enumerate(codes, start=1):
        try:
            df = await fetcher.get_stock_ohlcv_by_timeframe(code, timeframe, lookback_days=int(cfg["lookback_days"]))
            if df.empty or len(df) < int(cfg["min_bars"]):
                print(f"  [{i}/{len(codes)}] {code}: skipped (insufficient bars)")
                continue
            symbol = SymbolInfo(code=code, name=code, market="KOSPI", sector=None, market_cap=None, is_in_universe=True)
            feature_rows: list[tuple[dict[str, float], bool]] = []
            pairs, meta = await collect_symbol_pairs(
                symbol, timeframe, df,
                window=int(cfg["window"]), step=int(cfg["step"]), max_forward=int(cfg["max_forward"]),
                feature_rows=feature_rows,
            )
            all_rows.extend(feature_rows)
            all_pairs.extend(pairs)
            totals["windows"] += meta["windows"]
            totals["signals"] += meta["signals"]
            totals["unresolved"] += meta["unresolved"]
            print(
                f"  [{i}/{len(codes)}] {code}: {len(feature_rows)} feature rows "
                f"({meta['signals']} signals / {meta['windows']} windows / {meta['unresolved']} unresolved→loss)"
            )
        except Exception as exc:
            print(f"  [{i}/{len(codes)}] {code}: failed ({exc})")
    return all_rows, all_pairs, totals


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--timeframe", default="1d")
    parser.add_argument(
        "--target-size", type=int, default=200,
        help="학습에 쓸 목표 종목 수 (기본 200 — 라이브 유니버스를 못 가져오면 79종목 고정 리스트로 폴백)",
    )
    args = parser.parse_args()

    # fit_probability_calibration.py와 같은 이유: get_pattern_stats_map()이 캐시가
    # 비어 있으면 run_backtest()를 백그라운드로만 던지고 즉시 범용 기본 승률을
    # 돌려준다 -- 이 스크립트처럼 짧게 끝나는 프로세스에서는 그 계산이 끝나기 전에
    # 수집이 다 끝나버려 empirical 특징이 패턴 타입과 무관한 가짜 값만 갖게 된다.
    print("실제 패턴별 백테스트 통계 계산 중... (몇 분 걸릴 수 있음)")

    def _backtest_progress(timeframe: str, code: str, idx: int, total: int) -> None:
        print(f"\r  [{timeframe}] {idx}/{total} {code}      ", end="", flush=True)

    await run_backtest(progress_callback=_backtest_progress)
    print("\r백테스트 통계 준비 완료.                              \n")

    print(f"수집 시작: timeframe={args.timeframe}, target_size={args.target_size}")
    rows, tagged_pairs, totals = await _collect_all_rows(args.timeframe, args.target_size)
    print(f"\n총 {len(rows)}개 (특징, 승패) 표본 수집 완료.")
    unresolved_rate = totals["unresolved"] / max(totals["signals"], 1)
    print(
        f"  windows={totals['windows']}, signals={totals['signals']}, "
        f"unresolved(→loss로 계산)={totals['unresolved']} ({unresolved_rate:.0%})"
    )

    if len(rows) < MIN_FIT_SAMPLES:
        print(
            f"표본 부족({len(rows)} < {MIN_FIT_SAMPLES}) — 과적합 위험이 커서 저장하지 않습니다.\n"
            "샌드박스/네트워크 제한으로 KRX 데이터를 못 받아온 경우 이 결과가 나옵니다. "
            "실제 인터넷이 되는 환경에서 다시 실행해주세요."
        )
        return

    # 기존 손으로 정한 가중치 공식이 base_rate 고정 예측보다 못했던 것과 비교할
    # 기준선을 여기서도 같이 출력한다.
    pairs = [(p, w) for _, p, w in tagged_pairs]
    old_report = build_calibration_report(pairs)
    baseline_brier = old_report.base_rate * (1 - old_report.base_rate)
    print(
        f"\n(기존 손 가중치 공식 기준) base_rate={old_report.base_rate:.3f}, "
        f"brier={old_report.brier_score:.3f} (base_rate만 항상 예측 시 {baseline_brier:.3f})"
    )

    model = fit_probability_model(rows)
    if model is None:
        print("학습 실패 — 저장하지 않습니다.")
        return

    save_probability_model(model)
    print(f"저장 완료: sample_size={model.sample_size}, fitted_at={model.fitted_at}")

    # 학습된 모델이 실제로 base_rate 고정 예측보다 나은지 같은 표본으로 확인한다.
    new_pairs = [(predict_directional_probability(f), won) for f, won in rows]
    new_report = build_calibration_report(new_pairs)
    print(
        f"(새 학습 모델 기준) brier={new_report.brier_score:.3f} (baseline {baseline_brier:.3f}) "
        f"{'✓ baseline보다 좋음' if new_report.brier_score < baseline_brier else '⚠ baseline보다 안 좋음'}"
    )


if __name__ == "__main__":
    asyncio.run(main())
