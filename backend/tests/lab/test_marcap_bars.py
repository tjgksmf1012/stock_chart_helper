from datetime import date

import pandas as pd

from app.lab.marcap_bars import adjust_for_splits, load_marcap_bars, merge_bars_with_fallback


def _df(closes, stocks):
    n = len(closes)
    return pd.DataFrame({
        "date": pd.date_range("2024-01-01", periods=n).date,
        "open": closes, "high": [c * 1.01 for c in closes],
        "low": [c * 0.99 for c in closes], "close": closes,
        "volume": [1000] * n, "stocks": stocks,
    })


class TestAdjustForSplits:
    def test_split_1_to_2_backadjusts_earlier_prices(self):
        # 3일째 1:2 분할 — 주식수 2배, 가격 절반. 보정 후 시계열이 연속이어야 한다.
        df = _df([10000, 10000, 5000, 5000], [100, 100, 200, 200])
        out = adjust_for_splits(df)
        assert out["close"].tolist() == [5000.0, 5000.0, 5000.0, 5000.0]
        assert out["open"].tolist()[0] == 5000.0  # 가격 4종 모두 보정

    def test_no_change_returns_same_prices(self):
        df = _df([10000, 10100], [100, 100])
        assert adjust_for_splits(df)["close"].tolist() == [10000, 10100]

    def test_small_share_change_ignored(self):
        # 자사주 소각 등 5% 미만 변동은 분할이 아니다 — 보정하지 않는다
        df = _df([10000, 10000], [100, 102])
        assert adjust_for_splits(df)["close"].tolist() == [10000, 10000]

    def test_volume_inversely_adjusted_on_split(self):
        df = _df([10000, 5000], [100, 200])
        out = adjust_for_splits(df)
        assert out["volume"].tolist() == [2000.0, 1000]


class TestLoadMarcapBars:
    def _write_parquet(self, tmp_path, year, rows):
        df = pd.DataFrame(rows)
        df.to_parquet(tmp_path / f"marcap-{year}.parquet")

    def test_loads_code_across_years_sorted(self, tmp_path):
        self._write_parquet(tmp_path, 2023, {
            "Date": ["2023-12-28"], "Code": ["005930"], "Open": [100.0], "High": [101.0],
            "Low": [99.0], "Close": [100.0], "Volume": [10], "Stocks": [50],
        })
        self._write_parquet(tmp_path, 2024, {
            "Date": ["2024-01-02", "2024-01-03"], "Code": ["005930", "999999"],
            "Open": [102.0, 1.0], "High": [103.0, 1.0], "Low": [101.0, 1.0],
            "Close": [102.0, 1.0], "Volume": [11, 1], "Stocks": [50, 1],
        })
        bars = load_marcap_bars("005930", data_dir=tmp_path)
        assert bars["date"].tolist() == [date(2023, 12, 28), date(2024, 1, 2)]
        assert list(bars.columns) == ["date", "open", "high", "low", "close", "volume"]

    def test_zero_price_rows_dropped(self, tmp_path):
        self._write_parquet(tmp_path, 2024, {
            "Date": ["2024-01-02", "2024-01-03"], "Code": ["000001", "000001"],
            "Open": [0.0, 100.0], "High": [0.0, 101.0], "Low": [0.0, 99.0],
            "Close": [0.0, 100.0], "Volume": [0, 5], "Stocks": [10, 10],
        })
        bars = load_marcap_bars("000001", data_dir=tmp_path)
        assert len(bars) == 1

    def test_missing_code_returns_none(self, tmp_path):
        self._write_parquet(tmp_path, 2024, {
            "Date": ["2024-01-02"], "Code": ["005930"], "Open": [1.0], "High": [1.0],
            "Low": [1.0], "Close": [1.0], "Volume": [1], "Stocks": [1],
        })
        assert load_marcap_bars("999999", data_dir=tmp_path) is None


class TestMergeWithFallback:
    def test_fallback_fills_missing_codes_only(self):
        fetched = {"A": _df([1] * 200, [1] * 200)}

        def loader(code):
            return _df([2] * 200, [1] * 200) if code == "B" else None

        merged, n_fallback = merge_bars_with_fallback(fetched, ["A", "B", "C"], loader, min_bars=150)
        assert set(merged) == {"A", "B"} and n_fallback == 1
        assert merged["A"]["close"].iloc[0] == 1  # 원본 우선

    def test_short_fallback_rejected(self):
        merged, n = merge_bars_with_fallback({}, ["B"], lambda c: _df([2] * 10, [1] * 10), min_bars=150)
        assert merged == {} and n == 0

    def test_loader_exception_skipped(self):
        def boom(code):
            raise RuntimeError("read error")

        merged, n = merge_bars_with_fallback({}, ["B"], boom, min_bars=150)
        assert merged == {} and n == 0
