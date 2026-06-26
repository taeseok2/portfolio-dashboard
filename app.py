import os
from datetime import datetime

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
import yfinance as yf
from streamlit_autorefresh import st_autorefresh

# --- Page config ---
st.set_page_config(
    page_title="Portfolio Dashboard",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# Auto-refresh every 60 seconds
st_autorefresh(interval=60_000, key="price_refresh")

# --- Dark-mode CSS ---
st.markdown("""
<style>
  /* Global background */
  .stApp { background-color: #0e1117; color: #e0e0e0; }

  /* Metric cards */
  [data-testid="metric-container"] {
    background: #1c1f26;
    border: 1px solid #2a2d36;
    border-radius: 12px;
    padding: 16px 20px;
  }
  [data-testid="metric-container"] label { color: #9ca3af !important; font-size: 0.78rem; letter-spacing: 0.05em; }
  [data-testid="metric-container"] [data-testid="stMetricValue"] { color: #f0f0f0 !important; font-size: 1.6rem; font-weight: 700; }
  [data-testid="stMetricDelta"] { font-size: 0.85rem !important; }

  /* Dataframe */
  .stDataFrame { border-radius: 12px; overflow: hidden; }

  /* Section headers */
  .section-title {
    color: #9ca3af;
    font-size: 0.72rem;
    font-weight: 600;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    margin: 32px 0 12px 0;
    border-bottom: 1px solid #2a2d36;
    padding-bottom: 6px;
  }

  /* Hide Streamlit branding */
  #MainMenu, footer { visibility: hidden; }
</style>
""", unsafe_allow_html=True)

# --- Helpers ---
PLOTLY_LAYOUT = dict(
    paper_bgcolor="#0e1117",
    plot_bgcolor="#0e1117",
    font=dict(color="#e0e0e0", family="Inter, sans-serif"),
    margin=dict(l=16, r=16, t=40, b=16),
)

def fmt_currency(v): return f"₩{v:,.0f}"
def fmt_pct(v):      return f"{v:+.2f}%"
def fmt_delta(v):    return f"{v:+,.0f}"


@st.cache_data(ttl=300)   # 5-minute cache
def load_portfolio():
    return pd.read_csv("portfolio.csv")


@st.cache_data(ttl=300)
def fetch_quote(ticker: str) -> dict:
    """Return a dict with price, day_change_pct, ma7, ma30, volatility."""
    t = yf.Ticker(ticker)
    hist = t.history(period="35d", auto_adjust=True)
    if hist.empty:
        return {}
    close = hist["Close"]
    price = float(close.iloc[-1])
    prev  = float(close.iloc[-2]) if len(close) > 1 else price
    day_change_pct = (price - prev) / prev * 100 if prev else 0

    ma7  = float(close.tail(7).mean())  if len(close) >= 7  else price
    ma30 = float(close.tail(30).mean()) if len(close) >= 30 else price

    returns = close.pct_change().dropna()
    vol = float(returns.tail(21).std() * np.sqrt(252) * 100) if len(returns) >= 5 else 0

    return dict(price=price, day_change_pct=day_change_pct, ma7=ma7, ma30=ma30, volatility=vol)


@st.cache_data(ttl=300)
def load_history():
    path = os.path.join("data", "history.csv")
    if not os.path.exists(path):
        return pd.DataFrame()
    df = pd.read_csv(path, parse_dates=["date"])
    return df


@st.cache_data(ttl=300)
def fetch_returns(ticker: str):
    """Daily returns series over ~6 months for risk metrics."""
    hist = yf.Ticker(ticker).history(period="6mo", auto_adjust=True)
    if hist.empty:
        return pd.Series(dtype=float)
    return hist["Close"].pct_change().dropna()


@st.cache_data(ttl=300)
def fetch_30d(ticker: str):
    return yf.Ticker(ticker).history(period="35d", auto_adjust=True)[["Close"]]


# --- Load data ---
portfolio = load_portfolio()
history   = load_history()

tickers = portfolio["ticker"].tolist()
has_sector = "sector" in portfolio.columns
has_name   = "name" in portfolio.columns
ticker_to_name = dict(zip(portfolio["ticker"], portfolio["name"])) if has_name else {}

with st.spinner("Fetching live prices..."):
    quotes = {t: fetch_quote(t) for t in tickers}

# Build enriched positions table
rows = []
for _, row in portfolio.iterrows():
    tk   = row["ticker"]
    sh   = float(row["shares"])
    cb   = float(row["cost_basis"])
    q    = quotes.get(tk, {})
    if not q:
        continue
    price     = q["price"]
    mkt_val   = price * sh
    cost_val  = cb * sh
    gain      = mkt_val - cost_val
    gain_pct  = (gain / cost_val * 100) if cost_val else 0
    rows.append(dict(
        Ticker   = tk,
        Name     = ticker_to_name.get(tk, tk),
        Sector   = row["sector"] if has_sector else "Unclassified",
        Shares   = sh,
        Price    = price,
        MktValue = mkt_val,
        CostVal  = cost_val,
        Gain     = gain,
        GainPct  = gain_pct,
        DayChg   = q["day_change_pct"],
        MA7      = q["ma7"],
        MA30     = q["ma30"],
        Volatility = q["volatility"],
    ))

positions = pd.DataFrame(rows)

# Graceful degradation: if no quotes came back (e.g. the data provider is
# rate-limiting or temporarily down), show a clear message instead of crashing.
if positions.empty:
    st.markdown("## 📈 Portfolio Dashboard")
    st.error(
        "Couldn't fetch live price data for any holdings right now. "
        "This usually means the market data provider (Yahoo Finance) is "
        "rate-limiting or temporarily unavailable. Prices are cached for "
        "5 minutes — please refresh in a little while."
    )
    st.stop()

total_value    = positions["MktValue"].sum()
total_cost     = positions["CostVal"].sum()
total_gain     = total_value - total_cost
total_gain_pct = (total_gain / total_cost * 100) if total_cost else 0

# --- Header ---
st.markdown("## 📈 Portfolio Dashboard")
st.caption(f"Prices cached for 5 min · Last refresh: {datetime.now().strftime('%H:%M:%S')}")

# --- KPI row ---
c1, c2, c3, c4 = st.columns(4)
c1.metric("Total Value",      fmt_currency(total_value))
c2.metric("Total Cost Basis", fmt_currency(total_cost))
c3.metric("Total Gain / Loss",
          fmt_currency(total_gain),
          delta=fmt_pct(total_gain_pct),
          delta_color="normal")
day_pnl = (positions["Gain"] * positions["DayChg"] / 100).sum()  # approx daily P&L
c4.metric("Est. Day P&L", fmt_currency(day_pnl), delta_color="normal")

# --- Allocation + History row ---
st.markdown('<div class="section-title">Allocation & Portfolio History</div>', unsafe_allow_html=True)

col_pie, col_hist = st.columns([1, 2])

with col_pie:
    fig_pie = px.pie(
        positions,
        names="Name",
        values="MktValue",
        hole=0.55,
        color_discrete_sequence=px.colors.qualitative.Pastel,
    )
    fig_pie.update_traces(textposition="inside", textinfo="label+percent")
    fig_pie.update_layout(
        **PLOTLY_LAYOUT,
        showlegend=False,
        height=340,
        title=dict(text="Allocation by Market Value", font=dict(size=13), x=0.5),
    )
    st.plotly_chart(fig_pie, use_container_width=True)

with col_hist:
    if history.empty:
        st.info("No history data yet. Run `python fetch_data.py` to seed data/history.csv, or wait for the GitHub Actions cron to kick in.")
    else:
        hist_agg = history.groupby("date")["market_value"].sum().reset_index()
        fig_hist = go.Figure()
        fig_hist.add_trace(go.Scatter(
            x=hist_agg["date"],
            y=hist_agg["market_value"],
            mode="lines",
            fill="tozeroy",
            fillcolor="rgba(99,102,241,0.12)",
            line=dict(color="#6366f1", width=2),
            name="Portfolio Value",
        ))
        fig_hist.update_layout(
            **PLOTLY_LAYOUT,
            height=340,
            title=dict(text="Portfolio Value Over Time", font=dict(size=13), x=0),
            showlegend=False,
            xaxis=dict(gridcolor="#1f2330", zerolinecolor="#1f2330", tickformat="%b %d", type="date"),
            yaxis=dict(tickprefix="$", gridcolor="#1f2330", zerolinecolor="#1f2330"),
        )
        st.plotly_chart(fig_hist, use_container_width=True)

# --- Sector allocation ---
st.markdown('<div class="section-title">Sector Allocation</div>', unsafe_allow_html=True)

sector_alloc = (
    positions.groupby("Sector")["MktValue"]
    .sum()
    .sort_values(ascending=True)
    .reset_index()
)
sector_alloc["Pct"] = sector_alloc["MktValue"] / sector_alloc["MktValue"].sum() * 100

fig_sector = go.Figure()
fig_sector.add_trace(go.Bar(
    x=sector_alloc["MktValue"],
    y=sector_alloc["Sector"],
    orientation="h",
    marker=dict(color="#6366f1"),
    text=[f"₩{v:,.0f}  ({p:.1f}%)" for v, p in zip(sector_alloc["MktValue"], sector_alloc["Pct"], strict=False)],
    textposition="outside",
))
fig_sector.update_layout(
    **PLOTLY_LAYOUT,
    height=320,
    showlegend=False,
    xaxis=dict(tickprefix="₩", gridcolor="#1f2330", zerolinecolor="#1f2330"),
    yaxis=dict(gridcolor="#1f2330", zerolinecolor="#1f2330"),
)
st.plotly_chart(fig_sector, use_container_width=True)

# --- Portfolio Risk ---
st.markdown('<div class="section-title">Portfolio Risk</div>', unsafe_allow_html=True)

weights = (positions.set_index("Ticker")["MktValue"] / total_value)
returns_df = pd.DataFrame({
    ticker_to_name.get(tk, tk): fetch_returns(tk) for tk in positions["Ticker"]
}).dropna()

if returns_df.empty or len(returns_df) < 20:
    st.info("Not enough return history to compute risk metrics yet.")
else:
    name_weights = weights.rename(index=ticker_to_name)
    w = name_weights.reindex(returns_df.columns).fillna(0)
    w = w / w.sum()
    port_returns = returns_df.dot(w)

    ann_factor = np.sqrt(252)
    ann_return = port_returns.mean() * 252 * 100
    ann_vol    = port_returns.std() * ann_factor * 100
    rf         = 0.04
    sharpe     = ((port_returns.mean() * 252) - rf) / (port_returns.std() * ann_factor) if port_returns.std() else 0

    cum    = (1 + port_returns).cumprod()
    peak   = cum.cummax()
    max_dd = ((cum - peak) / peak).min() * 100

    r1, r2, r3, r4 = st.columns(4)
    r1.metric("Annualized Return", f"{ann_return:+.1f}%")
    r2.metric("Annualized Volatility", f"{ann_vol:.1f}%")
    r3.metric("Sharpe Ratio", f"{sharpe:.2f}")
    r4.metric("Max Drawdown", f"{max_dd:.1f}%")

    st.caption(
        "Risk metrics use ~6 months of daily returns, weighted by current market value. "
        "Sharpe assumes a 4% annual risk-free rate. Volatility and Sharpe are annualized (x sqrt 252)."
    )

# --- Correlation heatmap ---
st.markdown('<div class="section-title">Holdings Correlation</div>', unsafe_allow_html=True)

if returns_df.empty or returns_df.shape[1] < 2:
    st.info("Not enough overlapping return history to compute correlations yet.")
else:
    corr = returns_df.corr()
    fig_corr = go.Figure(data=go.Heatmap(
        z=corr.values,
        x=corr.columns,
        y=corr.columns,
        zmin=-1, zmax=1,
        colorscale="RdBu_r",
        text=corr.round(2).values,
        texttemplate="%{text}",
        textfont=dict(size=9),
        colorbar=dict(title="ρ"),
    ))
    fig_corr.update_layout(
        **PLOTLY_LAYOUT,
        height=600,
        xaxis=dict(side="bottom"),
        yaxis=dict(autorange="reversed"),
    )
    st.plotly_chart(fig_corr, use_container_width=True)

    st.caption(
        "Pairwise correlation of daily returns over ~6 months. "
        "Values near +1 (red) move together; near 0 (white) move independently; "
        "negative (blue) move opposite. Lower average correlation means better diversification."
    )

# --- Positions table ---
st.markdown('<div class="section-title">Positions</div>', unsafe_allow_html=True)

display = positions[[
    "Name", "Sector", "Shares", "Price", "MktValue",
    "Gain", "GainPct", "DayChg", "MA7", "MA30", "Volatility"
]].copy()

display.columns = [
    "Name", "Sector", "Shares", "Price (₩)", "Mkt Value (₩)",
    "Gain/Loss (₩)", "Gain/Loss (%)", "Day Chg (%)",
    "7-Day MA (₩)", "30-Day MA (₩)", "Ann. Vol (%)"
]

# Style helper
def color_val(v):
    c = "#4ade80" if v > 0 else ("#f87171" if v < 0 else "#9ca3af")
    return f"color: {c}"

def color_pct(v):
    c = "#4ade80" if v > 0 else ("#f87171" if v < 0 else "#9ca3af")
    return f"color: {c}"

styled = (
    display.style
    .format({
        "Price (₩)":       "₩{:,.0f}",
        "Mkt Value (₩)":   "₩{:,.0f}",
        "Gain/Loss (₩)":   "₩{:+,.0f}",
        "Gain/Loss (%)":   "{:+.2f}%",
        "Day Chg (%)":     "{:+.2f}%",
        "7-Day MA (₩)":    "₩{:,.0f}",
        "30-Day MA (₩)":   "₩{:,.0f}",
        "Ann. Vol (%)":    "{:.1f}%",
        "Shares":          "{:.0f}",
    })
    .map(color_val, subset=["Gain/Loss (₩)"])
    .map(color_pct, subset=["Gain/Loss (%)", "Day Chg (%)"])
    .set_properties(**{"background-color": "#1c1f26", "border-color": "#2a2d36"})
    .set_table_styles([
        {"selector": "thead th", "props": [("background-color", "#13151c"), ("color", "#9ca3af"), ("font-size", "0.75rem")]},
        {"selector": "tbody tr:hover td", "props": [("background-color", "#22252e")]},
    ])
)

st.dataframe(styled, use_container_width=True, hide_index=True)

# --- Per-ticker price chart ---
st.markdown('<div class="section-title">30-Day Price Charts</div>', unsafe_allow_html=True)

cols = st.columns(min(3, len(tickers)))
for i, tk in enumerate(tickers):
    hist_tk = fetch_30d(tk)
    if hist_tk.empty:
        continue
    col = cols[i % 3]
    with col:
        q    = quotes.get(tk, {})
        chg  = q.get("day_change_pct", 0)
        clr  = "#4ade80" if chg >= 0 else "#f87171"
        label = ticker_to_name.get(tk, tk)

        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=hist_tk.index,
            y=hist_tk["Close"],
            mode="lines",
            line=dict(color=clr, width=1.5),
            fill="tozeroy",
            fillcolor=f"rgba({'74,222,128' if chg>=0 else '248,113,113'},0.08)",
            name=label,
        ))
        fig.update_layout(
            **PLOTLY_LAYOUT,
            height=200,
            title=dict(text=f"{label}  <span style='color:{clr};font-size:13px'>{chg:+.2f}%</span>", font=dict(size=14), x=0),
            showlegend=False,
            xaxis=dict(showticklabels=False, gridcolor="#1f2330"),
            yaxis=dict(tickprefix="$", gridcolor="#1f2330"),
        )
        st.plotly_chart(fig, use_container_width=True)
