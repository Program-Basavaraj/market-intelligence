"""Out-of-sample backtest of the swing signals, with Indian delivery-trade costs.

Only out-of-sample walk-forward predictions are used. Execution assumption: the signal is known
after the close on day t; buy at the OPEN of t+1; sell at the CLOSE of t+h. Long-only, because
short-selling delivery shares for several days is not possible in the Indian cash market.

Known biases, also shown on the website:
  * Survivorship bias — the universe is today's index constituents.
  * Yahoo prices are split-adjusted; dividends are ignored (slightly understates returns).
  * Costs are approximate and editable in config/settings.json.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd


def round_trip_cost(c: dict) -> float:
    """Approximate cost of buy + sell as a fraction of trade value."""
    pct = lambda x: x / 100  # noqa: E731
    per_side_fees = pct(c["brokerage_pct"]) + pct(c["exchange_pct"]) + pct(c["sebi_pct"])
    gst = per_side_fees * pct(c["gst_pct"])
    buy = per_side_fees + gst + pct(c["stt_pct"]) + pct(c["stamp_buy_pct"]) + pct(c["slippage_pct"])
    sell = per_side_fees + gst + pct(c["stt_pct"]) + pct(c["slippage_pct"])
    return buy + sell


def _curve_stats(r: pd.Series, h: int) -> dict:
    if r.empty:
        return {}
    eq = (1 + r).cumprod()
    periods_per_year = 252 / h
    years = len(r) / periods_per_year
    dd = eq / eq.cummax() - 1
    sd = r.std(ddof=1)
    return {"total_return_pct": round(float(eq.iloc[-1] - 1) * 100, 2),
            "cagr_pct": round(float(eq.iloc[-1] ** (1 / years) - 1) * 100, 2) if years > 0 and eq.iloc[-1] > 0 else None,
            "sharpe": round(float(r.mean() / sd * math.sqrt(periods_per_year)), 3) if sd > 0 else None,
            "max_drawdown_pct": round(float(dd.min()) * 100, 2), "periods": int(len(r))}


def run(oos: pd.DataFrame, h: int, model: str, threshold: float | None, costs: dict) -> dict:
    if oos is None or oos.empty or threshold is None:
        return {"available": False, "reason": "no validated threshold / out-of-sample predictions"}
    cost = round_trip_cost(costs)
    df = oos.dropna(subset=[f"trade_{h}"]).copy()
    df["net"] = df[f"trade_{h}"] - cost
    dates = np.sort(df["date"].unique())
    rebal = dates[::h]   # non-overlapping holding periods
    strat, bench, invested = [], [], 0
    sig = df[df[f"{model}_bull"] >= threshold]
    for d in rebal:
        day_all = df[df["date"] == d]
        day_sig = sig[sig["date"] == d]
        bench.append(day_all["net"].mean() if len(day_all) else 0.0)
        if len(day_sig):
            strat.append(day_sig["net"].mean())
            invested += 1
        else:
            strat.append(0.0)
    s, b = pd.Series(strat, index=rebal), pd.Series(bench, index=rebal)
    eq_s, eq_b = (1 + s).cumprod(), (1 + b).cumprod()
    bear = df[df[f"{model}_bear"] >= threshold]
    result = {
        "available": True, "horizon": h, "model": model, "threshold": threshold,
        "round_trip_cost_pct": round(cost * 100, 3),
        "execution": "buy next open, sell close after h sessions, equal weight, non-overlapping periods",
        "trades": int(len(sig)), "win_rate_pct": round(float((sig["net"] > 0).mean()) * 100, 2) if len(sig) else None,
        "avg_trade_net_pct": round(float(sig["net"].mean()) * 100, 3) if len(sig) else None,
        "exposure_pct": round(100 * invested / max(len(rebal), 1), 1),
        "strategy": _curve_stats(s, h), "benchmark_equal_weight_universe": _curve_stats(b, h),
        "bearish_signal_check": {
            "signals": int(len(bear)),
            "avg_forward_return_pct": round(float(bear[f"fwd_{h}"].mean()) * 100, 3) if len(bear) else None,
            "universe_avg_forward_return_pct": round(float(df[f"fwd_{h}"].mean()) * 100, 3),
            "note": "Bearish signals are evaluated as an 'avoid' list (no shorting).",
        },
        "equity_curve": [{"date": str(pd.Timestamp(d).date()), "strategy": round(float(x), 4), "benchmark": round(float(y), 4)}
                         for d, x, y in zip(rebal, eq_s, eq_b)],
        "biases": ["survivorship bias (current constituents)", "dividends ignored", "approximate costs",
                   "no capacity / liquidity limits beyond the liquidity filter"],
    }
    return result
