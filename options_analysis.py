"""
options_analysis.py
Options-specific analysis: expected move from IV and strategy suggestion
based on the combination of seasonal directional bias and IV level.

Expected move formula (1-sigma, 68% probability range):
    EM% = IV × √(DTE / 365)

The ratio EM% / |seasonal_avg%| tells you whether the options market is
pricing in more or less movement than the historical seasonal pattern:
  < 1.0  — options cheap relative to the pattern → favour buying premium
  1–2.0  — fairly priced range
  > 2.0  — options expensive relative to the pattern → favour selling premium
"""
import math
from datetime import date


def compute_expected_move(spot: float, iv_pct: float, expiry: str) -> dict:
    """
    Computes the market's expected 1-sigma price move to the given expiry.

    Parameters
    ----------
    spot    : current spot price
    iv_pct  : ATM implied volatility in percent (e.g. 28.5 for 28.5%)
    expiry  : expiry date as ISO string "YYYY-MM-DD"

    Returns a dict with dte, expected_move_pct, expected_move_dollar,
    and the implied 1-sigma range [range_low, range_high].
    """
    today = date.today()
    try:
        exp_date = date.fromisoformat(expiry)
    except ValueError:
        return {"error": f"cannot parse expiry date: {expiry}"}

    dte = (exp_date - today).days
    if dte <= 0:
        return {"error": "expiry already passed"}

    em_pct = iv_pct * math.sqrt(dte / 365)
    em_dollar = spot * em_pct / 100

    return {
        "dte": dte,
        "expiry": expiry,
        "expected_move_pct": round(em_pct, 2),
        "expected_move_dollar": round(em_dollar, 2),
        "range_low": round(spot - em_dollar, 2),
        "range_high": round(spot + em_dollar, 2),
    }


def _iv_level(iv_rank_or_hv_pct: float | None) -> str:
    """Translates a percentile value (0-100) into low / normal / high."""
    if iv_rank_or_hv_pct is None:
        return "normal"
    if iv_rank_or_hv_pct < 25:
        return "low"
    if iv_rank_or_hv_pct > 75:
        return "high"
    return "normal"


# Strategy matrix: (directional_bias, iv_level) → (name, rationale, structure hint)
_STRATEGIES = {
    ("bullish", "low"): (
        "Long Call / Debit Call Spread",
        "bullish seasonal pattern + cheap options → buy directional premium",
        "Buy ATM call (or buy ATM call / sell OTM call to reduce cost)",
    ),
    ("bullish", "normal"): (
        "Short Put",
        "bullish seasonal pattern + normal IV → short put collects theta while staying directionally long",
        "Sell OTM put at a strike you are comfortable owning the underlying",
    ),
    ("bullish", "high"): (
        "Short Put / Cash-Secured Put",
        "bullish seasonal pattern + expensive options → sell elevated premium in the expected direction",
        "Sell ATM or slightly OTM put; consider put spread to cap risk",
    ),
    ("bearish", "low"): (
        "Long Put / Debit Put Spread",
        "bearish seasonal pattern + cheap options → buy directional premium",
        "Buy ATM put (or buy ATM put / sell OTM put to reduce cost)",
    ),
    ("bearish", "normal"): (
        "Short Call",
        "bearish seasonal pattern + normal IV → short call collects theta while staying directionally short",
        "Sell OTM call above a resistance level",
    ),
    ("bearish", "high"): (
        "Short Call / Bear Call Spread",
        "bearish seasonal pattern + expensive options → sell elevated premium in the expected direction",
        "Sell ATM or slightly OTM call; buy further OTM call as hedge",
    ),
    ("neutral", "low"): (
        "Long Straddle / Long Strangle",
        "no clear directional edge + cheap options → buy volatility, profit from any large move",
        "Buy ATM call and ATM put (straddle), or slightly OTM call and put (strangle)",
    ),
    ("neutral", "normal"): (
        "No clear edge — consider skipping",
        "no strong seasonal bias and normal IV: risk/reward unattractive",
        "Wait for a clearer seasonal signal or a significant IV dislocation",
    ),
    ("neutral", "high"): (
        "Iron Condor / Short Strangle",
        "no directional bias + expensive options → sell volatility, profit from range-bound behaviour",
        "Sell OTM call and OTM put (strangle), then buy further OTM wings to define risk (iron condor)",
    ),
}


def suggest_strategy(
    seasonal_avg_pct: float,
    seasonal_win_rate: float,
    iv_rank_or_hv_pct: float | None,
    expected_move: dict | None = None,
) -> dict:
    """
    Suggests an options strategy based on seasonal bias and IV level.

    Parameters
    ----------
    seasonal_avg_pct     : historical average monthly return for this month (%)
    seasonal_win_rate    : historical win rate for this month (%)
    iv_rank_or_hv_pct    : IV Rank or HV percentile (0-100); used to classify IV as low/normal/high
    expected_move        : output of compute_expected_move (optional, used for pricing ratio)

    Returns a dict with bias, iv_level, strategy name, rationale, structure, and
    optionally a pricing_ratio (options EM / seasonal avg).
    """
    # Directional bias
    if seasonal_avg_pct > 0.5 and seasonal_win_rate > 55:
        bias = "bullish"
    elif seasonal_avg_pct < -0.5 and seasonal_win_rate < 45:
        bias = "bearish"
    else:
        bias = "neutral"

    iv_lvl = _iv_level(iv_rank_or_hv_pct)
    name, rationale, structure = _STRATEGIES[(bias, iv_lvl)]

    result = {
        "bias": bias,
        "iv_level": iv_lvl,
        "strategy": name,
        "rationale": rationale,
        "structure": structure,
    }

    # Pricing ratio: how many times the EM covers the seasonal expected move
    if (expected_move and "expected_move_pct" in expected_move
            and abs(seasonal_avg_pct) > 0.1):
        ratio = expected_move["expected_move_pct"] / abs(seasonal_avg_pct)
        result["pricing_ratio"] = round(ratio, 1)
        if ratio < 1.0:
            result["pricing_note"] = "options price in LESS than the historical move → premium looks cheap"
        elif ratio > 2.0:
            result["pricing_note"] = "options price in MORE than 2× the historical move → premium looks expensive"
        else:
            result["pricing_note"] = "options fairly priced relative to the historical seasonal move"

    return result
