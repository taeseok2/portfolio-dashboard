"""
Tests for the pure-Python calculation logic that lives in app.py.
We extract the maths into standalone functions here so tests don't need
to boot Streamlit.
"""

import numpy as np
import pandas as pd
import pytest


# ─── Replicate the calculation logic from app.py ─────────────────────────────
# (These helpers mirror what app.py does so we can test them in isolation.)

def compute_gain(price: float, shares: float, cost_basis: float):
    mkt_val  = price * shares
    cost_val = cost_basis * shares
    gain     = mkt_val - cost_val
    gain_pct = (gain / cost_val * 100) if cost_val else 0
    return mkt_val, cost_val, gain, gain_pct


def compute_moving_averages(close_prices: list[float]):
    s = pd.Series(close_prices)
    ma7  = float(s.tail(7).mean())  if len(s) >= 7  else float(s.iloc[-1])
    ma30 = float(s.tail(30).mean()) if len(s) >= 30 else float(s.iloc[-1])
    return ma7, ma30


def compute_annualised_vol(close_prices: list[float]) -> float:
    s       = pd.Series(close_prices)
    returns = s.pct_change().dropna()
    if len(returns) < 5:
        return 0.0
    return float(returns.tail(21).std() * np.sqrt(252) * 100)


def compute_day_change_pct(close_prices: list[float]) -> float:
    if len(close_prices) < 2:
        return 0.0
    prev  = close_prices[-2]
    price = close_prices[-1]
    return (price - prev) / prev * 100 if prev else 0.0


# ─── Tests ───────────────────────────────────────────────────────────────────

class TestGainLoss:
    def test_gain_positive_when_price_above_cost(self):
        _, _, gain, gain_pct = compute_gain(200.0, 10, 150.0)
        assert gain == pytest.approx(500.0)
        assert gain_pct == pytest.approx(33.333, rel=1e-3)

    def test_gain_negative_when_price_below_cost(self):
        _, _, gain, gain_pct = compute_gain(100.0, 5, 120.0)
        assert gain == pytest.approx(-100.0)
        assert gain_pct < 0

    def test_zero_gain_at_cost_basis(self):
        _, _, gain, gain_pct = compute_gain(150.0, 10, 150.0)
        assert gain == pytest.approx(0.0)
        assert gain_pct == pytest.approx(0.0)

    def test_market_value_formula(self):
        mkt_val, _, _, _ = compute_gain(250.0, 4, 200.0)
        assert mkt_val == pytest.approx(1000.0)

    def test_zero_cost_basis_does_not_raise(self):
        _, _, _, gain_pct = compute_gain(100.0, 1, 0.0)
        assert gain_pct == 0.0


class TestMovingAverages:
    def test_ma7_uses_last_7_prices(self):
        prices = list(range(1, 36))   # 1..35
        ma7, _ = compute_moving_averages(prices)
        assert ma7 == pytest.approx(np.mean(prices[-7:]))

    def test_ma30_uses_last_30_prices(self):
        prices = list(range(1, 36))
        _, ma30 = compute_moving_averages(prices)
        assert ma30 == pytest.approx(np.mean(prices[-30:]))

    def test_ma_fallback_when_fewer_than_7(self):
        prices = [10.0, 11.0, 12.0]
        ma7, ma30 = compute_moving_averages(prices)
        # fewer than 7 → last price
        assert ma7 == pytest.approx(prices[-1])
        assert ma30 == pytest.approx(prices[-1])

    def test_ma7_lt_ma30_in_uptrend(self):
        # Prices rising: recent avg > historical avg
        prices = list(range(100, 135))   # 100,101,...,134
        ma7, ma30 = compute_moving_averages(prices)
        assert ma7 > ma30


class TestVolatility:
    def test_returns_zero_with_fewer_than_5_returns(self):
        assert compute_annualised_vol([100, 101, 102, 103]) == 0.0

    def test_higher_vol_for_noisy_series(self):
        rng = np.random.default_rng(0)
        flat   = [100.0] * 35
        noisy  = (100 + rng.normal(0, 5, 35)).tolist()
        assert compute_annualised_vol(noisy) > compute_annualised_vol(flat)

    def test_constant_prices_give_zero_vol(self):
        assert compute_annualised_vol([150.0] * 35) == pytest.approx(0.0, abs=1e-10)

    def test_vol_is_non_negative(self):
        prices = [100 + i * 0.5 for i in range(35)]
        assert compute_annualised_vol(prices) >= 0.0


class TestDayChange:
    def test_positive_day_change(self):
        assert compute_day_change_pct([100.0, 105.0]) == pytest.approx(5.0)

    def test_negative_day_change(self):
        assert compute_day_change_pct([200.0, 190.0]) == pytest.approx(-5.0)

    def test_zero_change(self):
        assert compute_day_change_pct([100.0, 100.0]) == pytest.approx(0.0)

    def test_single_price_returns_zero(self):
        assert compute_day_change_pct([100.0]) == 0.0

    def test_zero_prev_price_does_not_raise(self):
        result = compute_day_change_pct([0.0, 10.0])
        assert result == 0.0


class TestPortfolioAggregation:
    def test_total_value_sums_market_values(self):
        positions = pd.DataFrame([
            {"MktValue": 1000.0},
            {"MktValue": 2500.0},
            {"MktValue":  750.0},
        ])
        assert positions["MktValue"].sum() == pytest.approx(4250.0)

    def test_total_gain_pct(self):
        total_value = 11000.0
        total_cost  = 10000.0
        gain_pct = (total_value - total_cost) / total_cost * 100
        assert gain_pct == pytest.approx(10.0)

    def test_allocation_weights_sum_to_100(self):
        positions = pd.DataFrame([
            {"Ticker": "AAPL", "MktValue": 3000.0},
            {"Ticker": "MSFT", "MktValue": 2000.0},
            {"Ticker": "NVDA", "MktValue": 5000.0},
        ])
        total = positions["MktValue"].sum()
        weights = positions["MktValue"] / total * 100
        assert weights.sum() == pytest.approx(100.0)

    def test_weight_series_used_for_risk_calc(self):
        """weights.reindex(returns_df.columns) must stay normalised after fillna."""
        positions = pd.DataFrame([
            {"Ticker": "AAPL", "MktValue": 6000.0},
            {"Ticker": "MSFT", "MktValue": 4000.0},
        ])
        total   = positions["MktValue"].sum()
        weights = positions.set_index("Ticker")["MktValue"] / total
        # Reindex to columns present in a hypothetical returns_df
        w = weights.reindex(["AAPL", "MSFT"]).fillna(0)
        w = w / w.sum()
        assert w.sum() == pytest.approx(1.0)
        assert w["AAPL"] == pytest.approx(0.6)
