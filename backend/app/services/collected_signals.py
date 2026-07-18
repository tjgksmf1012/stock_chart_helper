"""클라우드 수집 신호(JSONL)의 병합·파싱 — 순수 로직.

GitHub Actions가 매일 수집해 커밋하는 backend/collected/paper_signals.jsonl 을
다루는 공용 코드. 한 줄 = 신호 1건, dedupe 키 = (strategy_id, code, signal_date).
IO(파일/네트워크)는 호출부(scripts/collect_signals.py, routes/lab.py)가 담당한다.
"""
from __future__ import annotations

import json
from typing import Any

_REQUIRED_KEYS = ("strategy_id", "code", "signal_date", "stop_price")


def record_key(record: dict[str, Any]) -> tuple[str, str, str]:
    return (str(record["strategy_id"]), str(record["code"]), str(record["signal_date"]))


def merge_signal_records(
    existing_lines: list[str], new_records: list[dict[str, Any]]
) -> tuple[list[str], int]:
    """기존 JSONL 줄에 새 레코드를 append (중복 키는 무시). (전체 줄, 추가 수)."""
    seen: set[tuple[str, str, str]] = set()
    for line in existing_lines:
        try:
            seen.add(record_key(json.loads(line)))
        except Exception:
            continue  # 깨진 기존 줄은 그대로 두되 dedupe 대상에서 제외

    lines = list(existing_lines)
    added = 0
    for record in new_records:
        key = record_key(record)
        if key in seen:
            continue
        seen.add(key)
        lines.append(json.dumps(record, ensure_ascii=False))
        added += 1
    return lines, added


def parse_collected_records(text: str) -> list[dict[str, Any]]:
    """JSONL 텍스트를 레코드 목록으로. 깨진 줄·필수 키 누락 줄은 조용히 건너뛴다."""
    records: list[dict[str, Any]] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except Exception:
            continue
        if not isinstance(record, dict) or any(k not in record for k in _REQUIRED_KEYS):
            continue
        records.append(record)
    return records
