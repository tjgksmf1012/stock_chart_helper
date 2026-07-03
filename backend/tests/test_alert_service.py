"""관심종목 알림 레벨 판정(_evaluate_levels) 테스트."""
from __future__ import annotations

from app.services.alert_service import _evaluate_levels


def _kinds(alerts: list[dict]) -> list[str]:
    return [a["kind"] for a in alerts]


class TestBullish:
    """상방 패턴 (이중 바닥 등): 위로 돌파/익절, 아래로 손절."""

    def test_no_alert_inside_range(self):
        alerts = _evaluate_levels("double_bottom", neckline=10_000, invalidation=9_000, target=11_000, price=9_500)
        assert alerts == []

    def test_trigger_on_neckline_touch(self):
        alerts = _evaluate_levels("double_bottom", neckline=10_000, invalidation=9_000, target=11_000, price=10_050)
        assert _kinds(alerts) == ["trigger"]

    def test_target_supersedes_trigger(self):
        # 목표 도달 시 돌파선 알림은 중복이므로 목표만
        alerts = _evaluate_levels("double_bottom", neckline=10_000, invalidation=9_000, target=11_000, price=11_200)
        assert _kinds(alerts) == ["target"]

    def test_stop_breach(self):
        alerts = _evaluate_levels("double_bottom", neckline=10_000, invalidation=9_000, target=11_000, price=8_900)
        assert _kinds(alerts) == ["stop"]


class TestBearish:
    """하방 패턴 (이중 천장 등): 아래로 이탈/익절, 위로 손절."""

    def test_trigger_on_breakdown(self):
        alerts = _evaluate_levels("double_top", neckline=10_000, invalidation=11_000, target=9_000, price=9_950)
        assert _kinds(alerts) == ["trigger"]

    def test_target_on_deep_fall(self):
        alerts = _evaluate_levels("double_top", neckline=10_000, invalidation=11_000, target=9_000, price=8_800)
        assert _kinds(alerts) == ["target"]

    def test_stop_on_rally(self):
        alerts = _evaluate_levels("double_top", neckline=10_000, invalidation=11_000, target=9_000, price=11_100)
        assert _kinds(alerts) == ["stop"]


class TestDirectionNeutralPatterns:
    """Regression: rectangle/symmetric_triangle/channels are direction-neutral TYPES --
    the same type can break out bullish or bearish depending on the specific instance.
    _evaluate_levels used to call the old _is_bullish(pattern_type), which always
    returned False for these types regardless of actual direction, silently flipping
    alert direction (e.g. reporting a "stop breach" for what was actually a bullish
    target hit).
    """

    def test_rectangle_bullish_instance_uses_bullish_levels(self):
        # target above neckline -> this instance broke out upward.
        alerts = _evaluate_levels("rectangle", neckline=10_000, invalidation=9_000, target=11_000, price=11_200)
        assert _kinds(alerts) == ["target"]

    def test_rectangle_bearish_instance_uses_bearish_levels(self):
        # target below neckline -> this instance broke down.
        alerts = _evaluate_levels("rectangle", neckline=10_000, invalidation=11_000, target=9_000, price=8_800)
        assert _kinds(alerts) == ["target"]

    def test_rectangle_bearish_instance_stop_is_above(self):
        alerts = _evaluate_levels("rectangle", neckline=10_000, invalidation=11_000, target=9_000, price=11_100)
        assert _kinds(alerts) == ["stop"]


class TestEdgeCases:
    def test_no_pattern(self):
        assert _evaluate_levels(None, neckline=10_000, invalidation=9_000, target=11_000, price=10_500) == []

    def test_missing_levels_skipped(self):
        alerts = _evaluate_levels("double_bottom", neckline=None, invalidation=None, target=None, price=10_500)
        assert alerts == []

    def test_invalid_price(self):
        assert _evaluate_levels("double_bottom", neckline=10_000, invalidation=9_000, target=11_000, price=0) == []
