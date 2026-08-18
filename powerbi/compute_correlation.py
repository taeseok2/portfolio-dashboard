"""
compute_correlation.py

Run this alongside fetch_data.py (e.g. as an extra step in the same
GitHub Actions cron, right after the daily price fetch) to produce a
ticker-by-ticker correlation matrix. Power BI imports the output
directly and renders it as a heatmap Matrix visual with conditional
formatting -- no DAX statistics required.

Usage:
    python compute_correlation.py

Reads:   data/history.csv          (date, ticker, price, shares, market_value)
Writes:  data/correlation_matrix.csv (ticker_a, ticker_b, correlation)
"""

import pandas as pd

LOOKBACK_DAYS = 90


def compute_correlation_matrix(
    history_path: str = "data/history.csv",
    output_path: str = "data/correlation_matrix.csv",
    lookback_days: int = LOOKBACK_DAYS,
) -> None:
    history = pd.read_csv(history_path, parse_dates=["date"])
    history = history.sort_values("date")

    cutoff = history["date"].max() - pd.Timedelta(days=lookback_days)
    recent = history[history["date"] >= cutoff]

    # Wide format: one column per ticker, one row per date
    wide = recent.pivot(index="date", columns="ticker", values="price")
    daily_returns = wide.pct_change().dropna(how="all")

    corr = daily_returns.corr()

    # Long format (ticker_a, ticker_b, correlation) -- easiest shape
    # for Power BI's Matrix visual + conditional formatting.
    long_corr = (
        corr.reset_index()
        .melt(id_vars="index", var_name="ticker_b", value_name="correlation")
        .rename(columns={"index": "ticker_a"})
    )
    long_corr.to_csv(output_path, index=False)
    print(f"Wrote {len(long_corr)} rows to {output_path}")


if __name__ == "__main__":
    compute_correlation_matrix()
