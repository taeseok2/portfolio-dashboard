"""Shared pytest fixtures."""

import os
import textwrap

import pandas as pd
import pytest


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture()
def sample_portfolio_csv(tmp_path) -> str:
    """Write a minimal portfolio.csv (with sector) and return its path."""
    content = textwrap.dedent("""\
        ticker,shares,cost_basis,sector
        AAPL,10,150.00,Technology
        MSFT,5,280.00,Technology
        NVDA,6,400.00,Technology
    """)
    p = tmp_path / "portfolio.csv"
    p.write_text(content)
    return str(p)


@pytest.fixture()
def sample_portfolio_csv_no_sector(tmp_path) -> str:
    """Write a portfolio.csv without the optional sector column."""
    content = textwrap.dedent("""\
        ticker,shares,cost_basis
        AAPL,10,150.00
        MSFT,5,280.00
    """)
    p = tmp_path / "portfolio.csv"
    p.write_text(content)
    return str(p)


@pytest.fixture()
def empty_history_dir(tmp_path) -> str:
    """Return a tmp data directory with no history.csv yet."""
    d = tmp_path / "data"
    d.mkdir()
    return str(d)


@pytest.fixture()
def history_dir_with_data(tmp_path) -> str:
    """Return a tmp data directory with one day of history already present."""
    d = tmp_path / "data"
    d.mkdir()
    df = pd.DataFrame([
        {"date": "2024-01-02", "ticker": "AAPL", "price": 185.00, "shares": 10, "market_value": 1850.00},
        {"date": "2024-01-02", "ticker": "MSFT", "price": 374.00, "shares": 5,  "market_value": 1870.00},
    ])
    df.to_csv(d / "history.csv", index=False)
    return str(d)


@pytest.fixture()
def mock_yf_ticker(mocker):
    """
    Patch yfinance.Ticker so tests never hit the network.
    Returns a factory: call mock_yf_ticker(close_prices=[...]) to customise the
    sequence of closing prices returned.
    """
    import numpy as np
    import pandas as pd

    def _factory(close_prices=None):
        if close_prices is None:
            # 35 trading-day-like prices around $200
            rng = np.random.default_rng(42)
            close_prices = (200 + rng.normal(0, 3, 35)).tolist()

        dates = pd.date_range(end="2024-02-01", periods=len(close_prices), freq="B")
        hist_df = pd.DataFrame({"Close": close_prices}, index=dates)

        mock_ticker = mocker.MagicMock()
        mock_ticker.history.return_value = hist_df
        mocker.patch("yfinance.Ticker", return_value=mock_ticker)
        return mock_ticker

    return _factory
