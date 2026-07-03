"""Regression tests for personalization_service.py's thin-sample overconfidence fix.

_pick_top_bucket() used to rank purely by raw win_rate with min_total=1, so a single
lucky trade (1/1 = 100%) would outrank a well-established pattern (e.g. 16/20 = 80%)
as "your best pattern" -- then get a +5 point bonus applied to every future
recommendation via score_personal_fit(). The fix uses a Bayesian-shrunk win rate for
ranking (pulls thin samples toward neutral) and raises the eligibility floor.
"""

from __future__ import annotations

from app.services.personalization_service import _pick_top_bucket, _shrunk_win_rate


def _bucket(wins: int, total: int) -> dict:
    return {"wins": wins, "total": total, "win_rate": round(wins / total, 3)}


class TestShrunkWinRate:
    def test_small_sample_is_pulled_toward_neutral(self):
        # 1/1 = 100% raw, but shrunk toward 0.5 given almost no evidence.
        assert _shrunk_win_rate(1, 1) < 0.7

    def test_large_sample_stays_close_to_raw_rate(self):
        assert abs(_shrunk_win_rate(16, 20) - 0.8) < 0.06

    def test_more_samples_at_same_rate_increases_confidence(self):
        small = _shrunk_win_rate(1, 1)
        large = _shrunk_win_rate(20, 20)
        assert large > small


class TestPickTopBucketDoesNotOverweightThinSamples:
    def test_one_lucky_trade_does_not_beat_a_well_established_pattern(self):
        buckets = {
            "cup_and_handle": _bucket(wins=1, total=1),  # 100% off a single trade
            "double_bottom": _bucket(wins=16, total=20),  # 80% off 20 trades
        }
        key, _ = _pick_top_bucket(buckets)
        assert key == "double_bottom"

    def test_genuinely_best_pattern_with_enough_samples_still_wins(self):
        buckets = {
            "cup_and_handle": _bucket(wins=9, total=10),  # 90% off 10 trades
            "double_bottom": _bucket(wins=12, total=20),  # 60% off 20 trades
        }
        key, _ = _pick_top_bucket(buckets)
        assert key == "cup_and_handle"

    def test_falls_back_to_all_buckets_when_nothing_meets_the_floor(self):
        # A brand-new user with only 1-2 trades in any bucket -- must not return None.
        buckets = {"double_bottom": _bucket(wins=1, total=1)}
        key, value = _pick_top_bucket(buckets)
        assert key == "double_bottom"
        assert value is not None

    def test_empty_buckets_returns_none(self):
        assert _pick_top_bucket({}) == (None, None)
