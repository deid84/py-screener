# Seasonality + Volatility Screener for Options

A command-line tool that, for a list of tickers, computes:

1. **Monthly historical seasonality** — average return, standard deviation, and win rate for each month, over the full available history.
2. **Realized historical volatility** and its current percentile, as a proxy for how "expensive" options are likely to be right now compared to the ticker's own past.
3. **Live IV snapshot** from the options chain (ATM call/put for the next available expiries).
4. A **final ranking** of the analyzed tickers, based on a simple score combining expected seasonality and volatility "discount".

## Installation

```bash
pip install -r requirements.txt
```

Requires Python 3.9+ and an active internet connection (data is downloaded from Yahoo Finance via the `yfinance` library).

## Usage

```bash
python screener.py --tickers GLD,XRT,EQT,UNG --years 5
```

Available options:

- `--tickers` (required): comma-separated list of tickers.
- `--years`: years of history to analyze (default 5). More years = more robust estimate, but slower to download.
- `--no-options`: skip the live options chain fetch (faster; useful if you only want seasonality).
- `--csv filename.csv`: also save the final ranking to a CSV file.

Quick example, seasonality only over 10 years:

```bash
python screener.py --tickers AAPL,MSFT,NVDA --years 10 --no-options
```

## How to read the output

For each ticker you will see:

- The full seasonality table, sorted from the historically best to worst month, with a reliability flag for the current month (e.g. "very small sample", "consistent pattern").
- The current realized historical volatility and its percentile over the analyzed period.
- The live IV snapshot from the options chain (if available for that ticker).
- A combined score, used only to rank tickers against each other in the final ranking.

## Methodological limitations — read before using results for investing

**The score is not a trading signal.** It is a number built ad-hoc to rank the input tickers relative to one another. It has no statistical validation of predictive robustness.

**Seasonality is a historical tendency, not a law.** With only a few years of data (e.g. 5), a single anomalous month can heavily skew the average. Always check `n_oss` (number of observations) and the standard deviation relative to the mean: if the standard deviation is larger than the mean, the pattern is likely statistical noise, not a real effect.

**"Realized historical volatility" is NOT implied volatility (IV).** This script has no access to an IV history (yfinance does not provide it for free). It uses the past realized volatility of the underlying as an approximate proxy for how "cheap" options are today. Real IV — what actually determines option prices — reflects the market's expectations about the future and can diverge significantly from historical volatility, especially around known events such as earnings or macro data releases. For a "true" IV percentile you would need a professional data source with IV history (e.g. a broker like IBKR, or a paid data provider).

**The options chain snapshot is just a photograph.** It shows the situation at the time the script is run, not a history. Always verify live bid/ask on your broker before placing an order — yfinance data may have delays or small discrepancies compared to the real order book.

**No P&L backtest.** This tool only performs descriptive screening (seasonality + volatility); it does not simulate executing an options strategy over time, nor does it calculate Sharpe ratio or drawdown. If you want to validate an idea more rigorously, the natural next step would be to build a proper backtest on historical options data, not just the underlying.

**This is an informational tool, not financial advice.** It should be used as a starting point for your own research, not as sufficient reason to open a position.

## File structure

```
options_screener/
├── screener.py        # main script, CLI
├── seasonality.py     # monthly seasonality computation
├── volatility.py      # realized volatility + live IV snapshot
├── requirements.txt
└── README.md
```

## Possible future extensions

- Save a daily IV snapshot to gradually build a personal IV history over time (currently impossible due to the lack of free historical IV data).
- Add a real options strategy backtest (e.g. simulate buying an OTM call every year in the same month and compute the actual historical P&L).
- Extend correlation analysis across the selected tickers, to avoid unknowingly concentrating risk on a single macro factor (e.g. multiple tickers all tied to natural gas prices).
