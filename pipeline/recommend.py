"""Bullish / bearish / neutral research assessments.

Keeps four different quantities strictly separate (spec §9):
  technical_score  — rule-based, −100…+100, NOT a probability
  news_sentiment   — −1…+1 weighted headline sentiment, NOT a probability
  model probabilities — calibrated P(bearish), P(neutral), P(bullish); sum to 100 %
  model_confidence — how decisive/validated the model is, NOT the probability of profit
Research only. Nothing here places trades.
"""
from __future__ import annotations

import math
from datetime import date

import numpy as np
import pandas as pd

INSUFFICIENT = "Insufficient evidence — no recommendation."


def technical_score(df: pd.DataFrame, ind: pd.DataFrame) -> dict:
    last, c = ind.iloc[-1], float(df["close"].iloc[-1])
    pts, notes = 0.0, []

    def rule(cond, good, bad, w, text_g, text_b):
        nonlocal pts
        if cond is None or (isinstance(cond, float) and math.isnan(cond)):
            return
        pts += w if cond else -w
        notes.append(text_g if cond else text_b)

    g = lambda k: last.get(k, np.nan)  # noqa: E731
    if not np.isnan(g("sma_50")):
        rule(c > g("sma_50"), 1, -1, 10, "Price above 50-day SMA", "Price below 50-day SMA")
    if not np.isnan(g("sma_200")):
        rule(c > g("sma_200"), 1, -1, 10, "Price above 200-day SMA", "Price below 200-day SMA")
        rule(g("sma_50") > g("sma_200"), 1, -1, 10, "50-day SMA above 200-day (long-term uptrend)",
             "50-day SMA below 200-day (long-term downtrend)")
    if not np.isnan(g("macd")):
        rule(g("macd") > g("macd_signal"), 1, -1, 10, "MACD above signal line", "MACD below signal line")
    r = g("rsi_14")
    if not np.isnan(r):
        if r >= 70:
            pts += 3
            notes.append(f"RSI {r:.0f}: strong momentum but overbought — not an automatic sell")
        elif r >= 50:
            pts += 8
            notes.append(f"RSI {r:.0f}: positive momentum")
        elif r > 30:
            pts -= 8
            notes.append(f"RSI {r:.0f}: weak momentum")
        else:
            pts -= 3
            notes.append(f"RSI {r:.0f}: oversold — not an automatic buy")
    if not np.isnan(g("adx")) and g("adx") >= 25:
        rule(g("plus_di") > g("minus_di"), 1, -1, 12, f"ADX {g('adx'):.0f}: strong trend, +DI leading",
             f"ADX {g('adx'):.0f}: strong trend, −DI leading")
    if g("supertrend_dir") in (1, -1):
        rule(g("supertrend_dir") == 1, 1, -1, 8, "Supertrend in buy mode", "Supertrend in sell mode")
    if not np.isnan(g("cmf_20")) and abs(g("cmf_20")) > 0.05:
        rule(g("cmf_20") > 0, 1, -1, 8, "Chaikin Money Flow positive (accumulation)",
             "Chaikin Money Flow negative (distribution)")
    if bool(g("breakout")):
        pts += 10
        notes.append("20-day breakout on above-average volume")
    if bool(g("breakdown")):
        pts -= 10
        notes.append("20-day breakdown on above-average volume")
    max_pts = 10 + 10 + 10 + 10 + 8 + 12 + 8 + 8 + 10
    return {"score": round(100 * pts / max_pts, 1), "evidence": notes,
            "note": "Rule-based summary of indicators; not a probability."}


def trade_scenarios(close: float, atr: float, sr: dict) -> dict:
    if not atr or math.isnan(atr):
        return {}
    sup = [s["level"] for s in sr.get("support", [])]
    res = [r["level"] for r in sr.get("resistance", [])]
    stop = max(min(sup[0] - 0.5 * atr, close - atr), close - 3 * atr) if sup else close - 2 * atr
    tgt_candidates = [r for r in res if r >= close + atr]
    target = tgt_candidates[0] if tgt_candidates else close + 2.5 * atr
    risk, reward = close - stop, target - close
    return {"reference_price": round(close, 2),
            "entry_scenario": f"Only if price holds above {round(sup[0], 2) if sup else round(close - atr, 2)} "
                              f"(nearest support) after the next session opens; avoid chasing a gap-up.",
            "stop_loss_scenario": round(stop, 2), "target_scenario": round(target, 2),
            "risk_reward": round(reward / risk, 2) if risk > 0 else None,
            "method": "stop below nearest support (≥1 ATR, ≤3 ATR away); target at next resistance ≥1 ATR away, "
                      "else 2.5 ATR"}


def _confidence(p: np.ndarray, lift: float | None) -> str:
    ent = -float(np.sum(p * np.log(np.clip(p, 1e-12, 1)))) / math.log(3)
    decisiveness = 1 - ent
    if lift and lift >= 1.25 and decisiveness >= 0.15:
        return "high"
    if lift and lift >= 1.08 and decisiveness >= 0.07:
        return "medium"
    return "low"


def assess(symbol_row: dict, df: pd.DataFrame, ind: pd.DataFrame, quality: dict, fund: dict, qstats: dict,
           news_sent: dict | None, model_out: dict, market_ctx: dict, sr: dict) -> dict:
    close = float(df["close"].iloc[-1])
    atr = float(ind["atr_14"].iloc[-1]) if not np.isnan(ind["atr_14"].iloc[-1]) else float("nan")
    tech = technical_score(df, ind)
    scen = trade_scenarios(close, atr, sr)
    horizons = []
    base_reasons = []
    if quality.get("stale"):
        base_reasons.append(f"price data is stale (last bar {quality.get('last_date')})")
    if not quality.get("liquid", True):
        base_reasons.append(f"illiquid: median traded value ₹{quality.get('median_traded_value_cr')} cr/day")
    if quality.get("bars", 0) < 260:
        base_reasons.append("less than one year of price history")

    fail_reasons = []
    if market_ctx.get("nifty_below_200dma"):
        fail_reasons.append("Broad market (Nifty 50) is below its 200-day average")
    if ind["hv_20"].iloc[-1] and quality.get("vol_regime") == "high":
        fail_reasons.append("Volatility is in its top 20 % of the past year — wider swings likely")
    if news_sent and news_sent.get("negative_events"):
        fail_reasons.append("Recent negative corporate news")
    if fund.get("available") and fund.get("red_flags"):
        fail_reasons.append(f"Fundamental red flags: {', '.join(f['flag'] for f in fund['red_flags'][:3])}")
    fail_reasons.append("Unexpected news, results or market-wide shocks after the data timestamp")

    for h, mo in model_out.items():
        entry = {"horizon_days": h, "type": "swing"}
        rep = mo.get("report", {})
        probs = mo.get("probs", {}).get(symbol_row["symbol"])
        reasons = list(base_reasons)
        if not rep.get("gate", {}).get("passed"):
            reasons.append("model did not pass out-of-sample validation: " + "; ".join(rep.get("gate", {}).get("reasons", [])))
        if probs is None and rep.get("gate", {}).get("passed"):
            reasons.append("no model prediction for this stock (insufficient feature history)")
        if reasons:
            entry.update({"label": "insufficient", "message": INSUFFICIENT, "reasons": reasons})
            horizons.append(entry)
            continue
        p = np.array(probs, dtype=float)
        p = p / p.sum()
        pct = [round(float(x) * 100, 1) for x in p]
        pct[1] = round(100 - pct[0] - pct[2], 1)   # make the rounded numbers sum to exactly 100
        thr = rep.get("thresholds", {})
        bull_t, bear_t = thr.get("bullish", {}), thr.get("bearish", {})
        if bull_t.get("validated") and p[2] >= bull_t["threshold"]:
            label, lift = "bullish", bull_t.get("holdout_lift")
        elif bear_t.get("validated") and p[0] >= bear_t["threshold"]:
            label, lift = "bearish", bear_t.get("holdout_lift")
        else:
            label, lift = "neutral", None
        hs = next((x for x in qstats.get("horizons", []) if x.get("horizon_days") == h), {})
        entry.update({
            "label": label,
            "probabilities": {"bearish": pct[0], "neutral": pct[1], "bullish": pct[2]},
            "thresholds_used": {"bullish": bull_t.get("threshold"), "bearish": bear_t.get("threshold")},
            "model_confidence": _confidence(p, lift),
            "model": rep.get("selected_model"),
            "historical_return_distribution_pct": hs.get("quantiles_pct"),
            "historical_p_positive": hs.get("p_positive"),
            "label_note": ("Probability crossed a threshold validated on held-out data" if label != "neutral" else
                           "No class crossed its validated threshold — no directional edge detected"),
        })
        horizons.append(entry)

    fund_just = []
    if fund.get("available"):
        sc = fund["scorecard"]
        fund_just.append(f"Fundamental scorecard: {sc['label']}"
                         + (f" ({sc['passed']}/{sc['evaluated']} checks passed)" if sc["score"] is not None else ""))
        fund_just += [f"⚠ {f['flag']}: {f['detail']}" for f in fund.get("red_flags", [])[:3]]
    else:
        fund_just.append(f"Fundamentals unavailable: {fund.get('reason', 'not fetched')}")
    news_just = []
    if news_sent:
        news_just.append(f"{news_sent['count']} news item(s) in 7 days, weighted sentiment {news_sent['score']:+.2f}")
        if news_sent.get("order_wins"):
            news_just.append(f"{news_sent['order_wins']} order-win report(s)")
        if news_sent.get("negative_events"):
            news_just.append(f"{news_sent['negative_events']} negative event(s)")
    else:
        news_just.append("No matched news in the last 7 days")

    return {
        "symbol": symbol_row["symbol"], "name": symbol_row.get("name"), "exchange": symbol_row.get("exchanges", "NSE"),
        "latest_price": round(close, 2), "data_timestamp": quality.get("last_date"), "data_type": quality.get("data_type"),
        "data_quality": quality, "horizons": horizons,
        "intraday": {"label": "insufficient", "message": INSUFFICIENT,
                     "reasons": ["intraday models need an authorised intraday data feed (not configured)"]},
        "technical": tech, "technical_justification": tech["evidence"][:6],
        "fundamental_justification": fund_just, "news_justification": news_just,
        "news_sentiment": news_sent["score"] if news_sent else None,
        "support": sr.get("support", []), "resistance": sr.get("resistance", []),
        "scenarios": scen, "failure_reasons": fail_reasons,
        "disclaimer": "Research estimate only — not investment advice, not a guarantee. Not a buy/sell instruction.",
        "as_of": str(date.today()),
    }
