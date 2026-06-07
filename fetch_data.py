"""
fetch_data.py — Daily price snapshot for every ticker in portfolio.csv.
Appends one row per ticker to data/history.csv with columns:
  date, ticker, price, shares, market_value

Run manually:   python fetch_data.py
Run in CI:      see .github/workflows/update_history.yml
"""

import os
import sys
import pandas as pd
import yfinance as yf
from datetime import date

DATA_DIR  = "data"
HIST_FILE = os.path.join(DATA_DIR, "history.csv")
PORT_FILE = "portfolio.csv"


def main():
    os.makedirs(DATA_DIR, exist_ok=True)

    portfolio = pd.read_csv(PORT_FILE)
    today     = date.today().isoformat()

    # Load existing history so we can skip already-fetched dates
    if os.path.exists(HIST_FILE):
        existing = pd.read_csv(HIST_FILE)
        existing["date"] = pd.to_datetime(existing["date"]).dt.date.astype(str)
    else:
        existing = pd.DataFrame(columns=["date", "ticker", "price", "shares", "market_value"])

    already_fetched = set(
        existing[existing["date"] == today]["ticker"].tolist()
    )

    new_rows = []
    for _, row in portfolio.iterrows():
        ticker = row["ticker"]
        shares = float(row["shares"])

        if ticker in already_fetched:
            print(f"  {ticker}: already in history for {today}, skipping.")
            continue

        try:
            t     = yf.Ticker(ticker)
            hist  = t.history(period="2d", auto_adjust=True)
            if hist.empty:
                print(f"  {ticker}: no data returned, skipping.", file=sys.stderr)
                continue
            price = float(hist["Close"].iloc[-1])
        except Exception as exc:
            print(f"  {ticker}: fetch error — {exc}", file=sys.stderr)
            continue

        new_rows.append(dict(
            date         = today,
            ticker       = ticker,
            price        = round(price, 4),
            shares       = shares,
            market_value = round(price * shares, 2),
        ))
        print(f"  {ticker}: ${price:.2f}  ×  {shares}  =  ${price * shares:,.2f}")

    if not new_rows:
        print("Nothing new to append.")
        return

    new_df   = pd.DataFrame(new_rows)
    combined = pd.concat([existing, new_df], ignore_index=True)
    combined.to_csv(HIST_FILE, index=False)
    print(f"\nAppended {len(new_rows)} row(s) to {HIST_FILE}")


if __name__ == "__main__":
    main()
