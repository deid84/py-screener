"""
iv_archive.py
Stores historical IV snapshots in a local SQLite database and computes
IV Rank / IV Percentile once enough history has accumulated.

Why this matters: yfinance has no IV history. The only way to build one
is to save today's snapshot every time the screener runs. After 30+ days
you get a meaningful IV Rank; after a year you have a proper IV Percentile.

Storage: a single file `iv_archive.db` in the project directory (gitignored).

IV Rank     = (current_iv - min_iv_period) / (max_iv_period - min_iv_period) * 100
IV Percentile = % of stored days where iv < current_iv
"""
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

DEFAULT_DB = "iv_archive.db"


def _connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS iv_snapshots (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            date        TEXT    NOT NULL,
            ticker      TEXT    NOT NULL,
            expiry      TEXT    NOT NULL,
            spot        REAL,
            strike_atm  REAL,
            iv_call_pct REAL,
            iv_put_pct  REAL,
            iv_mid_pct  REAL,
            volume_call INTEGER,
            volume_put  INTEGER
        )
    """)
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_unique_snapshot "
        "ON iv_snapshots(date, ticker, expiry)"
    )
    conn.commit()
    return conn


def save_snapshot(ticker: str, snapshots: list, db_path: str = DEFAULT_DB):
    """
    Saves IV snapshots (output of fetch_atm_iv_snapshot) to the archive.
    Only the nearest expiry is stored to keep the time series clean.
    Duplicate entries for the same date+ticker+expiry are silently ignored.
    """
    if not snapshots:
        return

    conn = _connect(db_path)
    today = datetime.utcnow().strftime("%Y-%m-%d")

    snap = snapshots[0]  # nearest expiry only
    iv_mid = round((snap["iv_call_pct"] + snap["iv_put_pct"]) / 2, 2)
    try:
        conn.execute("""
            INSERT OR IGNORE INTO iv_snapshots
            (date, ticker, expiry, spot, strike_atm,
             iv_call_pct, iv_put_pct, iv_mid_pct, volume_call, volume_put)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            today, ticker, snap["expiry"],
            snap.get("spot"), snap.get("strike_atm"),
            snap["iv_call_pct"], snap["iv_put_pct"], iv_mid,
            snap.get("volume_call", 0), snap.get("volume_put", 0),
        ))
        conn.commit()
    finally:
        conn.close()


def load_iv_history(ticker: str, days: int = 365, db_path: str = DEFAULT_DB) -> list[tuple]:
    """
    Returns a list of (date, iv_mid_pct) tuples for the ticker,
    going back `days` calendar days, sorted by date ascending.
    Returns an empty list if the archive doesn't exist yet.
    """
    if not Path(db_path).exists():
        return []

    conn = _connect(db_path)
    cutoff = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d")
    try:
        rows = conn.execute(
            "SELECT date, iv_mid_pct FROM iv_snapshots "
            "WHERE ticker = ? AND date >= ? ORDER BY date ASC",
            (ticker, cutoff),
        ).fetchall()
    finally:
        conn.close()
    return rows


def compute_iv_rank(
    ticker: str,
    current_iv: float,
    days: int = 365,
    db_path: str = DEFAULT_DB,
) -> dict | None:
    """
    Computes IV Rank and IV Percentile from the stored history.

    Returns None when fewer than 30 observations are available —
    not enough history to be meaningful.

    IV Rank      = (current - min) / (max - min) * 100
    IV Percentile = % of observations strictly below current IV
    """
    history = load_iv_history(ticker, days, db_path)
    ivs = [v for _, v in history if v is not None]

    if len(ivs) < 30:
        return {
            "available": False,
            "n_observations": len(ivs),
            "min_required": 30,
        }

    lo, hi = min(ivs), max(ivs)
    iv_rank = round((current_iv - lo) / (hi - lo) * 100, 1) if hi != lo else 50.0
    iv_pct = round(sum(1 for v in ivs if v < current_iv) / len(ivs) * 100, 1)

    return {
        "available": True,
        "iv_rank": iv_rank,
        "iv_percentile": iv_pct,
        "n_observations": len(ivs),
        "iv_min_period": round(lo, 1),
        "iv_max_period": round(hi, 1),
        "period_days": days,
    }
