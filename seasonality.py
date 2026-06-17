"""
seasonality.py
Computes historical seasonality statistics (average monthly return,
win rate, standard deviation) for a ticker, from daily price history.
"""
import pandas as pd

MONTH_NAMES = {
    1: "Jan", 2: "Feb", 3: "Mar", 4: "Apr", 5: "May", 6: "Jun",
    7: "Jul", 8: "Aug", 9: "Sep", 10: "Oct", 11: "Nov", 12: "Dec",
}


def compute_monthly_seasonality(price_df: pd.DataFrame) -> pd.DataFrame:
    """
    price_df: DataFrame with a 'Close' column indexed by DatetimeIndex
    (e.g. output of yfinance.download with daily data).

    Returns a DataFrame indexed by month (Jan..Dec) with columns:
    avg_pct, std_pct, n_obs, n_positive, win_rate_pct
    Sorted from the historically best to worst month.
    """
    df = price_df.copy()
    df["year"] = df.index.year
    df["month"] = df.index.month

    # approximate monthly return: first close vs last close of the month
    monthly = df.groupby(["year", "month"])["Close"].agg(["first", "last"])
    monthly["ret_pct"] = (monthly["last"] / monthly["first"] - 1) * 100
    monthly = monthly.reset_index()

    stats = monthly.groupby("month")["ret_pct"].agg(
        avg_pct="mean",
        std_pct="std",
        n_obs="count",
    )
    stats["n_positive"] = monthly.groupby("month")["ret_pct"].apply(lambda x: (x > 0).sum())
    stats["win_rate_pct"] = (stats["n_positive"] / stats["n_obs"] * 100).round(1)
    stats["avg_pct"] = stats["avg_pct"].round(2)
    stats["std_pct"] = stats["std_pct"].round(2)

    # months missing from the dataset (e.g. ticker too recent) are dropped
    stats.index = [MONTH_NAMES[m] for m in stats.index]
    stats.index.name = "month"
    return stats.sort_values("avg_pct", ascending=False)


def best_and_worst_months(stats: pd.DataFrame, n: int = 3):
    """Returns (best_n, worst_n) as separate DataFrames."""
    best = stats.sort_values("avg_pct", ascending=False).head(n)
    worst = stats.sort_values("avg_pct", ascending=True).head(n)
    return best, worst


def reliability_flag(row: "pd.Series | pd.DataFrame") -> str:
    """
    Qualitative flag on the statistical robustness of the seasonal pattern
    for a single month. A small sample or a standard deviation larger than
    the mean indicate an unreliable pattern.
    """
    if row["n_obs"] < 5:
        return "very small sample"
    if abs(row["std_pct"]) > abs(row["avg_pct"]) * 2:
        return "high noise relative to signal"
    if row["win_rate_pct"] >= 70 or row["win_rate_pct"] <= 30:
        return "consistent pattern"
    return "weak/mixed pattern"
