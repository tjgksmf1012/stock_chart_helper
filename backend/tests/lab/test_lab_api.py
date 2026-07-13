import json
from pathlib import Path

from app.api.routes.lab import load_latest_reports


def _write(dirpath: Path, name: str, payload: dict) -> None:
    (dirpath / name).write_text(json.dumps(payload), encoding="utf-8")


class TestLoadLatestReports:
    def test_latest_per_strategy_and_verdict_order(self, tmp_path):
        _write(tmp_path, "a_old.json", {"strategy": "a", "generated_at": "2026-07-12T01:00", "verdict": "watch", "ev_pct": 0.01})
        _write(tmp_path, "a_new.json", {"strategy": "a", "generated_at": "2026-07-13T01:00", "verdict": "fail", "ev_pct": -0.001})
        _write(tmp_path, "b.json", {"strategy": "b", "generated_at": "2026-07-13T02:00", "verdict": "pass", "ev_pct": 0.05})
        reports = load_latest_reports(tmp_path)
        assert [r["strategy"] for r in reports] == ["b", "a"]  # pass 먼저, 전략별 최신본만
        assert reports[1]["verdict"] == "fail"

    def test_broken_file_is_skipped(self, tmp_path):
        (tmp_path / "broken.json").write_text("{not json", encoding="utf-8")
        _write(tmp_path, "ok.json", {"strategy": "x", "generated_at": "1", "verdict": "pass", "ev_pct": 0.01})
        assert [r["strategy"] for r in load_latest_reports(tmp_path)] == ["x"]

    def test_missing_dir(self, tmp_path):
        assert load_latest_reports(tmp_path / "nope") == []
