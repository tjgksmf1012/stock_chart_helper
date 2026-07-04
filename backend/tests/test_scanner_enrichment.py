"""스캔 결과 수급 정렬 보강(_enrich_money_flow_alignment) 테스트."""
from __future__ import annotations

import pytest

from app.services.scanner import _enrich_money_flow_alignment


def _row(code: str, pattern_type: str | None = "double_bottom", no_signal: bool = False) -> dict:
    return {
        "code": code,
        "pattern_type": pattern_type,
        "no_signal_flag": no_signal,
        "trade_readiness_score": 0.5,
    }


def _fake_flow_factory(alignment_by_code: dict[str, str]):
    async def _fake(code: str, pattern_type: str | None = None, neckline: float | None = None, target_level: float | None = None):
        alignment = alignment_by_code.get(code)
        if alignment is None:
            return None
        return {"alignment": alignment}

    return _fake


@pytest.mark.anyio
async def test_aligned_and_diverged_boosts(monkeypatch):
    monkeypatch.setattr(
        "app.services.money_flow_service.get_money_flow",
        _fake_flow_factory({"A": "aligned", "B": "diverged", "C": "mixed", "D": "neutral"}),
    )
    rows = [_row("A"), _row("B"), _row("C"), _row("D")]
    await _enrich_money_flow_alignment(rows)

    assert rows[0]["money_flow_rank_boost"] == 0.05
    assert rows[1]["money_flow_rank_boost"] == -0.05
    assert rows[2]["money_flow_rank_boost"] == -0.02
    assert rows[3]["money_flow_rank_boost"] == 0.0
    assert rows[0]["money_flow_alignment"] == "aligned"


@pytest.mark.anyio
async def test_skips_no_pattern_and_no_signal_rows(monkeypatch):
    calls: list[str] = []

    async def _tracking(code: str, pattern_type: str | None = None, neckline: float | None = None, target_level: float | None = None):
        calls.append(code)
        return {"alignment": "aligned"}

    monkeypatch.setattr("app.services.money_flow_service.get_money_flow", _tracking)
    rows = [_row("A", pattern_type=None), _row("B", no_signal=True), _row("C")]
    await _enrich_money_flow_alignment(rows)

    assert calls == ["C"]
    assert "money_flow_rank_boost" not in rows[0]
    assert "money_flow_rank_boost" not in rows[1]


@pytest.mark.anyio
async def test_fetch_failure_is_ignored(monkeypatch):
    async def _boom(code: str, pattern_type: str | None = None, neckline: float | None = None, target_level: float | None = None):
        raise RuntimeError("KIS down")

    monkeypatch.setattr("app.services.money_flow_service.get_money_flow", _boom)
    rows = [_row("A")]
    await _enrich_money_flow_alignment(rows)  # 예외가 새지 않아야 함

    assert "money_flow_rank_boost" not in rows[0]


@pytest.mark.anyio
async def test_respects_top_n(monkeypatch):
    calls: list[str] = []

    async def _tracking(code: str, pattern_type: str | None = None, neckline: float | None = None, target_level: float | None = None):
        calls.append(code)
        return {"alignment": "aligned"}

    monkeypatch.setattr("app.services.money_flow_service.get_money_flow", _tracking)
    rows = [_row(str(i)) for i in range(10)]
    await _enrich_money_flow_alignment(rows, top_n=3)

    assert calls == ["0", "1", "2"]
