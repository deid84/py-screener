# py-screener — Seasonality + Volatility Screener for Options

A command-line toolkit that combines historical seasonality analysis, volatility
assessment, and options-specific tools to help identify and evaluate monthly
options setups on a given list of tickers.

---

## What it does

| Module | Purpose |
|---|---|
| `screener.py` | Screens tickers: seasonality, IV, Greeks, skew, expected move, strategy suggestion |
| `backtest.py` | Walk-forward backtest of the seasonal signal — price-only or options-aware (Black-Scholes) |
| `seasonality.py` | Computes monthly return statistics + t-test significance |
| `volatility.py` | Realized HV percentile + live ATM IV snapshot with Greeks and skew |
| `options_analysis.py` | Expected move, strategy selector, Black-Scholes pricing and Greeks |
| `iv_archive.py` | Stores daily IV snapshots in a local SQLite database to build IV Rank over time |

---

## Installation

Requires **Python 3.10+** and an internet connection (data from Yahoo Finance via `yfinance`).

```bash
python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

---

## screener.py

Screens one or more tickers and prints a detailed report for each one, followed
by a comparative ranking.

```bash
python screener.py --tickers GLD,XRT,EQT,UNG --years 5
python screener.py --tickers AAPL --years 10 --no-options
python screener.py --tickers GLD,XRT --years 5 --csv ranking.csv
```

### Flags

| Flag | Default | Description |
|---|---|---|
| `--tickers` | required | Comma-separated list of tickers (e.g. `GLD,XRT,EQT`) |
| `--years` | `5` | Years of price history to download |
| `--no-options` | off | Skip the live options chain fetch (faster; seasonality + HV only) |
| `--iv-archive` | `iv_archive.db` | Path to the IV history database |
| `--csv` | — | Save the final ranking table to a CSV file |

### Output sections (per ticker)

**Current and next month seasonality**
Shows the historical average return, win rate, number of observations, and a
statistical significance flag for the current and next calendar month.

The significance flag comes from a one-sample t-test (H₀: avg return = 0):
- `significant (p=0.021)` — the pattern is unlikely to be random noise
- `marginal (p=0.08)` — borderline, treat with caution
- `not significant (p=0.45)` — no reliable edge in this month's history

**Full seasonality table**
All 12 months ranked from best to worst, with `avg_pct`, `std_pct`, `n_obs`,
`win_rate_pct`, and the t-test `p_value`. Use `n_obs` and `p_value` together:
a month with `n_obs=4` has too little data regardless of p-value.

**Realized historical volatility (HV)**
The current 20-day realized volatility and its percentile relative to the full
downloaded history. This is a **proxy** for IV — see Limitations below.

**Live IV snapshot**
ATM call and put for the next 1–2 available expiries: IV, bid/ask, and the
computed Greeks (Delta, Gamma, Theta per day, Vega per 1% IV move).

Also shows the **skew** (put IV − call IV at the same ATM strike). A positive
skew means the market is paying more for put protection, which is typical for
equities and risk-off assets.

**IV Rank / IV Percentile** *(available after 30+ daily runs)*
Once the local archive has accumulated enough snapshots, the report shows:
- **IV Rank** = (current IV − period low) / (period high − period low) × 100
- **IV Percentile** = % of stored days where IV was below today's level

These are more accurate than the HV proxy because they reflect actual market
pricing, not past price movements. The archive grows automatically every time
you run the screener with options enabled.

**Options analysis**
- **Expected move** = IV × √(DTE/365), expressed as ±% and ±$ with the
  implied 1-sigma price range.
- **Pricing ratio** = expected move / |seasonal avg|. A ratio below 1 means
  options are pricing in less movement than history suggests (cheap for buyers);
  above 2 means options are pricing in more than twice the historical move
  (expensive, favours sellers).
- **Strategy suggestion**: derived from the combination of seasonal directional
  bias (bullish / bearish / neutral) and IV level (low / normal / high):

  | Bias | IV low | IV normal | IV high |
  |---|---|---|---|
  | Bullish | Long Call / Debit Spread | Short Put | Short Put / CSP |
  | Bearish | Long Put / Debit Spread | Short Call | Short Call / Spread |
  | Neutral | Long Straddle / Strangle | No clear edge | Iron Condor / Strangle |

  Each suggestion includes a rationale and a structure hint.

---

## backtest.py

Walk-forward backtest of the seasonal signal. For each test month, seasonality
(and HV, for the options mode) is computed **exclusively on data preceding that
month**, eliminating lookahead bias.

### Price-only backtest (default)

Simulates entering long on the underlying at the first close of the month and
exiting at the last close. Useful as a baseline to confirm whether the seasonal
signal has any edge on the underlying before layering in options complexity.

```bash
python backtest.py --tickers GLD,XRT --years 10
python backtest.py --tickers GLD --years 10 --trend-filter
```

### Options-aware backtest (`--strategy`)

Prices an ATM European option at month entry using **Black-Scholes with the
20-day realized HV as the IV proxy**, holds to month-end expiry, and records
the P&L. Results are expressed as % of spot for direct comparison with the
underlying return.

```bash
python backtest.py --tickers GLD --years 10 --strategy long-call
python backtest.py --tickers XRT --years 10 --strategy short-put --trend-filter
python backtest.py --tickers GLD,XRT --years 10 --strategy long-call --csv bt_options.csv
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
| `--csv` | — | Save the full trade log to a CSV file |

### Interpreting the options backtest output

The report shows two columns side by side: **Options P&L** and **Underlying
return** for the same set of signal months.

- **Avg entry premium %**: how much of the spot price you pay in premium on
  average. A long call costing 2% of spot needs the underlying to move more
  than 2% just to break even.
- **Win rate (options)** is typically lower than the underlying win rate,
  because theta decay means you can be right on direction but still lose if the
  move is too small to cover the premium.
- **Total return (compounded)** is the most informative single number: compare
  the options column to the underlying column to see how much the leverage and
  theta cost affects the actual outcome.
- The **IV%** column in the trade detail shows the HV used as IV proxy at
  entry. High values (>30%) mean expensive options and a more conservative
  long-premium P&L.

---

## Recommended workflow

1. **Screen** with `screener.py` to identify tickers with a favorable current
   or next-month seasonal signal and contained IV. Note the p-value and IV
   level in the report.

2. **Check the strategy suggestion** in the Options analysis section. Verify
   that the bias, IV level, and pricing ratio are consistent with your own view.

3. **Validate with the price-only backtest** (`backtest.py --tickers TICKER`)
   to confirm the seasonal signal has a real out-of-sample edge on the
   underlying over your desired lookback period.

4. **Validate with the options backtest** (`--strategy long-call` or whichever
   strategy was suggested) to see whether the edge survives after accounting
   for option premiums and theta decay.

5. **Check the IV archive** counter in the screener output. Once you have 30+
   observations, the IV Rank replaces the HV proxy for a more accurate read
   on whether options are cheap or expensive.

---

## Limitations — read before trading

**HV ≠ IV.** The realized historical volatility (HV) is used as a proxy for
implied volatility throughout most of the tool (screener ranking, options
backtest, strategy selector fallback). Real IV reflects market expectations
about the future and can diverge significantly from HV, especially around
earnings, macro events, or regime shifts. The IV archive solves this over time,
but requires daily runs to accumulate.

**Options backtest uses HV as IV proxy.** The options-aware backtest prices
options with the 20-day realized HV, not the actual market IV on that date
(historical IV data is not available for free). This means the backtest
underestimates premium in high-IV regimes and overestimates it in low-IV
regimes. Treat results as directionally informative, not exact.

**ATM strike = entry spot.** The backtest assumes the option is struck exactly
at the spot price at month entry. Real markets only list discrete strikes; the
nearest available strike may add a few cents of delta bias.

**No transaction costs.** Bid/ask spread, commissions, and slippage are not
modelled. For near-the-money options with wide spreads (common on illiquid
ETFs), actual P&L will be worse.

**Seasonality is a historical tendency, not a law.** With 5 years of data you
have at most 5 observations per month. Always check `n_obs` and `p_value`
together: a significant p-value on 4 observations is not reliable. Prefer
`--years 10` or more.

**This is an informational tool, not financial advice.** Use it as a starting
point for your own research, not as sufficient reason to open a position.
