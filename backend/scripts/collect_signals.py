"""헤드리스 신호 수집 CLI — GitHub Actions가 매일 16:35(KST)에 실행한다.

로컬 앱을 켜지 않는 날에도 검증 통과(pass/watch) 전략의 신호가
backend/collected/paper_signals.jsonl 에 쌓이게 하는 수집 로봇.
로컬 백엔드는 시작 시/스케줄로 이 파일을 동기화해 종이매매 DB에 넣는다.

사용 (backend/에서):
  python scripts/collect_signals.py [--top-n 60] [--lookback-bars 420]
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Windows 콘솔(cp949)에서 한글 출력이 깨지지 않게
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from app.api.routes.lab import load_latest_reports  # noqa: E402
from app.services.collected_signals import merge_signal_records  # noqa: E402
from app.services.lab_signals import collect_recent_signals, eligible_strategy_ids  # noqa: E402
from app.strategies.registry import make_strategy  # noqa: E402

_BASE = Path(__file__).resolve().parents[1]
_REPORTS_DIR = _BASE / "collected" / "lab_reports"
_OUT_PATH = _BASE / "collected" / "paper_signals.jsonl"


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--top-n", type=int, default=60)
    parser.add_argument("--lookback-bars", type=int, default=420)
    args = parser.parse_args()

    reports = load_latest_reports(_REPORTS_DIR)
    if not reports:
        print(f"[중단] 공개 리포트 없음: {_REPORTS_DIR} — run_lab을 먼저 실행해 커밋하세요.")
        sys.exit(1)
    verdict_by_id = {r["strategy"]: r.get("verdict") for r in reports if r.get("strategy")}
    label_by_id = {r["strategy"]: r.get("label", r["strategy"]) for r in reports if r.get("strategy")}
    eligible = eligible_strategy_ids(reports)
    print(f"자격 전략: {eligible}")
    if not eligible:
        print("검증 통과 전략이 없어 수집할 것이 없습니다.")
        return

    from app.lab.universe import fetch_current_universe_biased
    from app.services.data_fetcher import get_data_fetcher

    codes = await fetch_current_universe_biased(args.top_n)
    if not codes:
        print("[실패] 유니버스를 만들지 못했습니다 (데이터 소스 접근 불가?).")
        sys.exit(1)
    print(f"유니버스: {len(codes)}종목")

    fetcher = get_data_fetcher()
    bars_by_code: dict = {}
    for i, code in enumerate(codes, 1):
        try:
            df = await fetcher.get_stock_ohlcv_by_timeframe(code, "1d", lookback_days=args.lookback_bars)
            if df is not None and len(df) >= 60:
                bars_by_code[code] = df.reset_index(drop=True)
        except Exception as exc:
            print(f"  [{i}/{len(codes)}] {code} 시세 실패: {exc}")
    print(f"시세 확보: {len(bars_by_code)}/{len(codes)}종목")
    if not bars_by_code:
        print("[실패] 시세를 하나도 못 받았습니다 (러너 IP 차단 가능성).")
        sys.exit(1)

    as_of = date.today()
    collected_at = datetime.now().isoformat(timespec="seconds")
    new_records: list[dict] = []
    for strategy_id in eligible:
        try:
            strategy = make_strategy(strategy_id)
        except KeyError:
            continue
        for sig in collect_recent_signals(strategy, bars_by_code, as_of=as_of, lookback_days=5):
            new_records.append({
                **sig,
                "strategy_label": label_by_id.get(strategy_id, strategy_id),
                "verdict": verdict_by_id.get(strategy_id),
                "collected_at": collected_at,
            })

    existing_lines = (
        _OUT_PATH.read_text(encoding="utf-8").splitlines() if _OUT_PATH.exists() else []
    )
    lines, added = merge_signal_records(existing_lines, new_records)
    _OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    _OUT_PATH.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    print(f"신호 {len(new_records)}건 중 신규 {added}건 추가 → {_OUT_PATH} (총 {len(lines)}줄)")


if __name__ == "__main__":
    asyncio.run(main())
