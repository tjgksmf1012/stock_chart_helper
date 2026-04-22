from __future__ import annotations

from datetime import datetime

from app.api.routes.outcomes import PriceEvent, _decide_outcome_from_events


def test_decide_outcome_marks_win_when_target_hits_first():
    decision = _decide_outcome_from_events(
        events=[
            PriceEvent(
                when=datetime(2026, 4, 21, 15, 0),
                high=102.0,
                low=98.0,
                close=101.0,
                basis="daily_high_low",
            ),
            PriceEvent(
                when=datetime(2026, 4, 22, 15, 0),
                high=111.0,
                low=103.0,
                close=109.0,
                basis="daily_high_low",
            ),
        ],
        target_price=110.0,
        stop_price=95.0,
    )

    assert decision is not None
    assert decision.outcome == "win"
    assert decision.exit_price == 110.0
    assert decision.evaluation_basis == "daily_high_low"


def test_decide_outcome_is_conservative_when_same_bar_hits_target_and_stop():
    decision = _decide_outcome_from_events(
        events=[
            PriceEvent(
                when=datetime(2026, 4, 22, 10, 5),
                high=111.0,
                low=94.0,
                close=101.0,
                basis="intraday_high_low",
            ),
        ],
        target_price=110.0,
        stop_price=95.0,
    )

    assert decision is not None
    assert decision.outcome == "stopped_out"
    assert decision.exit_price == 95.0
    assert "보수적으로 손절 처리" in decision.reason
