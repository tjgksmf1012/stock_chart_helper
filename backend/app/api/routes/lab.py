"""실험실 API — 랩 검증 리포트(data/lab/*.json)를 전략별 최신본으로 제공.

리포트는 scripts/run_lab.py가 생성한다. 이 API는 읽기 전용이며, 트레이드
목록(수천 건)은 목록 응답에서 제외해 payload를 가볍게 유지한다.
스펙(2026-07-12 트레이딩 랩) Phase 3: 검증을 통과하지 못한 전략의 신호는
추천에 쓰이지 않는다 — 그 판정의 원천 데이터가 이 엔드포인트다.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/lab", tags=["lab"])

_LAB_DIR = Path(__file__).resolve().parents[3] / "data" / "lab"

_VERDICT_ORDER = {"pass": 0, "watch": 1, "fail": 2}


def load_latest_reports(lab_dir: Path) -> list[dict[str, Any]]:
    """전략별 최신 리포트 (generated_at 기준). 깨진 파일은 건너뛴다."""
    latest: dict[str, dict[str, Any]] = {}
    if not lab_dir.exists():
        return []
    for path in lab_dir.glob("*.json"):
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("lab report 읽기 실패 (%s): %s", path.name, exc)
            continue
        strategy_id = raw.get("strategy")
        if not strategy_id:
            continue
        generated = str(raw.get("generated_at", ""))
        if strategy_id not in latest or generated > str(latest[strategy_id].get("generated_at", "")):
            latest[strategy_id] = raw
    return sorted(
        latest.values(),
        key=lambda r: (_VERDICT_ORDER.get(r.get("verdict"), 3), -(r.get("ev_pct") or 0.0)),
    )


def _without_trades(report: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in report.items() if k != "trades"}


@router.get("/reports")
async def list_lab_reports() -> dict[str, Any]:
    reports = load_latest_reports(_LAB_DIR)
    return {"reports": [_without_trades(r) for r in reports]}


@router.get("/reports/{strategy_id}")
async def get_lab_report(strategy_id: str, include_trades: bool = False) -> dict[str, Any]:
    for report in load_latest_reports(_LAB_DIR):
        if report.get("strategy") == strategy_id:
            return report if include_trades else _without_trades(report)
    raise HTTPException(status_code=404, detail=f"전략 리포트 없음: {strategy_id}")
