"""
Tests for fetch_data.py — all network calls are mocked via conftest.mock_yf_ticker.
"""

import os
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

import fetch_data as fd  # noqa: E402 — must come after sys.path patch

# ─── Helpers ─────────────────────────────────────────────────────────────────

def _run(portfolio_csv: str, data_dir: str, today_str: str, mocker):
    """Patch module-level paths + date, call main(), return the history DataFrame."""
    mocker.patch.object(fd, "PORT_FILE", portfolio_csv)
    mocker.patch.object(fd, "DATA_DIR",  data_dir)
    mocker.patch.object(fd, "HIST_FILE", os.path.join(data_dir, "history.csv"))

    class _FakeDate:
        @staticmethod
        def today():
            class _D:
                def isoformat(self):
                    return today_str
            return _D()

    mocker.patch("fetch_data.date", _FakeDate)
    fd.main()
    path = os.path.join(data_dir, "history.csv")
    if not os.path.exists(path):
        # main() writes nothing when there are no new rows — represent that
        # as an empty frame with the expected schema.
        return pd.DataFrame(columns=["date", "ticker", "price", "shares", "market_value"])
    return pd.read_csv(path)


# ─── Tests ───────────────────────────────────────────────────────────────────

class TestFetchDataMain:
    def test_creates_history_csv_when_missing(
        self, sample_portfolio_csv, empty_history_dir, mock_yf_ticker, mocker
    ):
        """First run: no history.csv → file is created with one row per ticker."""
        mock_yf_ticker()
        df = _run(sample_portfolio_csv, empty_history_dir, "2024-03-01", mocker)

        assert os.path.exists(os.path.join(empty_history_dir, "history.csv"))
        assert len(df) == 3  # AAPL, MSFT, NVDA
        assert set(df["ticker"]) == {"AAPL", "MSFT", "NVDA"}

    def test_required_columns_present(
        self, sample_portfolio_csv, empty_history_dir, mock_yf_ticker, mocker
    ):
        mock_yf_ticker()
        df = _run(sample_portfolio_csv, empty_history_dir, "2024-03-02", mocker)

        for col in ("date", "ticker", "price", "shares", "market_value"):
            assert col in df.columns, f"Missing column: {col}"

    def test_market_value_equals_price_times_shares(
        self, sample_portfolio_csv, empty_history_dir, mock_yf_ticker, mocker
    ):
        """market_value must equal price × shares (rounded to 2 dp)."""
        mock_yf_ticker(close_prices=[200.0] * 35)
        df = _run(sample_portfolio_csv, empty_history_dir, "2024-03-03", mocker)

        for _, row in df.iterrows():
            expected = round(row["price"] * row["shares"], 2)
            assert abs(row["market_value"] - expected) < 0.01

    def test_skips_duplicate_ticker_on_same_date(
        self, sample_portfolio_csv, history_dir_with_data, mock_yf_ticker, mocker
    ):
        """Running twice on the same date must not create duplicate rows."""
        mock_yf_ticker()
        _run(sample_portfolio_csv, history_dir_with_data, "2024-03-04", mocker)
        df1 = pd.read_csv(os.path.join(history_dir_with_data, "history.csv"))
        count_first = len(df1[df1["date"] == "2024-03-04"])

        # Second run — should be a no-op for those tickers
        mocker.patch.object(fd, "PORT_FILE", sample_portfolio_csv)
        mocker.patch.object(fd, "DATA_DIR",  history_dir_with_data)
        mocker.patch.object(fd, "HIST_FILE", os.path.join(history_dir_with_data, "history.csv"))

        class _FakeDate2:
            @staticmethod
            def today():
                class _D:
                    def isoformat(self):
                        return "2024-03-04"
                return _D()

        mocker.patch("fetch_data.date", _FakeDate2)
        fd.main()

        df2 = pd.read_csv(os.path.join(history_dir_with_data, "history.csv"))
        count_second = len(df2[df2["date"] == "2024-03-04"])
        assert count_second == count_first

    def test_appends_preserves_prior_rows(
        self, sample_portfolio_csv, history_dir_with_data, mock_yf_ticker, mocker
    ):
        """Existing rows from a prior date must survive the append."""
        mock_yf_ticker()
        df = _run(sample_portfolio_csv, history_dir_with_data, "2024-03-05", mocker)

        # 2 original rows + 3 new rows
        assert len(df) == 5
        assert "2024-01-02" in df["date"].values

    def test_graceful_skip_on_empty_yf_response(
        self, sample_portfolio_csv, empty_history_dir, mocker
    ):
        """If yfinance returns an empty DataFrame, the ticker is skipped cleanly."""
        empty_mock = mocker.MagicMock()
        empty_mock.history.return_value = pd.DataFrame()
        mocker.patch("yfinance.Ticker", return_value=empty_mock)

        df = _run(sample_portfolio_csv, empty_history_dir, "2024-03-06", mocker)
        assert len(df[df["date"] == "2024-03-06"]) == 0

    def test_price_rounded_to_4dp(
        self, sample_portfolio_csv, empty_history_dir, mock_yf_ticker, mocker
    ):
        """Prices must be stored with at most 4 decimal places."""
        mock_yf_ticker(close_prices=[123.456789] * 35)
        df = _run(sample_portfolio_csv, empty_history_dir, "2024-03-07", mocker)

        for price in df["price"]:
            assert price == round(price, 4)


class TestPortfolioCSV:
    def test_required_columns(self, sample_portfolio_csv):
        df = pd.read_csv(sample_portfolio_csv)
        assert {"ticker", "shares", "cost_basis"} <= set(df.columns)

    def test_no_null_values(self, sample_portfolio_csv):
        df = pd.read_csv(sample_portfolio_csv)
        assert not df[["ticker", "shares", "cost_basis"]].isnull().any().any()

    def test_positive_shares_and_cost(self, sample_portfolio_csv):
        df = pd.read_csv(sample_portfolio_csv)
        assert (df["shares"] > 0).all()
        assert (df["cost_basis"] > 0).all()
