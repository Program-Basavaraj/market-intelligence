"""Quantitative risk/return statistics for one stock.

All statistics are HISTORICAL descriptions of past returns, with confidence intervals.
They are not forecasts, and they are kept separate from model probabilities.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
from scipy import stats

TRADING_DAYS = 252


def wilson_interval(successes: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (float("nan"), float("nan"))
    p = successes / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (centre - half, centre + half)


def max_drawdown(close: pd.Series) -> dict:
    peak = close.cummax()
    dd = close / peak - 1
    trough = dd.idxmin()
    start = close.loc[:trough].idxmax()
    return {"max_drawdown_pct": round(float(dd.min()) * 100, 2), "peak_date": str(start.date()),
            "trough_date": str(trough.date()), "current_drawdown_pct": round(float(dd.iloc[-1]) * 100, 2)}


def var_cvar(returns: pd.Series, level: float = 0.95) -> dict:
    r = returns.dropna()
    q = float(np.quantile(r, 1 - level))
    tail = r[r <= q]
    mu, sd = float(r.mean()), float(r.std(ddof=1))
    z = stats.norm.ppf(1 - level)
    s, k = float(stats.skew(r)), float(stats.kurtosis(r))  # excess kurtosis
    zcf = z + (z**2 - 1) * s / 6 + (z**3 - 3 * z) * k / 24 - (2 * z**3 - 5 * z) * s**2 / 36
    return {"historical_var_pct": round(-q * 100, 3), "historical_cvar_pct": round(-float(tail.mean()) * 100, 3),
            "normal_var_pct": round(-(mu + z * sd) * 100, 3),
            "cornish_fisher_var_pct": round(-(mu + zcf * sd) * 100, 3), "level": level}


def horizon_stats(close: pd.Series, h: int, years: int = 3) -> dict:
    """Empirical distribution of non-overlapping-start h-day returns (last `years` years)."""
    c = close.tail(years * TRADING_DAYS + h)
    fwd = (c.shift(-h) / c - 1).dropna()
    if len(fwd) < 60:
        return {"horizon_days": h, "available": False}
    sample = fwd.iloc[::h]   # non-overlapping, so the n used in the CI is honest
    pos = int((sample > 0).sum())
    lo, hi = wilson_interval(pos, len(sample))
    boot = np.random.default_rng(42).choice(sample.to_numpy(), size=(2000, len(sample)), replace=True).mean(axis=1)
    return {
        "horizon_days": h, "available": True, "n_independent": int(len(sample)),
        "mean_return_pct": round(float(sample.mean()) * 100, 3),
        "mean_return_ci95_pct": [round(float(np.quantile(boot, 0.025)) * 100, 3),
                                 round(float(np.quantile(boot, 0.975)) * 100, 3)],
        "p_positive": round(pos / len(sample), 4), "p_positive_ci95": [round(lo, 4), round(hi, 4)],
        "p_negative": round(float((sample < 0).mean()), 4),
        "quantiles_pct": {q: round(float(np.quantile(fwd, q / 100)) * 100, 3) for q in (5, 10, 25, 50, 75, 90, 95)},
        "note": "Historical distribution of past h-day returns — not a forecast.",
    }


def analyse(close: pd.Series, bench: pd.Series | None, rf_annual: float, horizons: list[int]) -> dict:
    r = close.pct_change().dropna().tail(3 * TRADING_DAYS)
    if len(r) < 120:
        return {"available": False, "reason": "fewer than 120 daily returns"}
    rf_d = (1 + rf_annual) ** (1 / TRADING_DAYS) - 1
    ex = r - rf_d
    sd = float(r.std(ddof=1))
    downside = ex[ex < 0]
    dd_sd = float(np.sqrt((downside**2).sum() / len(ex))) if len(downside) else float("nan")
    jb = stats.jarque_bera(r)
    t = stats.ttest_1samp(r, 0.0)
    out = {
        "available": True, "window_days": int(len(r)),
        "annual_return_pct": round(float((1 + r.mean()) ** TRADING_DAYS - 1) * 100, 2),
        "annual_volatility_pct": round(sd * math.sqrt(TRADING_DAYS) * 100, 2),
        "sharpe": round(float(ex.mean() / sd * math.sqrt(TRADING_DAYS)), 3) if sd > 0 else None,
        "sortino": round(float(ex.mean() / dd_sd * math.sqrt(TRADING_DAYS)), 3) if dd_sd and dd_sd > 0 else None,
        "risk_free_rate_pct": rf_annual * 100,
        **max_drawdown(close.tail(3 * TRADING_DAYS)),
        "var_1d": var_cvar(r, 0.95),
        "normality": {"jarque_bera_p": float(jb.pvalue), "skew": round(float(stats.skew(r)), 3),
                      "excess_kurtosis": round(float(stats.kurtosis(r)), 3),
                      "normal_assumption_ok": bool(jb.pvalue > 0.05),
                      "note": "If normality is rejected, prefer historical / Cornish-Fisher VaR over normal VaR."},
        "mean_return_significance": {"t_stat": round(float(t.statistic), 3), "p_value": round(float(t.pvalue), 4),
                                     "significant_at_5pct": bool(t.pvalue < 0.05)},
        "horizons": [horizon_stats(close, h) for h in horizons],
    }
    if bench is not None:
        b = bench.reindex(close.index).ffill().pct_change()
        j = pd.concat([close.pct_change(), b], axis=1).dropna().tail(TRADING_DAYS)
        if len(j) >= 60 and j.iloc[:, 1].var() > 0:
            out["beta_1y"] = round(float(np.cov(j.iloc[:, 0], j.iloc[:, 1], ddof=1)[0, 1] / j.iloc[:, 1].var(ddof=1)), 3)
            out["correlation_1y"] = round(float(j.iloc[:, 0].corr(j.iloc[:, 1])), 3)
    return out
