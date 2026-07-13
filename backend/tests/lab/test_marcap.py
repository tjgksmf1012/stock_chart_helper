from datetime import date

import pandas as pd

from app.lab.marcap import load_marcap_caps, point_in_time_universe_from_marcap


def _write_parquet(tmp_path, year: int, rows: list[tuple[str, str, float]]) -> None:
    df = pd.DataFrame(
        [{"Date": pd.Timestamp(d), "Code": c, "Marcap": m} for d, c, m in rows]
    )
    df.to_parquet(tmp_path / f"marcap-{year}.parquet")


class TestMarcapUniverse:
    def test_picks_snapshot_on_or_before_asof(self, tmp_path):
        _write_parquet(tmp_path, 2022, [
            ("2022-01-03", "000001", 100.0),
            ("2022-01-03", "000002", 300.0),
            ("2022-01-04", "000001", 100.0),  # asof 이후 → 무시돼야 함
            ("2022-01-04", "000003", 999.0),
        ])
        caps = load_marcap_caps(date(2022, 1, 3), data_dir=tmp_path)
        assert set(caps.index) == {"000001", "000002"}
        assert point_in_time_universe_from_marcap(date(2022, 1, 3), top_n=1, data_dir=tmp_path) == ["000002"]

    def test_holiday_falls_back_to_previous_trading_day(self, tmp_path):
        _write_parquet(tmp_path, 2022, [("2022-01-03", "000001", 100.0)])
        caps = load_marcap_caps(date(2022, 1, 9), data_dir=tmp_path)  # 주말 → 직전 거래일
        assert list(caps.index) == ["000001"]

    def test_year_boundary_uses_previous_year_file(self, tmp_path):
        _write_parquet(tmp_path, 2021, [("2021-12-30", "000009", 500.0)])
        # 2022 파일이 없어도 1월 초 asof는 전년 파일의 마지막 거래일로 커버
        caps = load_marcap_caps(date(2022, 1, 2), data_dir=tmp_path)
        assert list(caps.index) == ["000009"]

    def test_missing_files_returns_empty(self, tmp_path):
        assert load_marcap_caps(date(2022, 1, 3), data_dir=tmp_path).empty
        assert point_in_time_universe_from_marcap(date(2022, 1, 3), 10, data_dir=tmp_path) == []
