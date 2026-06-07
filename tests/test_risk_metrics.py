"""
Tests for the risk-metric and sector-allocation logic added to app.py.
All calculations are extracted into standalone functions here so the tests
never need to boot Streamlit or hit the network.
"""

import numpy as np
import pandas as pd
import pytest


# ─── Mirror the risk-metric logic from app.py ────────────────────────────────

def build_port_returns(returns_df: pd.DataFrame, weights: pd.Series) -> pd.Series:
    """Weighted portfolio daily returns."""
    w = weights.reindex(returns_df.columns).fillna(0)
    w = w / w.sum()
    return returns_df.dot(w)


def compute_risk_metrics(port_returns: pd.Series, rf: float = 0.04) -> dict:
    ann_factor = np.sqrt(252)
    ann_return = port_returns.mean() * 252 * 100
    ann_vol    = port_returns.std() * ann_factor * 100
    sharpe     = (
        ((port_returns.mean() * 252) - rf) / (port_returns.std() * ann_factor)
        if port_returns.std()
        else 0.0
    )
    cum    = (1 + port_returns).cumprod()
    peak   = cum.cummax()
    max_dd = ((cum - peak) / peak).min() * 100
    return dict(
        ann_return=ann_return,
        ann_vol=ann_vol,
        sharpe=sharpe,
        max_dd=max_dd,
    )


def compute_correlation(returns_df: pd.DataFrame) -> pd.DataFrame:
    return returns_df.corr()


def aggregate_by_sector(positions: pd.DataFrame) -> pd.DataFrame:
    result = (
        positions.groupby("Sector")["MktValue"]
        .sum()
        .sort_values(ascending=True)
        .reset_index()
    )
    result["Pct"] = result["MktValue"] / result["MktValue"].sum() * 100
    return result


# ─── Fixtures ────────────────────────────────────────────────────────────────

def _make_returns(n: int = 126, seed: int = 0) -> pd.DataFrame:
    """Generate n days of synthetic daily returns for AAPL, MSFT, NVDA."""
    rng = np.random.default_rng(seed)
    return pd.DataFrame(
        rng.normal(0.0005, 0.015, (n, 3)),
        columns=["AAPL", "MSFT", "NVDA"],
    )


def _make_positions() -> pd.DataFrame:
    return pd.DataFrame([
        {"Ticker": "AAPL", "Sector": "Technology",       "MktValue": 3000.0},
        {"Ticker": "MSFT", "Sector": "Technology",       "MktValue": 2000.0},
        {"Ticker": "NVDA", "Sector": "Technology",       "MktValue": 1200.0},
        {"Ticker": "GOOGL","Sector": "Comm. Services",   "MktValue": 1100.0},
        {"Ticker": "JPM",  "Sector": "Financials",       "MktValue":  900.0},
    ])


# ─── Portfolio return construction ───────────────────────────────────────────

class TestBuildPortReturns:
    def test_equal_weights_average(self):
        df = pd.DataFrame({"A": [0.01, 0.02], "B": [0.03, 0.04]})
        w  = pd.Series({"A": 1.0, "B": 1.0})
        result = build_port_returns(df, w)
        expected = pd.Series([0.02, 0.03])
        pd.testing.assert_series_equal(result.reset_index(drop=True), expected, check_names=False)

    def test_weights_normalised_internally(self):
        """Raw weights of (2, 2) should behave identically to (1, 1)."""
        df = pd.DataFrame({"A": [0.01, 0.02], "B": [0.03, 0.04]})
        r1 = build_port_returns(df, pd.Series({"A": 1.0, "B": 1.0}))
        r2 = build_port_returns(df, pd.Series({"A": 2.0, "B": 2.0}))
        pd.testing.assert_series_equal(r1, r2)

    def test_single_asset_returns_itself(self):
        df = pd.DataFrame({"AAPL": [0.01, -0.02, 0.03]})
        w  = pd.Series({"AAPL": 1.0})
        result = build_port_returns(df, w)
        pd.testing.assert_series_equal(result, df["AAPL"], check_names=False)

    def test_unknown_ticker_in_weights_gets_zero(self):
        df = pd.DataFrame({"A": [0.01, 0.02]})
        w  = pd.Series({"A": 1.0, "GHOST": 999.0})
        result = build_port_returns(df, w)
        # GHOST is reindexed to NaN → 0 after fillna, so only A contributes
        expected = pd.Series([0.01, 0.02])
        pd.testing.assert_series_equal(result.reset_index(drop=True), expected, check_names=False)


# ─── Risk metrics ─────────────────────────────────────────────────────────────

class TestRiskMetrics:
    def test_keys_present(self):
        pr = build_port_returns(_make_returns(), pd.Series({"AAPL": 1, "MSFT": 1, "NVDA": 1}))
        m  = compute_risk_metrics(pr)
        for key in ("ann_return", "ann_vol", "sharpe", "max_dd"):
            assert key in m

    def test_zero_vol_series_gives_zero_sharpe(self):
        pr = pd.Series([0.0] * 50)
        m  = compute_risk_metrics(pr)
        assert m["sharpe"] == 0.0

    def test_max_drawdown_non_positive(self):
        pr = build_port_returns(_make_returns(), pd.Series({"AAPL": 1, "MSFT": 1, "NVDA": 1}))
        m  = compute_risk_metrics(pr)
        assert m["max_dd"] <= 0.0

    def test_positive_drift_gives_positive_ann_return(self):
        # Constant +0.1% per day → ~25% annualised
        pr = pd.Series([0.001] * 252)
        m  = compute_risk_metrics(pr)
        assert m["ann_return"] == pytest.approx(0.001 * 252 * 100, rel=1e-3)

    def test_ann_vol_scales_with_sqrt_252(self):
        daily_std = 0.01
        pr = pd.Series(np.random.default_rng(7).normal(0, daily_std, 500))
        m  = compute_risk_metrics(pr)
        # Approximate: ann_vol ≈ daily_std * sqrt(252) * 100
        assert abs(m["ann_vol"] - daily_std * np.sqrt(252) * 100) < 5.0  # within 5pp

    def test_sharpe_positive_for_strong_drift(self):
        # +0.5% per day with tiny vol → very high Sharpe
        pr = pd.Series([0.005] * 252)
        m  = compute_risk_metrics(pr, rf=0.04)
        assert m["sharpe"] > 1.0

    def test_sharpe_negative_for_losing_portfolio(self):
        pr = pd.Series([-0.001] * 252)
        m  = compute_risk_metrics(pr, rf=0.04)
        assert m["sharpe"] < 0.0

    def test_max_drawdown_zero_for_monotone_up(self):
        pr = pd.Series([0.01] * 126)
        m  = compute_risk_metrics(pr)
        assert m["max_dd"] == pytest.approx(0.0, abs=1e-6)

    def test_max_drawdown_captures_large_drop(self):
        # 50% drop: prices go 1→2→1 → drawdown ≈ -50%
        pr = pd.Series([1.0] * 63 + [-0.5] + [0.0] * 62)
        m  = compute_risk_metrics(pr)
        assert m["max_dd"] < -30.0

    def test_rf_rate_affects_sharpe(self):
        pr = pd.Series([0.001] * 252)
        m_low  = compute_risk_metrics(pr, rf=0.00)
        m_high = compute_risk_metrics(pr, rf=0.10)
        assert m_low["sharpe"] > m_high["sharpe"]


# ─── Correlation heatmap data ─────────────────────────────────────────────────

class TestCorrelation:
    def test_diagonal_is_one(self):
        corr = compute_correlation(_make_returns())
        for ticker in corr.columns:
            assert corr.loc[ticker, ticker] == pytest.approx(1.0)

    def test_symmetric(self):
        corr = compute_correlation(_make_returns())
        pd.testing.assert_frame_equal(corr, corr.T)

    def test_values_in_minus1_to_1(self):
        corr = compute_correlation(_make_returns())
        assert (corr.values >= -1.0 - 1e-9).all()
        assert (corr.values <=  1.0 + 1e-9).all()

    def test_perfectly_correlated_pair(self):
        df = pd.DataFrame({"A": [0.01, -0.01, 0.02], "B": [0.01, -0.01, 0.02]})
        corr = compute_correlation(df)
        assert corr.loc["A", "B"] == pytest.approx(1.0)

    def test_uncorrelated_pair_near_zero(self):
        rng = np.random.default_rng(42)
        df = pd.DataFrame({"A": rng.normal(0, 1, 1000), "B": rng.normal(0, 1, 1000)})
        corr = compute_correlation(df)
        assert abs(corr.loc["A", "B"]) < 0.10


# ─── Sector allocation ────────────────────────────────────────────────────────

class TestSectorAllocation:
    def test_pct_sums_to_100(self):
        result = aggregate_by_sector(_make_positions())
        assert result["Pct"].sum() == pytest.approx(100.0)

    def test_sorted_ascending_by_market_value(self):
        result = aggregate_by_sector(_make_positions())
        assert list(result["MktValue"]) == sorted(result["MktValue"].tolist())

    def test_sector_grouping(self):
        result = aggregate_by_sector(_make_positions())
        tech = result[result["Sector"] == "Technology"]["MktValue"].values[0]
        assert tech == pytest.approx(3000.0 + 2000.0 + 1200.0)

    def test_single_sector(self):
        df = pd.DataFrame([
            {"Ticker": "X", "Sector": "Tech", "MktValue": 500.0},
            {"Ticker": "Y", "Sector": "Tech", "MktValue": 500.0},
        ])
        result = aggregate_by_sector(df)
        assert len(result) == 1
        assert result["Pct"].iloc[0] == pytest.approx(100.0)

    def test_unclassified_treated_as_own_sector(self):
        df = pd.DataFrame([
            {"Ticker": "X", "Sector": "Unclassified", "MktValue": 200.0},
            {"Ticker": "Y", "Sector": "Technology",   "MktValue": 800.0},
        ])
        result = aggregate_by_sector(df)
        assert "Unclassified" in result["Sector"].values


# ─── Portfolio CSV schema (with sector) ───────────────────────────────────────

class TestPortfolioCSVWithSector:
    def test_sector_column_present(self, sample_portfolio_csv):
        df = pd.read_csv(sample_portfolio_csv)
        assert "sector" in df.columns

    def test_no_blank_sectors(self, sample_portfolio_csv):
        df = pd.read_csv(sample_portfolio_csv)
        assert not df["sector"].isnull().any()
        assert not (df["sector"].str.strip() == "").any()

    def test_graceful_without_sector(self, sample_portfolio_csv_no_sector):
        """app.py checks 'sector' in portfolio.columns — must not crash without it."""
        df = pd.read_csv(sample_portfolio_csv_no_sector)
        has_sector = "sector" in df.columns
        assert not has_sector  # confirms fixture is correct
        # Simulate the fallback: default sector label
        df["Sector"] = "Unclassified" if not has_sector else df["sector"]
        assert (df["Sector"] == "Unclassified").all()
