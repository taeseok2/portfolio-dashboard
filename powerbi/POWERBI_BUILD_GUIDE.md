# Korean ETF Portfolio Dashboard — Power BI Build Guide

This ports the Streamlit dashboard in your README to Power BI. The
GitHub Actions cron, `fetch_data.py`, `portfolio.csv`, and
`data/history.csv` all stay exactly as they are — only the front end
changes, from Streamlit/Plotly to Power BI Desktop + Power BI Service.

## Architecture

```
GitHub Repository (unchanged)
  portfolio.csv, data/history.csv
  .github/workflows/ci.yml + update_history.yml  (unchanged)
        │
        │  raw.githubusercontent.com URLs (public HTTPS, no gateway needed)
        ▼
Power BI Desktop
  Power Query  ──►  Portfolio, History, Correlation tables
  DAX measures ──►  KPIs, positions, risk metrics
  Report pages ──►  visuals
        │
        │  Publish
        ▼
Power BI Service
  Scheduled refresh (up to 8x/day on Pro; hourly-ish on Premium)
```

## What you need (provided alongside this guide)

| File | Purpose |
|---|---|
| `power_query.m` | Power Query M scripts for the Portfolio, History, Correlation (and optional LivePrices) queries |
| `dax_measures.dax` | Full DAX measure library — KPIs, positions table, moving averages, volatility, Sharpe ratio, max drawdown, allocation |
| `portfolio_template.csv` | Not needed — checked your repo and `portfolio.csv` already has real shares/cost_basis for all six tickers. Kept here only as a reference of the expected column layout. |
| `compute_correlation.py` | Companion to `fetch_data.py` — snapshots a ticker-by-ticker correlation matrix for the heatmap visual |

## 1. Get the data into Power BI

1. Open Power BI Desktop → **Get Data → Blank Query** → **Advanced Editor**.
2. Paste each query block from `power_query.m` in one at a time, renaming each query to match its comment header (`Portfolio`, `History`, `Correlation`).
3. Replace `<GITHUB_RAW_URL>` with your repo's raw base URL:
   `https://raw.githubusercontent.com/taeseok2/portfolio-dashboard/main`
4. **`History` columns are confirmed**, not assumed — checked directly against your `fetch_data.py`: it writes `date, ticker, price, shares, market_value` (not `close`), and `market_value` is pre-computed as `price × shares` at fetch time. The M script and DAX file below already match this.
5. **Data check before you build anything**: `data/history.csv` in your repo currently holds only 5 rows, all dated 2026-06-06, for tickers `AAPL/MSFT/GOOGL/AMZN/NVDA` — none of which match your actual `portfolio.csv` holdings (the six KRX ETFs). That's leftover seed/test data from before the portfolio was switched over. Go to the **Actions tab → Update Portfolio History → Run workflow** to trigger `fetch_data.py` manually and append real rows for your KRX tickers — otherwise the `Portfolio` ↔ `History` relationship will have zero matching rows and every measure below will show blank.
6. Skip the `Correlation` query until you've added `compute_correlation.py` to your cron (step 4).
6. Skip `LivePrices` unless daily-cron freshness genuinely isn't enough — it calls Yahoo's endpoint directly and is more likely to break under Power BI Service's scheduled refresh than a single local session. Read the caveats in the script comments first.

## 2. Build the data model

1. Go to **Model view**.
2. Draw a relationship: `Portfolio[ticker]` → `History[ticker]` (one-to-many, single direction, History on the many side).
3. Right-click `History[date]` → **Mark as date table** (or build a proper calendar table) so `DATESINPERIOD` in the DAX measures behaves correctly around weekends/holidays.
4. Once you've added the `Correlation` table, it doesn't need a relationship — it's used standalone as a self-contained matrix.

## 3. Add the DAX measures

Open `dax_measures.dax` and add each block as either a **measure** (Modeling → New Measure) or a **calculated column** — the file marks which is which. Order matters for a few of these (e.g. `Daily Return` and `Running Peak` must exist before `Annualized Volatility`, `Sharpe Ratio`, and `Max Drawdown` will resolve), so add them top to bottom.

## 4. Add the correlation snapshot to your cron

1. Copy `compute_correlation.py` into your repo alongside `fetch_data.py`.
2. In `.github/workflows/update_history.yml`, add a step after the existing `fetch_data.py` run:
   ```yaml
   - name: Compute correlation matrix
     run: python compute_correlation.py
   ```
3. Make sure the commit/push step that already handles `data/history.csv` also picks up `data/correlation_matrix.csv`.
4. Re-run the workflow once manually, then add the `Correlation` query from `power_query.m`.

## 5. Build the report pages

Mapped directly to your existing **Dashboard Features** table:

| Original section | Power BI equivalent |
|---|---|
| KPI row | Card visuals: `[Market Value]`, `[Cost Basis Value]`, `[Total Gain Loss]` + `[Total Gain Loss %]`, `[Day P&L]` |
| Allocation pie | Pie/Donut chart: legend = `Portfolio[name]`, values = `[Market Value]` (or `[Position Weight %]`) |
| Value over time | Line chart: axis = `History[date]`, values = `[Portfolio Value (History)]` — sums the pre-computed `market_value` column directly, no relationship needed |
| Positions table | Table/Matrix visual: `Portfolio[name]`, `[Latest Price]`, `[Position Market Value]`, `[Position Gain Loss]`, `[Day Change %]`, `[7-Day MA]`, `[30-Day MA]`, `[Annualized Volatility]` |
| 30-day mini charts | Native table sparklines (Power BI's built-in sparkline column, or a certified custom visual if your tenant hasn't enabled the preview feature) on `History[close]` filtered to the last 30 days |
| Correlation heatmap | Matrix visual on the `Correlation` table: rows = `ticker_a`, columns = `ticker_b`, values = `correlation`, with conditional formatting (color scale) applied |

Add `[Sharpe Ratio]` and `[Max Drawdown]` as cards on a "Risk Metrics" section — these exist in your codebase's `test_risk_metrics.py` but weren't broken out in the README's feature table, so place them wherever fits your layout.

## 6. Publish and schedule refresh

1. **Publish** to a Power BI Service workspace.
2. Since the data source is a public HTTPS URL (no on-prem gateway needed), go to the dataset's **Settings → Scheduled refresh** and enable it.
3. Match your cron's cadence: the workflow runs weekdays at 21:30 UTC, so schedule the Power BI refresh for shortly after (e.g. 22:00 UTC) so it always picks up the latest commit.
4. Scheduled refresh requires a **Power BI Pro** (or Premium Per User) license for shared workspaces; a free license only refreshes on-demand from Desktop.

## Known trade-offs vs. the Streamlit version

- **Live 5-minute pricing** becomes **daily** (matching the cron cadence) unless you wire in the optional `LivePrices` query — which trades reliability for freshness.
- **Correlation** is precomputed in Python rather than calculated live in DAX — more reliable and far simpler than replicating a covariance matrix in DAX, at the cost of only updating once a day.
