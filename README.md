# py-screener — Seasonality + Volatility Screener for Options

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)

A toolkit that combines historical seasonality analysis, volatility assessment,
and options-specific tools to help identify and evaluate monthly options setups
on a given list of tickers.

Data source: Yahoo Finance via `yfinance`. No paid data feed required.

---

## Table of contents

1. [What it does](#what-it-does)
2. [Installation](#installation)
3. [Quick start](#quick-start)
4. [screener.py — CLI screening](#screenerpy)
5. [backtest.py — walk-forward backtest](#backtestpy)
6. [server.py — HTTP dashboard](#serverpy)
7. [Docker deployment](#docker-deployment)
8. [Recommended workflow](#recommended-workflow)
9. [Limitations — read before trading](#limitations--read-before-trading)

---

## What it does

| Module | Purpose |
|---|---|
| `screener.py` | Screens tickers: seasonality, IV, Greeks, skew, expected move, strategy suggestion |
| `backtest.py` | Walk-forward backtest of the seasonal signal — price-only or options-aware |
| `server.py` | FastAPI HTTP server + built-in daily scheduler; serves the web dashboard |
| `seasonality.py` | Monthly return statistics + t-test significance per month |
| `volatility.py` | Realized HV percentile + live ATM IV snapshot with Greeks and skew |
| `options_analysis.py` | Expected move, strategy selector (3×3 matrix), Black-Scholes pricing and Greeks |
| `iv_archive.py` | Accumulates daily IV snapshots in SQLite to compute IV Rank over time |
| `db.py` | Persists screening and backtest results to SQLite for the dashboard |

---

## Installation

Requires **Python 3.10+** and an internet connection. No paid data feed — all
prices and options chains are fetched from Yahoo Finance via `yfinance`.

```bash
git clone https://github.com/YOUR_USERNAME/py-screener.git
cd py-screener
python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

The SQLite database (`iv_archive.db`) is created automatically on first run.
There is nothing else to configure for local use.

---

## Quick start

Choose the path that fits your use case.

### A — CLI only (no server needed)

Screen a list of tickers and print the report to the terminal:

```bash
python screener.py --tickers GLD,XRT,EQT --years 5
```

Run the backtest for a ticker:

```bash
python backtest.py --tickers GLD --years 10
python backtest.py --tickers GLD --years 10 --strategy long-call
```

### B — Local web dashboard

Run the screener once to populate the database, then start the server:

```bash
python screener.py --tickers GLD,XRT,EQT --years 5 --output db
uvicorn server:app --host 0.0.0.0 --port 8000 --workers 1
```

Open `http://localhost:8000`. The server will also run the screener
automatically every weekday at 22:00 UTC from that point on.

### C — Docker on a server (persistent, automated)

See [Docker deployment](#docker-deployment) below. One container handles both
the HTTP server and the daily scheduled run. No cron required.

---

## screener.py

Screens one or more tickers and prints a detailed report for each, followed by
a comparative ranking.

```bash
# Print report to terminal
python screener.py --tickers GLD,XRT,EQT,UNG --years 5

# Skip live options chain (faster — seasonality + HV only)
python screener.py --tickers AAPL --years 10 --no-options

# Save results to SQLite for the dashboard
python screener.py --tickers GLD,XRT --years 5 --output db

# Save ranking to CSV as well
python screener.py --tickers GLD,XRT --years 5 --csv ranking.csv
```

### Flags

| Flag | Default | Description |
|---|---|---|
| `--tickers` | required | Comma-separated list of tickers (e.g. `GLD,XRT,EQT`) |
| `--years` | `5` | Years of price history to download |
| `--no-options` | off | Skip the live options chain fetch |
| `--output` | `print` | `print` (stdout) or `db` (save to SQLite for the dashboard) |
| `--iv-archive` | `iv_archive.db` | Path to the IV history database |
| `--csv` | — | Save the final ranking table to a CSV file |

### Output sections (per ticker)

**Current and next month seasonality**
Historical average return, win rate, number of observations, and a statistical
significance flag for the current and next calendar month.

The significance flag comes from a one-sample t-test (H₀: avg return = 0):
- `significant (p=0.021)` — the pattern is unlikely to be random noise
- `marginal (p=0.08)` — borderline, treat with caution
- `not significant (p=0.45)` — no reliable edge in this month's history

**Full seasonality table**
All 12 months with `avg_pct`, `std_pct`, `n_obs`, `win_rate_pct`, and `p_value`.
Use `n_obs` and `p_value` together: a month with `n_obs=4` has too little data
regardless of p-value.

**Realized historical volatility (HV)**
Current 20-day realized volatility and its percentile relative to the downloaded
history. Used as a proxy for IV — see Limitations below.

**Live IV snapshot**
ATM call and put for the next 1–2 available expiries: IV, bid/ask, and computed
Greeks (Delta, Gamma, Theta per day, Vega per 1% IV move).

Also shows **skew** (put IV − call IV at the same ATM strike). Positive skew
means the market is paying more for put protection.

**IV Rank / IV Percentile** *(available after 30+ daily runs)*
Once the local archive has enough snapshots:
- **IV Rank** = (current IV − period low) / (period high − period low) × 100
- **IV Percentile** = % of stored days where IV was below today's level

More accurate than the HV proxy because it reflects actual market pricing.
The archive grows automatically every time you run the screener with options enabled.

**Options analysis**
- **Expected move** = IV × √(DTE/365) expressed as ±% and ±$ with the implied
  1-sigma price range.
- **Pricing ratio** = expected move / |seasonal avg|. Below 1: options are
  pricing in less movement than history suggests (favours buyers). Above 2:
  options are pricing in more than twice the historical move (favours sellers).
- **Strategy suggestion** from the directional bias (bullish/bearish/neutral)
  combined with the IV level (low/normal/high):

  | Bias | IV low | IV normal | IV high |
  |---|---|---|---|
  | Bullish | Long Call / Debit Spread | Short Put | Short Put / CSP |
  | Bearish | Long Put / Debit Spread | Short Call | Short Call / Spread |
  | Neutral | Long Straddle / Strangle | No clear edge | Iron Condor / Strangle |

---

## backtest.py

Walk-forward backtest of the seasonal signal. For each test month, seasonality
and HV are computed **exclusively on data preceding that month**, eliminating
lookahead bias.

### Price-only backtest (default)

Enters long on the underlying at the first close of the month, exits at the last
close. Useful baseline to check whether the seasonal signal has an edge before
adding options complexity.

```bash
python backtest.py --tickers GLD,XRT --years 10
python backtest.py --tickers GLD --years 10 --trend-filter
```

### Options-aware backtest (`--strategy`)

Prices an ATM European option at month entry using **Black-Scholes with the
20-day realized HV as the IV proxy**, holds to month-end, and records P&L as
% of spot.

```bash
python backtest.py --tickers GLD --years 10 --strategy long-call
python backtest.py --tickers XRT --years 10 --strategy short-put --trend-filter
python backtest.py --tickers GLD,XRT --years 10 --strategy long-call --csv bt.csv
```

Supported strategies: `long-call`, `short-put`, `long-put`, `short-call`.

### Flags

| Flag | Default | Description |
|---|---|---|
| `--tickers` | required | Comma-separated list of tickers |
| `--years` | `10` | Years of history to download |
| `--min-history` | `3` | Warm-up years before testing begins |
| `--entry-avg` | `1.0` | Min historical avg monthly return (%) to trigger entry |
| `--entry-wr` | `55` | Min historical win rate (%) to trigger entry |
| `--trend-filter` | off | Only enter when price is above its 200-day SMA |
| `--strategy` | — | If set, runs the options-aware backtest |
| `--output` | `print` | `print` (stdout) or `db` (save to SQLite) |
| `--iv-archive` | `iv_archive.db` | Path to the IV history database |
| `--csv` | — | Save the full trade log to a CSV file |

### Interpreting the options backtest output

The report shows two columns side by side: **Options P&L** and **Underlying
return** for the same signal months.

- **Avg entry premium %**: average option cost as % of spot at entry. A long
  call costing 2% needs the underlying to move more than 2% to break even.
- **Win rate (options)** is typically lower than the underlying win rate because
  theta decay means you can be right on direction but still lose if the move
  doesn't cover the premium.
- **Total return (compounded)** is the most informative single number: compare
  the options column to the underlying column to gauge the effect of leverage
  and theta cost.
- The **IV%** column in the trade detail shows the HV used as IV proxy at
  entry. Values above 30% mean expensive options and conservative long-premium P&L.

---

## server.py

FastAPI HTTP server with a built-in daily scheduler. Run it instead of (or
alongside) the CLI to get a web dashboard and automated daily screening.

```bash
# Development
uvicorn server:app --host 0.0.0.0 --port 8000 --workers 1
# → http://localhost:8000
```

> **Important:** always use `--workers 1`. Multiple workers each start their
> own scheduler instance, causing duplicate screening runs.

### Dashboard

Opening `http://localhost:8000` shows a single-page dashboard with:
- Sortable ranking table (click any column header to sort)
- Detail panel per ticker: seasonality table with colour-coded p-values,
  volatility/IV section, options analysis, Greeks
- IV history chart (requires 2+ daily runs to populate)

### Automatic daily screening

The scheduler runs the equivalent of `screener.py --output db` automatically
every weekday at the configured time (default 22:00 UTC). Configure via env vars:

| Env var | Default | Description |
|---|---|---|
| `TICKERS` | `GLD,XRT,EQT` | Comma-separated tickers to screen |
| `YEARS` | `5` | Years of history |
| `SCHEDULE_HOUR` | `22` | UTC hour for the daily run |
| `SCHEDULE_MIN` | `0` | UTC minute for the daily run |
| `IV_ARCHIVE_DB` | `iv_archive.db` | Path to the SQLite database |

### Manual trigger

To run screening immediately without waiting for the schedule:

```bash
curl -X POST http://localhost:8000/api/run
```

### API endpoints

| Endpoint | Description |
|---|---|
| `GET /api/results` | Latest screening run, all tickers sorted by score |
| `GET /api/results/{ticker}` | Score history for a specific ticker (last 90 days) |
| `GET /api/iv-history/{ticker}` | Stored IV history used for the chart |
| `GET /api/backtest/{ticker}` | Most recent backtest result for a ticker |
| `POST /api/run` | Triggers an immediate screening run in the background |

---

## Docker deployment

The project ships as a single image that acts as both the HTTP server and the
daily scheduler. Add it to an existing `docker-compose.yml` using the provided
snippet.

### Files in `deploy/`

| File | Purpose |
|---|---|
| `deploy/docker-compose.snippet.yml` | Service block to copy into your compose |
| `deploy/nginx.conf` | nginx `server {}` block (subdomain or sub-path variant) |

### Adding to an existing docker-compose

1. Build the image or let compose build it:
   ```yaml
   # excerpt from deploy/docker-compose.snippet.yml
   services:
     py-screener:
       build:
         context: ./py-screener
         dockerfile: Dockerfile
       restart: always
       environment:
         IV_ARCHIVE_DB: /data/iv_archive.db
         TICKERS: GLD,XRT,EQT,UNG
         YEARS: "5"
         SCHEDULE_HOUR: "22"
         SCHEDULE_MIN: "0"
       volumes:
         - screener_data:/data
       networks:
         - proxy   # same network as your nginx
   ```

2. Add the named volume `screener_data` and make sure the service is on the
   same Docker network as nginx.

3. Add an nginx location or server block from `deploy/nginx.conf`. The service
   is reachable internally as `http://py-screener:8000`.

4. Optionally add HTTP basic auth (recommended — the dashboard exposes portfolio
   data). See the comments in `deploy/nginx.conf`.

### First run

On first start the database is empty. The dashboard will show "No screening
results yet." Either wait for the scheduled run or trigger one immediately:

```bash
curl -X POST https://screener.yourdomain.com/api/run
```

---

## Recommended workflow

1. **Screen** with `screener.py` (or let the server do it automatically) to
   find tickers with a favorable seasonal signal and contained IV. Check the
   p-value and `n_obs` — a significant p-value on 4 observations is not useful.

2. **Review the strategy suggestion** in the Options analysis section. Verify
   that bias, IV level, and pricing ratio are consistent with your own view.

3. **Run the price-only backtest** to confirm the signal has an out-of-sample
   edge on the underlying over your desired lookback period.

4. **Run the options backtest** (`--strategy long-call` or whichever was
   suggested) to see whether the edge survives after accounting for premium and
   theta decay.

5. **Let the IV archive accumulate.** After 30+ daily runs the IV Rank replaces
   the HV proxy for a more accurate read on whether options are cheap or expensive.

---

## Limitations — read before trading

**HV ≠ IV.** Realized historical volatility is used as a proxy for implied
volatility throughout most of the tool. Real IV reflects market expectations and
can diverge significantly from HV, especially around earnings, macro events, or
regime shifts. The IV archive solves this over time but requires daily runs to
accumulate data.

**Options backtest uses HV as IV proxy.** The options-aware backtest prices
options with the 20-day realized HV, not the actual market IV on that date
(historical IV data is not freely available). The backtest underestimates premium
in high-IV regimes and overestimates it in low-IV regimes. Treat results as
directionally informative, not exact.

**ATM strike = entry spot.** The backtest assumes the option is struck exactly
at the spot price at entry. Real markets list discrete strikes; the nearest
available strike may add a small delta bias.

**No transaction costs.** Bid/ask spread, commissions, and slippage are not
modelled. For near-the-money options with wide spreads (common on illiquid ETFs),
actual P&L will be worse.

**Multiple testing.** Running 12 t-tests simultaneously (one per calendar month)
means approximately 0.6 false positives are expected at α=0.05 even with no real
edge. Always cross-check a significant month with enough observations (`n_obs`)
and the backtest before acting on it.

**Seasonality is a historical tendency, not a law.** With 5 years of data you
have at most 5 observations per month. Prefer `--years 10` or more for any
signal you intend to trade.

**This is an informational tool, not financial advice.** Use it as a starting
point for your own research, not as sufficient reason to open a position.
