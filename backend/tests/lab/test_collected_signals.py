import json

from app.services.collected_signals import merge_signal_records, parse_collected_records, record_key


def _rec(strategy: str, code: str, day: str, **overrides) -> dict:
    return {
        "strategy_id": strategy, "strategy_label": "라벨", "verdict": "pass",
        "code": code, "signal_date": day, "reference_price": 100.0,
        "stop_price": 90.0, "target_price": None, "max_holding_days": 21,
        "collected_at": "2026-07-18T16:35:00",
        **overrides,
    }


class TestRecordKey:
    def test_key_is_strategy_code_date(self):
        assert record_key(_rec("s1", "005930", "2026-07-18")) == ("s1", "005930", "2026-07-18")


class TestMergeSignalRecords:
    def test_appends_new_records_as_json_lines(self):
        lines, added = merge_signal_records([], [_rec("s1", "A", "2026-07-18")])
        assert added == 1
        assert json.loads(lines[0])["code"] == "A"

    def test_skips_records_already_present(self):
        existing = [json.dumps(_rec("s1", "A", "2026-07-18"), ensure_ascii=False)]
        lines, added = merge_signal_records(existing, [_rec("s1", "A", "2026-07-18"), _rec("s1", "B", "2026-07-18")])
        assert added == 1
        assert len(lines) == 2
        assert json.loads(lines[1])["code"] == "B"

    def test_preserves_existing_order_and_content(self):
        existing = [
            json.dumps(_rec("s1", "A", "2026-07-01"), ensure_ascii=False),
            json.dumps(_rec("s2", "B", "2026-07-02"), ensure_ascii=False),
        ]
        lines, added = merge_signal_records(existing, [])
        assert added == 0
        assert lines == existing


class TestParseCollectedRecords:
    def test_parses_valid_lines(self):
        text = "\n".join([
            json.dumps(_rec("s1", "A", "2026-07-18"), ensure_ascii=False),
            json.dumps(_rec("s2", "B", "2026-07-17"), ensure_ascii=False),
        ])
        records = parse_collected_records(text)
        assert [r["code"] for r in records] == ["A", "B"]

    def test_skips_malformed_and_incomplete_lines(self):
        text = "\n".join([
            "not-json{{{",
            json.dumps({"strategy_id": "s1", "code": "A"}),  # 필수 키(signal_date 등) 누락
            json.dumps(_rec("s1", "OK", "2026-07-18"), ensure_ascii=False),
            "",
        ])
        records = parse_collected_records(text)
        assert [r["code"] for r in records] == ["OK"]

    def test_empty_text(self):
        assert parse_collected_records("") == []
        assert parse_collected_records("\n\n") == []


class TestSyncPlumbing:
    """네트워크 없이 동기화 배선을 검증 — settings import 오타 같은 배선 버그를 잡는다."""

    def test_sync_url_reads_settings(self):
        from app.api.routes.lab import _collected_signals_url

        url = _collected_signals_url()
        assert isinstance(url, str)
        assert url == "" or url.startswith("https://")

    def test_sync_disabled_when_url_empty(self):
        import asyncio

        from app.api.routes.lab import sync_collected_signals

        assert asyncio.run(sync_collected_signals(url="")) == 0
