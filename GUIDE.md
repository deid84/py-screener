# Interpretation Guide — seasonal-screener

This document explains how to read every section of the dashboard and CLI output.
It is not a technical guide to the code: it is an operational manual for deciding
whether and how to act on a signal.

---

## Table of contents

1. [The ranking — how the score is calculated](#1-the-ranking)
2. [Seasonality — avg, win rate, significance, consistency](#2-seasonality)
3. [Volatility — HV percentile, IV Rank, IV Percentile](#3-volatility)
4. [Suggested strategy — the 3×3 matrix](#4-suggested-strategy)
5. [Technicals — trend bias and alignment](#5-technicals)
6. [Earnings warning](#6-earnings-warning)
7. [Practical workflow — from data to decision](#7-practical-workflow)
8. [Real examples with commentary](#8-real-examples)
9. [Signals to skip](#9-signals-to-skip)

---

## 1. The ranking

The **score** at the top of the list aggregates multiple factors:

- Seasonal signal strength (avg_pct, win rate)
- Statistical robustness (adjusted p-value)
- Volatility context (HV percentile)
- Technical alignment (trend alignment)

**The ranking is a starting point, not a trade list.**
It orders tickers by "worth investigating", not by "buy now".

A ticker with a high score but `not significant` and `mixed` consistency should
still be skipped. The score helps decide where to start reading, nothing more.

---

## 2. Seasonality

### avg_pct — Average historical monthly return

The mean return for that calendar month computed across all available years
(typically 10–15 years). Example: `+2.24%` for XLU in July means that
historically XLU has returned +2.24% on average during July.

> **This is not a forecast.** It is the historical average. The current month
> can behave very differently.

### win_rate — Percentage of positive years

How many times that month closed positive out of the total years available.
`80%` means 12 out of 15 years closed in the green.

| Win rate | Interpretation |
|----------|----------------|
| ≥ 70% | Strong directional pattern |
| 55–69% | Slight directional edge, not sufficient alone |
| 45–54% | Neutral, no directional preference |
| ≤ 30% | Strong bearish pattern |

### significance — Statistical reliability (t-test + BH correction)

The t-test checks whether avg_pct is statistically different from zero — i.e.,
whether the pattern cannot be explained by randomness alone. The
Benjamini-Hochberg (BH) correction adjusts the p-values because we test
12 months simultaneously (testing 12 months at random would produce on average
~0.6 false positives at α=0.05).

| Flag | p_adj | Meaning |
|------|-------|---------|
| `significant` | < 0.05 | Pattern is statistically robust |
| `marginal` | 0.05–0.10 | Weak signal, use with caution |
| `not significant` | > 0.10 | Cannot rule out randomness |

**With 15 years of data (15 observations per month) it is normal for most months
to show `not significant`.** The t-test has low statistical power with small
samples. A `not significant` month is not useless: if it has a win rate > 70%
and `consistent` consistency, it is still a valid signal even without formal
significance.

### consistency — Stability over time

Splits the history into two equal halves and checks whether the pattern is
coherent across both.

| Value | Meaning |
|-------|---------|
| `consistent` | Same direction and win rate side (> or ≤ 50%) in both halves |
| `mixed` | Pattern changes between the first and second half of history |
| `insufficient` | Too few data points for comparison |

> With 15 years each half has ~7–8 observations per month.
> `mixed` is common and not necessarily fatal — read it together with win rate
> and significance.

### Combining these three indicators

```
high avg_pct + win rate ≥ 70% + consistent    →  strong signal
high avg_pct + win rate ≥ 70% + significant   →  strong confirmed signal
high avg_pct + win rate ≥ 60% + not significant  →  weak signal, needs technical confirmation
high avg_pct + win rate < 55%                 →  skip, too noisy
```

---

## 3. Volatility

### HV percentile — Historical realized volatility

The current realized volatility (20-day rolling, annualized) relative to its
own history. `95th` means current volatility is higher than 95% of past values —
options are historically expensive.

| HV percentile | Interpretation |
|---------------|----------------|
| < 25th | Historically low IV — options are cheap |
| 25th–50th | Normal, slight low bias |
| 50th–75th | Normal, slight high bias |
| > 75th | Historically high IV — options are expensive |

> **Note:** HV (Historical Volatility) is a proxy for IV. It is not the same
> figure shown on IBKR or Tastytrade. They diverge especially around specific
> events (earnings, macro releases). Use it as a first filter, not as a
> definitive measure.

### IV Rank and IV Percentile

Available only after 30+ daily runs (once per day, Monday–Friday).
Until then the system shows `building history…`.

- **IV Rank**: where the current IV sits within the min–max range of the past
  252 trading days. `80` = current IV is at 80% of the historical range.
- **IV Percentile**: how many times in the past 252 days IV was lower than today.
  `80` = IV was lower 80% of the time.

Once available, these metrics replace the HV percentile for determining the IV
level in the strategy matrix.

---

## 4. Suggested strategy

The strategy is determined by a **seasonal bias × IV level** matrix:

|               | Low IV | Normal IV | High IV |
|---------------|--------|-----------|---------|
| **Bullish**   | Long Call | Bull Call Spread | Short Put |
| **Neutral**   | Long Straddle | Iron Condor | Short Strangle |
| **Bearish**   | Long Put | Bear Put Spread | Short Call |

### Seasonal bias

Derived from avg_pct and win rate for the current month:
- `bullish` → avg_pct > 0 and win rate > 55%
- `bearish` → avg_pct < 0 and win rate < 45%
- `neutral` → everything else

### IV level

- `low` → HV percentile < 40th (or IV Rank < 25 when available)
- `high` → HV percentile > 60th (or IV Rank > 75 when available)
- `normal` → everything else

### Expected move

The 1σ expected move estimates how far the underlying is likely to move by
expiry, based on ATM IV:

```
Expected move = Spot × IV_ATM × √(DTE / 365)
```

Example: GLD at 230, IV = 18%, DTE = 30 → expected move ≈ ±12.1

### Pricing ratio

`option_price / expected_move_1σ`. A ratio > 1 means the premium is higher
than the expected move — the option is expensive relative to implied volatility.

---

## 5. Technicals

Technical indicators confirm or contradict the seasonal bias.
They are not independent signals: they serve as an additional filter only.

| Indicator | What it measures |
|-----------|-----------------|
| MA50 / MA200 | Short and long-term trend |
| RSI(14) | Momentum (overbought > 70, oversold < 30) |
| 52w range % | Where price sits within its annual high/low range |
| trend_bias | Summary: bullish / bearish / neutral |

### Trend alignment

| Alignment | Operational meaning |
|-----------|---------------------|
| `ALIGNED` | Technical and seasonal agree → stronger signal |
| `DIVERGENT` | Technical and seasonal contradict → caution, weakened signal |
| `NEUTRAL` | One or both are neutral → no additional confirmation |

A bullish seasonal signal with a bearish technical reading (`DIVERGENT`) is
worth less than one with a bullish reading (`ALIGNED`). It does not cancel
the signal but calls for more caution on timing.

---

## 6. Earnings warning

For individual stocks, the system warns if earnings fall within 45 days.
ETFs do not have earnings dates, so the filter does not apply to them.

⚠ **Earnings warning** — if it appears, consider waiting until after the event
or using a structure that handles post-earnings IV crush.

---

## 7. Practical workflow

The recommended flow each time you open the dashboard:

### Step 1 — Filter for the current month

Look only at the current month in the "Current month" column. Future months
are informational but not yet actionable.

### Step 2 — Remove weak signals

Drop tickers with any of the following:
- win rate < 55% for the current month
- avg_pct < +0.5% (bullish) or > −0.5% (bearish)
- consistency `mixed` **and** significance `not significant` at the same time

### Step 3 — Assess volatility

For selling strategies (Short Put, Short Call, Iron Condor):
- prefer HV percentile > 60th — sell options when they are expensive
- avoid HV < 25th for selling strategies

For buying strategies (Long Call, Long Put, Straddle):
- prefer HV percentile < 40th — buy options when they are cheap

### Step 4 — Check technical alignment

`ALIGNED` → proceed with the suggested strategy  
`NEUTRAL` → proceed but with reduced size  
`DIVERGENT` → wait or skip  

### Step 5 — Check liquidity

If the `⚠ ILLIQUID` tag appears (bid-ask spread > 15% of mid), consider moving
to the next ticker or using a different expiry.

### Step 6 — Check earnings (stocks only)

If the earnings warning appears within 45 days, assess whether the strategy
survives the post-event IV compression.

### Step 7 — Size the position

The screener does not suggest position size. Apply your standard risk management.

---

## 8. Real examples

### XLU — July

```
Jul  +2.24%  80%  not significant (p_adj=0.150)  HV 58.2th  Short Put
```

- avg_pct +2.24%, win rate 80%: solid bullish pattern
- not significant at 5% (p_adj=0.150) but marginal — acceptable with 15 observations
- HV 58th: volatility in the upper-normal range, Short Put makes sense
- **Assessment:** usable signal if technicals are ALIGNED or NEUTRAL

### SLV — July

```
Jul  +4.47%  66.7%  not significant (p_adj=0.649)  HV 95.5th  Short Put
```

- avg_pct looks attractive (+4.47%) but p_adj=0.649: high variance in monthly
  returns, the pattern is noisy despite the high average
- HV 95th: very high volatility — options are expensive and collect high premium,
  but the risk of a large move is correspondingly high
- **Assessment:** high p_adj calls for caution. Consider smaller size or a
  credit spread to cap directional risk.

### UNG — July

```
Jul  +0.65%  26.7%  not significant (p_adj=0.916)  HV 40.2th  No clear edge
```

- avg_pct near zero and win rate 26.7%: this month is historically **bearish**
  (wins only 26.7% of the time), the positive average (+0.65%) is likely pulled
  up by a few large outlier years
- p_adj=0.916: no statistical evidence of a pattern
- HV 40th: normal, slightly low volatility
- **Assessment:** skip this month. Look at August (win rate 73.3%, p_adj=0.117)
  as a potential signal to position by end of July.

### GLD — July

```
Jul  +1.87%  66.7%  not significant (p_adj=0.574)  HV 95.1th  Short Put
```

- avg_pct decent, win rate 66.7%: bullish but not a strong pattern
- HV 95th: very high volatility
- **Assessment:** high IV justifies the Short Put for the premium collected,
  but the seasonal signal is weak (high p_adj). Use a wider OTM Short Put than
  usual to account for residual volatility risk.

---

## 9. Signals to skip

Some patterns appear frequently but do not warrant a trade:

| Situation | Why to skip |
|-----------|-------------|
| Win rate > 70% but avg_pct < 0.5% | Historical move too small to cover spread and slippage |
| High avg_pct but win rate < 55% | A few outsized years are distorting the mean |
| p_adj > 0.50 and consistency `mixed` | Both quality indicators are negative |
| HV < 30th with a selling strategy | Premium is too low for the risk/reward |
| DIVERGENT + not significant | Technical and seasonal contradict each other, neither is reliable |
| Any signal tagged `⚠ ILLIQUID` | The spread eats the premium advantage |

---

*Last updated July 2026. For updates to the codebase or analytical modules,
see [README.md](README.md).*
