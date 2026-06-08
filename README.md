# 📈 Personal Stock Portfolio Dashboard

A self-updating, public portfolio tracker built with **Streamlit + Plotly + yfinance**.
No API keys. No back-end server. Deploys free on Streamlit Community Cloud.

<!-- CI/CD: lint + tests (3.11/3.12) + security audit run on every PR. -->

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                            GitHub Repository                                │
│                                                                             │
│  portfolio.csv          ◄── Edit this to change holdings                   │
│  data/history.csv       ◄── Auto-appended by fetch_data.py                 │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────┐       │
│  │                     CI/CD (GitHub Actions)                      │       │
│  │                                                                 │       │
│  │  Every push / PR → ci.yml                                       │       │
│  │    ├── lint job    ruff check + format check                    │       │
│  │    ├── test job    pytest (Python 3.11 & 3.12) + coverage       │       │
│  │    └── audit job   pip-audit security scan                      │       │
│  │                                    │                            │       │
│  │                              must be green                      │       │
│  │                                    ▼                            │       │
│  │  Weekdays 21:30 UTC → update_history.yml                        │       │
│  │    ├── guard job   verify CI passes on main                     │       │
│  │    └── fetch job   python fetch_data.py → git commit & push     │       │
│  └─────────────────────────────────────────────────────────────────┘       │
│                                                                             │
│  ┌──────────────────┐   Streamlit Community Cloud (CD)                     │
│  │     app.py       │   auto-deploys whenever main branch changes           │
│  │  (Streamlit app) │──► reads portfolio.csv + history.csv                 │
│  │                  │    calls yfinance for live prices (5-min cache)       │
│  │                  │    renders dashboard (Plotly charts)                  │
│  └──────────────────┘                                                       │
└─────────────────────────────────────────────────────────────────────────────┘

Data flow:
  yfinance (live)  ──►  app.py       ──►  KPIs, position table, mini charts
  yfinance (close) ──►  fetch_data   ──►  data/history.csv  ──►  value-over-time chart
```

---

## CI/CD Pipeline

### Continuous Integration (`ci.yml`)

Triggered on **every push to any branch** and **every PR targeting `main`**.

| Job | What it does |
|---|---|
| **lint** | `ruff check .` — catches bugs, style issues, unused imports; `ruff format --check` — enforces consistent formatting |
| **test** | `pytest tests/` on Python 3.11 **and** 3.12 in parallel; generates a `coverage.xml` artifact |
| **audit** | `pip-audit` scans `requirements.txt` for known CVEs |

All three must pass before a PR can merge (enforce with branch protection — see below).

### Continuous Delivery

**Streamlit Community Cloud** watches the `main` branch and re-deploys automatically whenever a commit lands. There's no separate deploy step to configure.

**`update_history.yml`** (the daily price cron) has a `check-ci` guard job that calls the GitHub API to confirm CI is green on `main` before it runs. If you accidentally push broken code, the history cron won't execute until it's fixed.

### Recommended branch protection (GitHub → Settings → Branches → main)

```
✅ Require status checks to pass before merging
   ✅ Lint (ruff)
   ✅ Test (pytest) / 3.11
   ✅ Test (pytest) / 3.12
   ✅ Security audit (pip-audit)
✅ Require branches to be up to date before merging
✅ Do not allow bypassing the above settings
```

### Run CI locally

```bash
pip install -r requirements.txt -r requirements-dev.txt

# Lint
ruff check .
ruff format --check .

# Tests + coverage
pytest tests/ --cov=fetch_data --cov-report=term-missing -v

# Security audit
pip-audit -r requirements.txt
```

---

## File Structure

```
portfolio-dashboard/
├── app.py                          # Streamlit dashboard
├── fetch_data.py                   # Daily snapshot script (run by CI)
├── portfolio.csv                   # Your holdings  ← edit this
├── requirements.txt                # Production dependencies
├── requirements-dev.txt            # Dev/test dependencies (ruff, pytest…)
├── ruff.toml                       # Linter + formatter config
├── README.md
├── data/
│   └── history.csv                 # Accumulated daily snapshots
├── tests/
│   ├── conftest.py                 # Shared fixtures (mock yfinance, tmp CSVs)
│   ├── test_fetch_data.py          # Integration-style tests for fetch_data.py
│   ├── test_calculations.py        # Unit tests for portfolio maths (gain/loss, MA, vol)
│   └── test_risk_metrics.py        # Unit tests for risk metrics, correlation, sector allocation
└── .github/
    └── workflows/
        ├── ci.yml                  # Lint + test + audit on every push/PR
        └── update_history.yml      # Daily price cron (guarded by CI status)
```

---

## Local Setup

### 1. Clone and install

```bash
git clone https://github.com/<you>/portfolio-dashboard.git
cd portfolio-dashboard
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

pip install -r requirements.txt
```

### 2. Edit your holdings

Open `portfolio.csv` and replace the sample tickers with your own:

```
ticker,shares,cost_basis
AAPL,10,150.00
MSFT,5,280.00
```

- **ticker** — Yahoo Finance symbol (e.g. `BRK-B`, `VOO`, `TSLA`)
- **shares** — number of shares you hold
- **cost_basis** — your average purchase price per share

### 3. Seed historical data (optional but recommended)

```bash
python fetch_data.py
```

This writes today's closing prices to `data/history.csv`.
Run it once a day (or let GitHub Actions do it automatically) to build up history.

### 4. Run the dashboard

```bash
streamlit run app.py
```

Open [http://localhost:8501](http://localhost:8501).

---

## Deploy on Streamlit Community Cloud

1. **Push your repo to GitHub** (must be public, or a private repo on a paid Streamlit plan).

2. Go to [share.streamlit.io](https://share.streamlit.io) and sign in with GitHub.

3. Click **"New app"**:
   - **Repository**: `<you>/portfolio-dashboard`
   - **Branch**: `main`
   - **Main file path**: `app.py`

4. Click **Deploy**. Streamlit installs `requirements.txt` automatically.

5. Your dashboard is live at `https://<you>-portfolio-dashboard-app-xxxx.streamlit.app`.

> The app re-reads `portfolio.csv` and `data/history.csv` from the repo on each
> cold start. Every time the GitHub Actions cron commits new history, Streamlit
> picks it up on the next page load (or within 5 minutes via cache TTL).

---

## Set Up the GitHub Actions Cron

The workflow at `.github/workflows/update_history.yml` runs **Monday–Friday at
21:30 UTC** (≈ 5:30 PM ET, 30 minutes after NYSE close).

### Steps

1. **Push the repo** to GitHub — the workflow file is committed already.

2. Open your repo on GitHub → **Actions** tab. You should see
   `Update Portfolio History` listed.

3. GitHub Actions needs write access to commit the updated CSV back.
   This is already handled by `permissions: contents: write` in the YAML.
   No secrets or tokens to configure.

4. **Test it manually**: click **"Run workflow"** → **"Run workflow"** on the
   Actions page. Watch the logs; a successful run ends with
   `chore: daily price snapshot YYYY-MM-DD` in your commit history.

5. After the first automated run, refresh the deployed Streamlit app —
   the "Portfolio Value Over Time" chart will start filling in.

### Changing the schedule

Edit the `cron:` line in `.github/workflows/update_history.yml`.
The format is standard cron (`minute hour day month weekday`).
All times are UTC. [crontab.guru](https://crontab.guru) is handy for testing expressions.

---

## Dashboard Features

| Section | Details |
|---|---|
| **KPI row** | Total value, cost basis, total gain/loss ($+%), estimated day P&L |
| **Allocation pie** | Market-value weight per position |
| **Value over time** | Line chart driven by `data/history.csv` |
| **Positions table** | Price, market value, gain/loss, day change, 7-day MA, 30-day MA, annualized volatility |
| **30-day mini charts** | One sparkline per ticker, green/red based on day change |

Live prices are cached for **5 minutes** — interacting with the app (scrolling,
clicking) does not trigger extra API calls within that window.

---

## Notes

- This is a **tracking and analysis tool only**. It does not provide buy/sell signals
  or investment advice.
- yfinance data is sourced from Yahoo Finance. Prices may be delayed 15 minutes during
  market hours.
- Weekend and holiday runs are skipped by the `1-5` weekday filter in the cron.
  If a fetch fails (network error, market holiday), the script exits cleanly and
  no duplicate row is written.
