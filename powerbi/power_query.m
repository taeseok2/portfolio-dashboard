// ================================================================
// POWER QUERY M SCRIPTS — Korean ETF Portfolio Dashboard (Power BI)
// ================================================================
// How to use: In Power BI Desktop, Home > Transform Data > New Source >
// Blank Query, open the Advanced Editor, and paste each query below in
// separately (one query per "let...in" block). Rename each query to
// match the name in the comment header ("Portfolio", "History",
// "Correlation", "LivePrices (optional)").
//
// Replace <GITHUB_RAW_URL> with your repo's raw base URL, e.g.
//   https://raw.githubusercontent.com/<you>/portfolio-dashboard/main
// ================================================================


// ---------------------------------------------------------------
// Query: Portfolio
// Loads current holdings from portfolio.csv
// ---------------------------------------------------------------
let
    Source = Csv.Document(
        Web.Contents("<GITHUB_RAW_URL>/portfolio.csv"),
        [Delimiter=",", Columns=5, Encoding=65001, QuoteStyle=QuoteStyle.None]
    ),
    PromotedHeaders = Table.PromoteHeaders(Source, [PromoteAllScalars=true]),
    ChangedType = Table.TransformColumnTypes(PromotedHeaders,{
        {"ticker", type text},
        {"name", type text},
        {"shares", Int64.Type},
        {"cost_basis", type number},
        {"sector", type text}
    })
in
    ChangedType


// ---------------------------------------------------------------
// Query: History
// Loads daily price snapshots from data/history.csv.
// Confirmed against your repo — fetch_data.py actually writes:
//   date, ticker, price, shares, market_value
// (market_value is pre-computed as price * shares at fetch time, so
// the "Value over time" chart can sum it directly with no join back
// to Portfolio needed — see the Portfolio Value (History) measure
// in dax_measures.dax.)
//
// DATA CHECK: as of this write-up, data/history.csv holds only 5
// rows for a single date (2026-06-06), tickers AAPL/MSFT/GOOGL/AMZN/
// NVDA — none of which match your actual portfolio.csv holdings (the
// six KRX ETFs). That looks like leftover seed/test data from before
// the portfolio was switched over. Trigger update_history.yml
// manually (Actions tab → Run workflow) so it appends real rows for
// your KRX tickers before building the report, or the Portfolio↔
// History relationship will have zero matches.
// ---------------------------------------------------------------
let
    Source = Csv.Document(
        Web.Contents("<GITHUB_RAW_URL>/data/history.csv"),
        [Delimiter=",", Columns=5, Encoding=65001, QuoteStyle=QuoteStyle.None]
    ),
    PromotedHeaders = Table.PromoteHeaders(Source, [PromoteAllScalars=true]),
    ChangedType = Table.TransformColumnTypes(PromotedHeaders,{
        {"date", type date},
        {"ticker", type text},
        {"price", type number},
        {"shares", type number},
        {"market_value", type number}
    })
in
    ChangedType


// ---------------------------------------------------------------
// Query: Correlation
// Loads the ticker-by-ticker correlation matrix produced by the
// companion compute_correlation.py script (see that file — it
// writes data/correlation_matrix.csv in long format: ticker_a,
// ticker_b, correlation). Only add this query once that script is
// wired into your cron.
// ---------------------------------------------------------------
let
    Source = Csv.Document(
        Web.Contents("<GITHUB_RAW_URL>/data/correlation_matrix.csv"),
        [Delimiter=",", Columns=3, Encoding=65001, QuoteStyle=QuoteStyle.None]
    ),
    PromotedHeaders = Table.PromoteHeaders(Source, [PromoteAllScalars=true]),
    ChangedType = Table.TransformColumnTypes(PromotedHeaders,{
        {"ticker_a", type text},
        {"ticker_b", type text},
        {"correlation", type number}
    })
in
    ChangedType


// ---------------------------------------------------------------
// Query: LivePrices (OPTIONAL — advanced)
// Calls Yahoo Finance's public quote endpoint directly — the same
// underlying source yfinance wraps. Use this ONLY if the daily-cron
// History data isn't fresh enough for your use case.
//
// CAVEATS:
//  - This endpoint is unofficial and undocumented. Yahoo can change,
//    rate-limit, or block it without notice — more likely to break
//    on Power BI Service's scheduled refresh (shared IPs) than on a
//    single local Streamlit session.
//  - No error handling included below; wrap in try/otherwise for
//    production use so a failed call doesn't break the whole report.
// ---------------------------------------------------------------
let
    Tickers = {"360200.KS","203780.KS","332610.KS","381170.KS","381180.KS","133690.KS"},
    TickerList = Text.Combine(Tickers, ","),
    Source = Json.Document(Web.Contents(
        "https://query1.finance.yahoo.com/v7/finance/quote",
        [Query=[symbols=TickerList]]
    )),
    Result = Source[quoteResponse][result],
    ToTable = Table.FromList(Result, Splitter.SplitByNothing(), null, null, ExtraValues.Error),
    Expanded = Table.ExpandRecordColumn(ToTable, "Column1",
        {"symbol","regularMarketPrice","regularMarketChangePercent"},
        {"ticker","live_price","live_day_change_pct"})
in
    Expanded
