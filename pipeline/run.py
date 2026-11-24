"""Daily pipeline: python -m pipeline.run [--universe nifty50] [--skip-news] [--force-retrain]

Writes JSON files for the static website into settings.output_dir (default site/data).
Each step reports failures into status.json instead of hiding them.
"""
from __future__ import annotations

import argparse
import gzip
import json
import logging
import math
import re
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from . import backtest, fundamentals, indicators, instruments, marketcal, ml, news, quant, recommend, telegram
from .config import IST, Settings
from .providers import get_provider

log = logging.getLogger("pipeline")
VERSION = "1.1.0"

INDICES = {
    "^NSEI": "Nifty 50", "^BSESN": "Sensex", "^NSEBANK": "Nifty Bank", "^CNXIT": "Nifty IT",
    "^CNXAUTO": "Nifty Auto", "^CNXFMCG": "Nifty FMCG", "^CNXPHARMA": "Nifty Pharma", "^CNXMETAL": "Nifty Metal",
    "^CNXREALTY": "Nifty Realty", "^CNXENERGY": "Nifty Energy", "^CNXPSUBANK": "Nifty PSU Bank",
    "^CNXMEDIA": "Nifty Media", "^CNXINFRA": "Nifty Infra", "^NSMIDCP": "Nifty Next 50", "^CRSLDX": "Nifty 500",
}
BENCH = "^NSEI"


# ------------------------------------------------------------------ JSON helpers
def _clean(o):
    if isinstance(o, dict):
        return {str(k): _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_clean(v) for v in o]
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating, float)):
        f = float(o)
        return None if math.isnan(f) or math.isinf(f) else f
    if isinstance(o, (np.bool_,)):
        return bool(o)
    if isinstance(o, (pd.Timestamp, datetime, date)):
        return o.isoformat()[:10] if isinstance(o, (pd.Timestamp, date)) and not isinstance(o, datetime) else o.isoformat()
    return o


def dump(obj, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(_clean(obj), fh, ensure_ascii=False, separators=(",", ":"))
    tmp.replace(path)   # atomic: the site never reads a half-written file


def safe_name(sym: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]", "_", sym)


# ------------------------------------------------------------------ price cache
class PriceCache:
    """Incremental OHLCV cache. Re-downloads full history if an overlap mismatch suggests a split/bonus."""

    def __init__(self, root: Path):
        self.root = Path(root) / "prices"
        self.root.mkdir(parents=True, exist_ok=True)

    def path(self, ticker: str) -> Path:
        return self.root / f"{safe_name(ticker)}.csv.gz"

    def load(self, ticker: str) -> pd.DataFrame | None:
        p = self.path(ticker)
        if not p.exists():
            return None
        with gzip.open(p, "rt") as fh:
            df = pd.read_csv(fh, index_col=0, parse_dates=True)
        return df

    def save(self, ticker: str, df: pd.DataFrame):
        with gzip.open(self.path(ticker), "wt") as fh:
            df.to_csv(fh)

    def update(self, provider, tickers: list[str], years: int) -> tuple[dict, dict]:
        start_full = date.today() - timedelta(days=int(365.25 * years) + 10)
        cached = {t: self.load(t) for t in tickers}
        need_full = [t for t, df in cached.items() if df is None or df.empty]
        incremental = [t for t in tickers if t not in need_full]
        out, meta = {}, {}
        if incremental:
            last = min(cached[t].index.max() for t in incremental)
            fresh = provider.history(incremental, start=(last - timedelta(days=10)).date())
            for t in incremental:
                old = cached[t]
                new = fresh.get(t)
                if new is None or new.empty:
                    out[t] = old
                    meta[t] = {"provider_issue": "no fresh data returned; using cached history"}
                    continue
                overlap = old.index.intersection(new.index)
                if len(overlap) and (abs(old.loc[overlap, "close"] / new.loc[overlap, "close"] - 1) > 0.01).any():
                    need_full.append(t)   # corporate action re-based history
                    continue
                merged = pd.concat([old[~old.index.isin(new.index)], new]).sort_index()
                merged.attrs = new.attrs
                out[t] = merged
        if need_full:
            full = provider.history(need_full, start=start_full)
            for t in need_full:
                if t in full:
                    out[t] = full[t]
                elif cached.get(t) is not None:
                    out[t] = cached[t]
                    meta[t] = {"provider_issue": "full refresh failed; using cached history"}
        for t, df in out.items():
            cutoff = pd.Timestamp(start_full)
            df = df[df.index >= cutoff]
            out[t] = df
            self.save(t, df)
            meta.setdefault(t, {}).update(df.attrs if df.attrs else {"provider": "cache"})
        return out, meta


# ------------------------------------------------------------------ helpers
def quality_for(df: pd.DataFrame, ind: pd.DataFrame, meta: dict, now: datetime, holidays, settings) -> dict:
    last_date = df.index[-1].date()
    tv = (df["close"] * df["volume"]).tail(20).median() / 1e7
    return {
        "last_date": str(last_date), "bars": int(len(df)),
        "stale": marketcal.is_stale(last_date, now, holidays, 1),
        "median_traded_value_cr": round(float(tv), 2) if not math.isnan(tv) else None,
        "liquid": bool(tv >= settings.min_median_traded_value_cr) if not math.isnan(tv) else False,
        "provider": meta.get("provider", "unknown"), "fetched_at": meta.get("fetched_at"),
        "data_type": "End-of-day (delayed) — not real-time",
        "issues": meta.get("issues", []) + ([meta["provider_issue"]] if meta.get("provider_issue") else []),
        "vol_regime": indicators.volatility_regime(df["close"]),
        "rel_volume": round(float(ind["rel_volume"].iloc[-1]), 2) if not math.isnan(ind["rel_volume"].iloc[-1]) else None,
        "breakout": bool(ind["breakout"].iloc[-1]), "breakdown": bool(ind["breakdown"].iloc[-1]),
    }


def chart_payload(df: pd.DataFrame, ind: pd.DataFrame, n: int) -> dict:
    d, i = df.tail(n), ind.tail(n)
    r = lambda s: [None if (x is None or (isinstance(x, float) and math.isnan(x))) else round(float(x), 2) for x in s]  # noqa: E731
    return {"date": [str(x.date()) for x in d.index], "open": r(d["open"]), "high": r(d["high"]),
            "low": r(d["low"]), "close": r(d["close"]), "volume": [int(v) for v in d["volume"].fillna(0)],
            **{k: r(i[k]) for k in ("sma_20", "sma_50", "sma_200", "ema_20", "bb_upper", "bb_mid", "bb_lower", "rsi_14",
                                    "macd", "macd_signal", "macd_hist", "vwap_20", "supertrend", "psar", "adx",
                                    "plus_di", "minus_di", "stoch_k", "stoch_d", "obv", "cmf_20", "mfi_14", "atr_14")}}


def latest_indicators(ind: pd.DataFrame) -> dict:
    row = ind.drop(columns=["ichi_chikou"], errors="ignore").iloc[-1]
    return {k: (round(float(v), 4) if isinstance(v, (float, np.floating)) and not math.isnan(v) else
                bool(v) if isinstance(v, (bool, np.bool_)) else None if isinstance(v, float) else v)
            for k, v in row.items()}


def pct_change(s: pd.Series, n: int):
    if len(s) <= n:
        return None
    return round(float(s.iloc[-1] / s.iloc[-1 - n] - 1) * 100, 2)


# ------------------------------------------------------------------ main
def run(settings: Settings, provider=None, fetch_news: bool = True, master_override: pd.DataFrame | None = None,
        news_items_override: list | None = None, now: datetime | None = None, force_retrain: bool = False,
        fetch_fundamentals: bool = True) -> dict:
    t0 = time.time()
    now = now or datetime.now(timezone.utc)
    out = Path(settings.output_dir)
    (out / "stocks").mkdir(parents=True, exist_ok=True)
    holidays = marketcal.load_holidays()
    status = {"version": VERSION, "run_started": now.isoformat(), "state": "running", "warnings": [], "steps": {}}

    # 1. instruments
    if master_override is not None:
        master, irep = master_override, {"mode": "override", "sources": {}}
    else:
        master, irep = instruments.build_master(settings)
    universe = instruments.select_universe(master, settings.universe)
    instruments.save_public(master, irep, out)
    status["steps"]["instruments"] = {"master": len(master), "universe": settings.universe, "selected": len(universe),
                                      "report": irep}
    status["warnings"] += irep.get("warnings", [])

    # 2. prices
    provider = provider or get_provider("yahoo")
    cache = PriceCache(settings.cache_dir)
    sym_by_ticker = dict(zip(universe["yahoo_nse"], universe["symbol"]))
    tickers = list(sym_by_ticker) + list(INDICES)
    prices, pmeta = cache.update(provider, tickers, settings.history_years)
    failures = getattr(provider, "failures", {})
    status["steps"]["prices"] = {"provider": provider.name, "data_type": provider.data_type, "requested": len(tickers),
                                 "received": len(prices), "failed": len(set(tickers) - set(prices)),
                                 "failed_examples": dict(list(failures.items())[:15])}
    bench = prices.get(BENCH, pd.DataFrame()).get("close") if BENCH in prices else None
    if bench is None:
        status["warnings"].append("Nifty 50 benchmark unavailable — relative strength, beta and market features disabled")

    # 3. indicators & quality
    stocks, quality = {}, {}
    for tk, sym in sym_by_ticker.items():
        df = prices.get(tk)
        if df is None or len(df) < 60:
            continue
        ind = indicators.compute_all(df, bench)
        stocks[sym] = (df, ind)
        quality[sym] = quality_for(df, ind, pmeta.get(tk, {}), now, holidays, settings)
    status["steps"]["indicators"] = {"stocks": len(stocks)}
    market_dates = [q["last_date"] for q in quality.values()]
    status["market_date"] = max(market_dates) if market_dates else None

    # 4. fundamentals (incremental)
    fdir = Path(settings.cache_dir) / "fundamentals"
    fdir.mkdir(parents=True, exist_ok=True)
    fund_raw = {}
    for sym in stocks:
        p = fdir / f"{safe_name(sym)}.json"
        if p.exists():
            fund_raw[sym] = json.loads(p.read_text(encoding="utf-8"))
    refreshed, ferr = 0, 0
    if fetch_fundamentals and hasattr(provider, "fundamentals"):
        def age(sym):
            fa = fund_raw.get(sym, {}).get("fetched_at")
            return (now - datetime.fromisoformat(fa)).days if fa else 10_000
        due = sorted([s for s in stocks if age(s) >= settings.fundamentals_max_age_days], key=age, reverse=True)
        for sym in due[: settings.fundamentals_per_run]:
            try:
                raw = provider.fundamentals(f"{sym}.NS")
                fund_raw[sym] = raw
                (fdir / f"{safe_name(sym)}.json").write_text(json.dumps(_clean(raw)), encoding="utf-8")
                refreshed += 1
            except NotImplementedError:
                break
            except Exception as exc:  # noqa: BLE001
                ferr += 1
                log.warning("fundamentals %s: %s", sym, exc)
    status["steps"]["fundamentals"] = {"cached": len(fund_raw), "refreshed_this_run": refreshed, "errors": ferr}
    sector_of = dict(zip(universe["symbol"], universe["sector"]))
    fund = {s: fundamentals.analyse(fund_raw.get(s, {}), float(stocks[s][0]["close"].iloc[-1]), sector_of.get(s, ""))
            for s in stocks}
    revenue_lookup = {s: f.get("annual_revenue") for s, f in fund.items() if f.get("available")}

    # 5. news
    hist_path = Path(settings.state_dir) / "news_history.json"
    history = news.load_history(hist_path)
    before_ids = {h["id"] for h in history}
    feed_status = {}
    if news_items_override is not None:
        items = news_items_override
    elif fetch_news:
        items, feed_status = news.fetch_feeds(settings.news_feeds)
        for d in (now, now - timedelta(days=1)):
            try:
                got = news.fetch_bse_announcements(d.astimezone(IST))
                items += got
                feed_status[f"BSE announcements {d.astimezone(IST).date()}"] = f"ok ({len(got)})"
            except Exception as exc:  # noqa: BLE001
                feed_status[f"BSE announcements {d.astimezone(IST).date()}"] = f"failed: {str(exc)[:120]}"
    else:
        items = []
    matcher = news.CompanyMatcher(master)
    history = news.process(items, matcher, history, revenue_lookup, settings.usd_inr_fallback, now)
    dump(history, hist_path)
    new_ids = {h["id"] for h in history} - before_ids
    sent_by_sym = news.news_sentiment_by_symbol(history, 7, now)
    status["steps"]["news"] = {"fetched": len(items), "new": len(new_ids), "stored": len(history), "feeds": feed_status}
    dump({"generated_at": now.isoformat(), "items": history[:1500],
          "categories": {k: v["label"] for k, v in news.CATEGORIES.items()},
          "note": "Headlines and links only. Open the original source to read the article."}, out / "news.json")

    # 6. models
    model_out, model_public = {}, {}
    panel = ml.build_panel(stocks, bench, settings.horizons, settings.neutral_band_k, settings.min_neutral_band)
    if not panel.empty:
        results = ml.run(panel, settings.horizons, settings.cache_dir, settings, force=force_retrain)
        latest = panel.sort_values("date").groupby("symbol").tail(1).set_index("symbol")
        for h, res in results.items():
            probs = {}
            if res.get("bundle") is not None:
                p = ml.predict(res["bundle"], latest)
                probs = {sym: p[i].tolist() for i, sym in enumerate(latest.index)}
            model_out[h] = {"report": res["report"], "probs": probs}
            model_public[h] = res["report"]
        bt = {}
        for h, res in results.items():
            rep = res["report"]
            thr = (rep.get("thresholds") or {}).get("bullish", {}).get("threshold")
            bt[h] = backtest.run(res.get("oos"), h, rep.get("selected_model", "ensemble"), thr, settings.costs) \
                if rep.get("selected_model") else {"available": False, "reason": "no model"}
        dump({"generated_at": now.isoformat(), "horizons": bt}, out / "backtest.json")
    else:
        status["warnings"].append("Not enough price history to train models")
        dump({"generated_at": now.isoformat(), "horizons": {}}, out / "backtest.json")
    dump({"generated_at": now.isoformat(), "horizons": model_public,
          "intraday": {"available": False, "reason": "requires an authorised intraday data provider"},
          "classes": ml.CLASSES}, out / "model.json")
    status["steps"]["models"] = {str(h): {"gate_passed": r.get("gate", {}).get("passed"),
                                          "selected": r.get("selected_model")} for h, r in model_public.items()}

    # 7. market context & per-stock assessments
    nifty_df = prices.get(BENCH)
    market_ctx = {}
    if nifty_df is not None and len(nifty_df) > 200:
        market_ctx["nifty_below_200dma"] = bool(nifty_df["close"].iloc[-1] < nifty_df["close"].tail(200).mean())
    recs, scanner = [], []
    for sym, (df, ind) in stocks.items():
        row = universe[universe["symbol"] == sym].iloc[0].to_dict()
        sr = indicators.support_resistance(df)
        qs = quant.analyse(df["close"], bench, settings.risk_free_rate, settings.horizons)
        rec = recommend.assess(row, df, ind, quality[sym], fund[sym], qs, sent_by_sym.get(sym), model_out, market_ctx, sr)
        recs.append(rec)
        prev = df.iloc[-2] if len(df) > 1 else df.iloc[-1]
        patterns = indicators.candlestick_patterns(df.tail(30)).tail(5)
        detail = {
            "symbol": sym, "name": row.get("name"), "isin": row.get("isin"), "bse_code": row.get("bse_code"),
            "sector": row.get("sector"), "industry": row.get("industry"), "cap_category": row.get("cap_category"),
            "cap_source": row.get("cap_source"), "exchanges": row.get("exchanges"),
            "quality": quality[sym], "chart": chart_payload(df, ind, settings.chart_days),
            "indicators": latest_indicators(ind),
            "pivots": indicators.pivot_points(float(prev["high"]), float(prev["low"]), float(prev["close"])),
            "fibonacci": indicators.fibonacci(df), "structure": indicators.market_structure(df),
            "candlestick_patterns_last5": {str(d.date()): [k for k, v in r.items() if v] for d, r in patterns.iterrows()},
            "beta_corr": dict(zip(("beta", "correlation"), indicators.beta_corr(df["close"], bench))) if bench is not None else {},
            "fundamentals": fund[sym], "quant": qs, "recommendation": rec,
            "news": [n for n in history if n.get("symbol") == sym or any(c["symbol"] == sym for c in n.get("companies", []))][:25],
        }
        dump(detail, out / "stocks" / f"{safe_name(sym)}.json")
        c = df["close"]
        scanner.append({
            "symbol": sym, "file": safe_name(sym), "name": row.get("name"), "sector": row.get("sector") or "Unclassified",
            "cap": row.get("cap_category"), "exchanges": row.get("exchanges"), "price": round(float(c.iloc[-1]), 2),
            "chg_1d": pct_change(c, 1), "chg_5d": pct_change(c, 5), "chg_20d": pct_change(c, 20),
            "rel_vol": quality[sym]["rel_volume"], "traded_value_cr": quality[sym]["median_traded_value_cr"],
            "liquid": quality[sym]["liquid"], "stale": quality[sym]["stale"], "date": quality[sym]["last_date"],
            "rsi": round(float(ind["rsi_14"].iloc[-1]), 1) if not math.isnan(ind["rsi_14"].iloc[-1]) else None,
            "tech_score": rec["technical"]["score"],
            "fund_score": fund[sym].get("scorecard", {}).get("score") if fund[sym].get("available") else None,
            "fund_label": fund[sym].get("scorecard", {}).get("label") if fund[sym].get("available") else "n/a",
            "news_sent": rec["news_sentiment"], "breakout": quality[sym]["breakout"], "breakdown": quality[sym]["breakdown"],
            "horizons": {str(h["horizon_days"]): {"label": h["label"], "p": h.get("probabilities"),
                                                  "conf": h.get("model_confidence")} for h in rec["horizons"]},
        })
    dump({"generated_at": now.isoformat(), "market_date": status["market_date"], "rows": scanner}, out / "scanner.json")

    # 8. overview
    idx_rows = []
    for tk, label in INDICES.items():
        df = prices.get(tk)
        if df is None or df.empty:
            idx_rows.append({"ticker": tk, "name": label, "available": False})
            continue
        c = df["close"]
        idx_rows.append({"ticker": tk, "name": label, "available": True, "last": round(float(c.iloc[-1]), 2),
                         "date": str(df.index[-1].date()), "chg_1d": pct_change(c, 1), "chg_5d": pct_change(c, 5),
                         "chg_20d": pct_change(c, 20), "chg_1y": pct_change(c, 250),
                         "spark": [round(float(x), 2) for x in c.tail(120)]})
    sc = pd.DataFrame(scanner)
    breadth, sectors, movers = {}, [], {}
    if not sc.empty:
        adv, dec = int((sc["chg_1d"] > 0).sum()), int((sc["chg_1d"] < 0).sum())
        above200 = sum(1 for s, (df, ind) in stocks.items() if not math.isnan(ind["sma_200"].iloc[-1])
                       and df["close"].iloc[-1] > ind["sma_200"].iloc[-1])
        breadth = {"advances": adv, "declines": dec, "unchanged": int(len(sc) - adv - dec),
                   "ad_ratio": round(adv / dec, 2) if dec else None, "pct_above_200dma": round(100 * above200 / len(sc), 1),
                   "breakouts": int(sc["breakout"].sum()), "breakdowns": int(sc["breakdown"].sum())}
        g = sc.groupby("sector").agg(n=("symbol", "count"), chg_1d=("chg_1d", "mean"), chg_5d=("chg_5d", "mean"),
                                     chg_20d=("chg_20d", "mean")).reset_index()
        sectors = g[g["n"] >= 2].round(2).sort_values("chg_20d", ascending=False).to_dict("records")
        liq = sc[sc["liquid"]]
        cols = ["symbol", "file", "name", "price", "chg_1d", "rel_vol"]
        movers = {"gainers": liq.nlargest(10, "chg_1d")[cols].to_dict("records"),
                  "losers": liq.nsmallest(10, "chg_1d")[cols].to_dict("records"),
                  "volume_spikes": liq[liq["rel_vol"] >= settings.alerts["volume_spike_x"]].nlargest(10, "rel_vol")[cols].to_dict("records")}
    dump({"generated_at": now.isoformat(), "market_date": status["market_date"], "indices": idx_rows,
          "breadth": breadth, "sectors": sectors, "movers": movers, "market_context": market_ctx}, out / "overview.json")

    # 9. alerts
    try:
        status["steps"]["telegram"] = telegram.dispatch(settings, history, recs, new_ids, settings.state_dir)
    except Exception as exc:  # noqa: BLE001
        status["steps"]["telegram"] = {"error": str(exc)[:200]}

    status["settings"] = {"universe": settings.universe, "horizons": settings.horizons, "alerts": settings.alerts,
                          "costs": settings.costs, "history_years": settings.history_years}
    status.update({"state": "ok", "run_finished": datetime.now(timezone.utc).isoformat(),
                   "duration_sec": round(time.time() - t0, 1), "data_type": "End-of-day (delayed) — not real-time"})
    dump(status, out / "status.json")
    return status


def main():
    ap = argparse.ArgumentParser(description="Indian market intelligence daily pipeline")
    ap.add_argument("--universe", help="nifty50 | nifty100 | nifty200 | nifty500 | all_nse")
    ap.add_argument("--skip-news", action="store_true")
    ap.add_argument("--skip-fundamentals", action="store_true")
    ap.add_argument("--force-retrain", action="store_true")
    ap.add_argument("-v", "--verbose", action="store_true")
    a = ap.parse_args()
    logging.basicConfig(level=logging.DEBUG if a.verbose else logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    s = Settings.load()
    if a.universe:
        s.universe = a.universe
    try:
        st = run(s, fetch_news=not a.skip_news, force_retrain=a.force_retrain, fetch_fundamentals=not a.skip_fundamentals)
        print(json.dumps({k: st[k] for k in ("state", "market_date", "duration_sec")}, indent=2))
        print("warnings:", *st["warnings"], sep="\n  ")
    except Exception as exc:
        dump({"version": VERSION, "state": "failed", "error": str(exc)[:500],
              "run_finished": datetime.now(timezone.utc).isoformat()}, Path(s.output_dir) / "status_error.json")
        raise


if __name__ == "__main__":
    main()
