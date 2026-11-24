"""Swing-horizon probability models (2, 5, 10 trading days).

Design rules (from the project spec):
  * Three mutually exclusive classes — bearish / neutral / bullish — whose probabilities sum to 1.
    Class boundaries are volatility-scaled: band = max(k·σ20·√h, min_band); σ20 uses PAST returns only.
  * Time-ordered walk-forward validation with a purge gap of h days (no random splits, no leakage).
  * Probabilities are calibrated with temperature scaling fitted on a later, held-out slice.
  * A model is RELEASED only if it beats the naive base-rate forecast out of sample
    (Brier skill score > gate and log-loss below the base-rate log-loss). Otherwise the site shows
    "Insufficient evidence — no recommendation".
  * Decision thresholds are chosen on the first half of out-of-sample predictions and reported on
    the second half, so the reported precision is not self-selected.
Intraday horizons (5m–1h) are NOT built here: they require an authorised intraday feed.
"""
from __future__ import annotations

import logging
import math
import pickle
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import minimize_scalar
from scipy.stats import binomtest
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import confusion_matrix, precision_recall_fscore_support, roc_auc_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

log = logging.getLogger(__name__)
CLASSES = ["bearish", "neutral", "bullish"]
MIN_HOLDOUT_SIGNALS = 100
FEATURES = ["ret_5", "ret_20", "ret_60", "rsi", "macd_hist_n", "bb_pctb", "atr_pct", "hv", "rel_vol",
            "dist_sma50", "dist_sma200", "adx", "di_diff", "cmf", "gap", "rs_63", "mkt_ret_20", "mkt_vol",
            "log_turnover"]


# ------------------------------------------------------------------ features & labels
def make_features(df: pd.DataFrame, ind: pd.DataFrame, bench: pd.Series | None) -> pd.DataFrame:
    c = df["close"]
    f = pd.DataFrame(index=df.index)
    f["ret_5"] = c / c.shift(5) - 1
    f["ret_20"] = c / c.shift(20) - 1
    f["ret_60"] = c / c.shift(60) - 1
    f["rsi"] = ind["rsi_14"] / 100
    f["macd_hist_n"] = ind["macd_hist"] / c
    f["bb_pctb"] = ind["bb_pctb"].clip(-1, 2)
    f["atr_pct"] = ind["atr_14"] / c
    f["hv"] = ind["hv_20"] / 100
    f["rel_vol"] = np.log1p(ind["rel_volume"].clip(0, 20))
    f["dist_sma50"] = c / ind["sma_50"] - 1
    f["dist_sma200"] = c / ind["sma_200"] - 1
    f["adx"] = ind["adx"] / 100
    f["di_diff"] = (ind["plus_di"] - ind["minus_di"]) / 100
    f["cmf"] = ind["cmf_20"]
    f["gap"] = ind["gap_pct"] / 100
    f["rs_63"] = ind["rs_63"] / 100 if "rs_63" in ind else np.nan
    if bench is not None:
        b = bench.reindex(df.index).ffill()
        f["mkt_ret_20"] = b / b.shift(20) - 1
        f["mkt_vol"] = np.log(b / b.shift(1)).rolling(20).std() * math.sqrt(252)
    else:
        f["mkt_ret_20"] = np.nan
        f["mkt_vol"] = np.nan
    f["log_turnover"] = np.log1p((c * df["volume"]).rolling(20).median())
    return f.replace([np.inf, -np.inf], np.nan)[FEATURES]


def make_labels(close: pd.Series, h: int, k: float, min_band: float) -> tuple[pd.Series, pd.Series]:
    """Return (class 0/1/2 with NaN where future unknown, forward return)."""
    fwd = close.shift(-h) / close - 1
    sigma = close.pct_change().rolling(20).std()
    band = np.maximum(k * sigma * math.sqrt(h), min_band)
    y = pd.Series(np.where(fwd > band, 2, np.where(fwd < -band, 0, 1)), index=close.index, dtype=float)
    y[fwd.isna() | sigma.isna()] = np.nan
    return y, fwd


def build_panel(stocks: dict, bench: pd.Series | None, horizons: list[int], k: float, min_band: float) -> pd.DataFrame:
    frames = []
    for sym, (df, ind) in stocks.items():
        if len(df) < 260:
            continue
        f = make_features(df, ind, bench)
        f["symbol"] = sym
        f["date"] = df.index
        f["open_next"] = df["open"].shift(-1)
        for h in horizons:
            y, fwd = make_labels(df["close"], h, k, min_band)
            f[f"y_{h}"] = y
            f[f"fwd_{h}"] = fwd
            # tradable return: buy next open, sell at close after h sessions
            f[f"trade_{h}"] = df["close"].shift(-h) / df["open"].shift(-1) - 1
        frames.append(f)
    if not frames:
        return pd.DataFrame()
    panel = pd.concat(frames, ignore_index=True)
    for col in FEATURES:
        panel[col] = panel[col].astype("float32")
    return panel


# ------------------------------------------------------------------ calibration & metrics
def apply_temperature(proba: np.ndarray, T: float) -> np.ndarray:
    logits = np.log(np.clip(proba, 1e-9, 1)) / T
    logits -= logits.max(axis=1, keepdims=True)
    e = np.exp(logits)
    return e / e.sum(axis=1, keepdims=True)


def fit_temperature(proba: np.ndarray, y: np.ndarray) -> float:
    def nll(T):
        p = apply_temperature(proba, T)
        return -np.mean(np.log(np.clip(p[np.arange(len(y)), y.astype(int)], 1e-12, 1)))
    res = minimize_scalar(nll, bounds=(0.25, 10.0), method="bounded")
    return float(res.x)


def brier(proba: np.ndarray, y: np.ndarray) -> float:
    onehot = np.eye(3)[y.astype(int)]
    return float(np.mean(np.sum((proba - onehot) ** 2, axis=1)))


def log_loss(proba: np.ndarray, y: np.ndarray) -> float:
    return float(-np.mean(np.log(np.clip(proba[np.arange(len(y)), y.astype(int)], 1e-12, 1))))


def reliability(p: np.ndarray, hit: np.ndarray, bins: int = 10) -> list[dict]:
    edges = np.linspace(0, 1, bins + 1)
    out = []
    for lo, hi in zip(edges[:-1], edges[1:]):
        m = (p >= lo) & (p < hi if hi < 1 else p <= hi)
        if m.sum() >= 20:
            out.append({"bin": f"{lo:.1f}-{hi:.1f}", "mean_predicted": round(float(p[m].mean()), 4),
                        "observed": round(float(hit[m].mean()), 4), "n": int(m.sum())})
    return out


def evaluate(proba: np.ndarray, y: np.ndarray, base: np.ndarray) -> dict:
    clim = np.tile(base, (len(y), 1))
    b, bc = brier(proba, y), brier(clim, y)
    pred = proba.argmax(axis=1)
    prec, rec, f1, sup = precision_recall_fscore_support(y, pred, labels=[0, 1, 2], zero_division=0)
    auc = {}
    for ci, name in ((2, "bullish"), (0, "bearish")):
        try:
            auc[name] = round(float(roc_auc_score((y == ci).astype(int), proba[:, ci])), 4)
        except ValueError:
            auc[name] = None
    return {
        "n": int(len(y)), "brier": round(b, 5), "brier_base_rate": round(bc, 5),
        "brier_skill_score": round(1 - b / bc, 5) if bc > 0 else None,
        "log_loss": round(log_loss(proba, y), 5), "log_loss_base_rate": round(log_loss(clim, y), 5),
        "roc_auc": auc,
        "per_class": {CLASSES[i]: {"precision": round(float(prec[i]), 4), "recall": round(float(rec[i]), 4),
                                   "f1": round(float(f1[i]), 4), "support": int(sup[i])} for i in range(3)},
        "confusion_matrix": {"labels": CLASSES, "matrix": confusion_matrix(y, pred, labels=[0, 1, 2]).tolist()},
        "reliability_bullish": reliability(proba[:, 2], (y == 2).astype(float)),
        "class_base_rates": [round(float(x), 4) for x in base],
    }


# ------------------------------------------------------------------ models
def _models(seed: int = 7) -> dict:
    return {
        "logistic_regression": lambda: make_pipeline(StandardScaler(), LogisticRegression(C=0.5, max_iter=500)),
        "gradient_boosting": lambda: HistGradientBoostingClassifier(
            max_iter=250, learning_rate=0.05, max_leaf_nodes=31, min_samples_leaf=200, l2_regularization=1.0,
            random_state=seed),
    }


def prune_correlated(X: pd.DataFrame, threshold: float = 0.9) -> list[str]:
    corr = X.corr().abs()
    keep: list[str] = []
    for col in X.columns:
        if X[col].notna().sum() == 0:
            continue
        if all(corr.loc[col, k] < threshold for k in keep if not np.isnan(corr.loc[col, k])):
            keep.append(col)
    return keep


def _fit_predict(make, Xtr, ytr, Xcal, ycal, Xte):
    model = make()
    # gradient boosting handles missing values natively; linear models need them filled
    if isinstance(model, HistGradientBoostingClassifier):
        Xtr_f, Xcal_f, Xte_f = Xtr, Xcal, Xte
    else:
        Xtr_f, Xcal_f, Xte_f = Xtr.fillna(0), Xcal.fillna(0), Xte.fillna(0)
    model.fit(Xtr_f, ytr)
    T = fit_temperature(model.predict_proba(Xcal_f), ycal)
    return model, T, apply_temperature(model.predict_proba(Xte_f), T)


def walk_forward(panel: pd.DataFrame, h: int, features: list[str], min_train_days: int = 500,
                 test_days: int = 126, max_train_rows: int = 400_000, seed: int = 7,
                 min_train_rows: int = 5000) -> tuple[pd.DataFrame, dict]:
    """Expanding-window walk-forward with an h-day purge. Returns (out-of-sample predictions, metrics)."""
    data = panel.dropna(subset=[f"y_{h}"])
    dates = np.sort(data["date"].unique())
    if len(dates) < min_train_days + test_days:
        return pd.DataFrame(), {"error": f"need ≥ {min_train_days + test_days} trading days, have {len(dates)}"}
    rng = np.random.default_rng(seed)
    preds = []
    for start in range(min_train_days, len(dates) - h, test_days):
        test_start, test_end = dates[start], dates[min(start + test_days, len(dates) - 1)]
        purge_end = dates[max(start - h - 1, 0)]
        train = data[data["date"] <= purge_end]
        test = data[(data["date"] >= test_start) & (data["date"] < test_end)]
        if len(test) == 0 or len(train) < min_train_rows:
            continue
        if len(train) > max_train_rows:
            train = train.iloc[np.sort(rng.choice(len(train), max_train_rows, replace=False))]
        cut = train["date"].quantile(0.85)
        tr, cal = train[train["date"] <= cut], train[train["date"] > cut]
        base = np.bincount(tr[f"y_{h}"].astype(int), minlength=3) / len(tr)
        fold = test[["symbol", "date", f"y_{h}", f"trade_{h}", f"fwd_{h}"]].copy()
        fold["train_end"] = train["date"].max()
        fold["base_bear"], fold["base_neu"], fold["base_bull"] = base
        ens = None
        for name, make in _models(seed).items():
            _, _, p = _fit_predict(make, tr[features], tr[f"y_{h}"], cal[features], cal[f"y_{h}"].to_numpy(), test[features])
            fold[[f"{name}_bear", f"{name}_neu", f"{name}_bull"]] = p
            ens = p if ens is None else (ens + p)
        ens = ens / len(_models())
        fold[["ensemble_bear", "ensemble_neu", "ensemble_bull"]] = ens
        preds.append(fold)
    if not preds:
        return pd.DataFrame(), {"error": "no walk-forward folds could be built"}
    oos = pd.concat(preds, ignore_index=True)
    y = oos[f"y_{h}"].to_numpy().astype(int)
    base = oos[["base_bear", "base_neu", "base_bull"]].to_numpy()
    metrics = {}
    for name in list(_models()) + ["ensemble"]:
        p = oos[[f"{name}_bear", f"{name}_neu", f"{name}_bull"]].to_numpy()
        m = evaluate(p, y, base.mean(axis=0))
        # use the fold-specific base rates for the honest skill comparison
        m["brier_base_rate"] = round(float(np.mean(np.sum((base - np.eye(3)[y]) ** 2, axis=1))), 5)
        m["brier_skill_score"] = round(1 - m["brier"] / m["brier_base_rate"], 5)
        m["log_loss_base_rate"] = round(log_loss(base, y), 5)
        metrics[name] = m
    metrics["_folds"] = len(preds)
    metrics["_oos_period"] = [str(pd.Timestamp(oos["date"].min()).date()), str(pd.Timestamp(oos["date"].max()).date())]
    return oos, metrics


def choose_thresholds(oos: pd.DataFrame, h: int, model: str) -> dict:
    """Pick P(class) cut-offs on the first half of OOS data, report on the second half."""
    oos = oos.sort_values("date")
    mid = oos["date"].iloc[len(oos) // 2]
    a, b = oos[oos["date"] < mid], oos[oos["date"] >= mid]
    out = {}
    for cls, idx, col in (("bullish", 2, f"{model}_bull"), ("bearish", 0, f"{model}_bear")):
        base_a = float((a[f"y_{h}"] == idx).mean())
        best = None
        for t in np.arange(0.40, 0.76, 0.05):
            sel = a[a[col] >= t]
            if len(sel) < max(50, 0.005 * len(a)):
                continue
            prec = float((sel[f"y_{h}"] == idx).mean())
            if best is None or prec > best[1]:
                best = (round(float(t), 2), prec)
        if best is None:
            out[cls] = {"threshold": None, "reason": "no threshold had enough signals"}
            continue
        sel_b = b[b[col] >= best[0]]
        base_b = float((b[f"y_{h}"] == idx).mean())
        hits = int((sel_b[f"y_{h}"] == idx).sum())
        prec_b = hits / len(sel_b) if len(sel_b) else None
        # one-sided binomial test, using the number of distinct signal DATES as a conservative n
        n_eff = int(sel_b["date"].nunique()) if len(sel_b) else 0
        p_value = float(binomtest(int(round(prec_b * n_eff)), n_eff, base_b, alternative="greater").pvalue) \
            if n_eff and prec_b is not None and 0 < base_b < 1 else None
        out[cls] = {"threshold": best[0], "selection_precision": round(best[1], 4), "selection_base_rate": round(base_a, 4),
                    "holdout_precision": round(prec_b, 4) if prec_b is not None else None,
                    "holdout_base_rate": round(base_b, 4), "holdout_signals": int(len(sel_b)),
                    "holdout_signal_dates": n_eff,
                    "holdout_lift": round(prec_b / base_b, 3) if prec_b and base_b else None,
                    "p_value": round(p_value, 5) if p_value is not None else None,
                    "validated": bool(prec_b is not None and len(sel_b) >= MIN_HOLDOUT_SIGNALS
                                      and prec_b > base_b * 1.05 and p_value is not None and p_value < 0.05)}
    return out


def bss_block_bootstrap(oos: pd.DataFrame, h: int, model: str, block: int = 21, reps: int = 500,
                        seed: int = 11) -> dict:
    """Moving-block bootstrap over DATES (stocks on the same day are correlated, and overlapping
    labels are autocorrelated), so the confidence interval is not over-optimistic."""
    y = oos[f"y_{h}"].to_numpy().astype(int)
    onehot = np.eye(3)[y]
    p = oos[[f"{model}_bear", f"{model}_neu", f"{model}_bull"]].to_numpy()
    base = oos[["base_bear", "base_neu", "base_bull"]].to_numpy()
    per = pd.DataFrame({"date": oos["date"].to_numpy(), "b": np.sum((p - onehot) ** 2, axis=1),
                        "bc": np.sum((base - onehot) ** 2, axis=1)}).groupby("date")[["b", "bc"]].sum()
    b, bc = per["b"].to_numpy(), per["bc"].to_numpy()
    n = len(b)
    if n < block * 3:
        return {"lower_5pct": None, "median": None, "n_dates": int(n)}
    rng = np.random.default_rng(seed)
    starts = rng.integers(0, n - block + 1, size=(reps, int(np.ceil(n / block))))
    idx = (starts[:, :, None] + np.arange(block)[None, None, :]).reshape(reps, -1)[:, :n]
    bss = 1 - b[idx].sum(axis=1) / bc[idx].sum(axis=1)
    return {"lower_5pct": round(float(np.quantile(bss, 0.05)), 5), "median": round(float(np.median(bss)), 5),
            "n_dates": int(n), "block_days": block, "reps": reps}


def gate(metrics: dict, model: str, min_bss: float, min_n: int, boot: dict | None = None) -> dict:
    m = metrics.get(model, {})
    reasons = []
    if m.get("n", 0) < min_n:
        reasons.append(f"only {m.get('n', 0)} out-of-sample predictions (< {min_n})")
    if (m.get("brier_skill_score") or -1) < min_bss:
        reasons.append(f"Brier skill score {m.get('brier_skill_score')} below {min_bss} (does not beat base rates)")
    if m.get("log_loss", 9) >= m.get("log_loss_base_rate", 0):
        reasons.append("log-loss not better than base-rate forecast")
    if boot is not None and (boot.get("lower_5pct") is None or boot["lower_5pct"] <= 0):
        reasons.append(f"skill not statistically reliable (bootstrap 5th percentile of Brier skill = "
                       f"{boot.get('lower_5pct')}, must be > 0)")
    return {"passed": not reasons, "reasons": reasons, "bootstrap": boot, "criteria": {
        "min_brier_skill_score": min_bss, "min_oos_samples": min_n, "log_loss_must_beat_base_rate": True,
        "bootstrap_lower_5pct_brier_skill_must_exceed": 0.0}}


def train_final(panel: pd.DataFrame, h: int, features: list[str], model_name: str, seed: int = 7,
                max_rows: int = 500_000):
    data = panel.dropna(subset=[f"y_{h}"])
    if len(data) > max_rows:
        data = data.iloc[np.sort(np.random.default_rng(seed).choice(len(data), max_rows, replace=False))]
    cut = data["date"].quantile(0.85)
    tr, cal = data[data["date"] <= cut], data[data["date"] > cut]
    makers = _models(seed)
    names = list(makers) if model_name == "ensemble" else [model_name]
    parts = []
    for n in names:
        model, T, _ = _fit_predict(makers[n], tr[features], tr[f"y_{h}"], cal[features], cal[f"y_{h}"].to_numpy(),
                                   cal[features].iloc[:1])
        parts.append((n, model, T))
    return {"parts": parts, "features": features, "horizon": h, "model_name": model_name,
            "trained_at": datetime.now(timezone.utc).isoformat(), "train_rows": int(len(data)),
            "train_end": str(pd.Timestamp(data["date"].max()).date())}


def predict(bundle: dict, X: pd.DataFrame) -> np.ndarray:
    total = None
    for name, model, T in bundle["parts"]:
        Xf = X[bundle["features"]]
        if not isinstance(model, HistGradientBoostingClassifier):
            Xf = Xf.fillna(0)
        p = apply_temperature(model.predict_proba(Xf), T)
        total = p if total is None else total + p
    return total / len(bundle["parts"])


def run(panel: pd.DataFrame, horizons: list[int], cache_dir: Path, settings, force: bool = False) -> dict:
    """Train/validate (when due) and return {h: {bundle, report, oos}}."""
    model_dir = Path(cache_dir) / "models"
    model_dir.mkdir(parents=True, exist_ok=True)
    results = {}
    for h in horizons:
        path = model_dir / f"swing_h{h}.pkl"
        if path.exists() and not force:
            with open(path, "rb") as fh:
                saved = pickle.load(fh)
            age = (datetime.now(timezone.utc) - datetime.fromisoformat(saved["report"]["trained_at"])).days
            if age < settings.retrain_every_days:
                results[h] = saved
                continue
        base_feats = [f for f in FEATURES if panel[f].notna().mean() > 0.5]
        feats = prune_correlated(panel[base_feats].dropna().sample(min(100_000, len(panel.dropna(subset=base_feats))),
                                                                   random_state=1))
        oos, metrics = walk_forward(panel, h, feats)
        if oos.empty:
            report = {"horizon": h, "trained_at": datetime.now(timezone.utc).isoformat(), "gate": {
                "passed": False, "reasons": [metrics.get("error", "validation failed")]}, "metrics": metrics}
            results[h] = {"bundle": None, "report": report, "oos": pd.DataFrame()}
            continue
        candidates = [m for m in metrics if not m.startswith("_")]
        best = min(candidates, key=lambda m: metrics[m]["log_loss"])
        boot = bss_block_bootstrap(oos, h, best)
        g = gate(metrics, best, settings.gate_min_brier_skill, settings.gate_min_samples, boot)
        thresholds = choose_thresholds(oos, h, best)
        bundle = train_final(panel, h, feats, best) if g["passed"] else None
        report = {"horizon": h, "selected_model": best, "features": feats,
                  "features_dropped_correlated": [f for f in base_feats if f not in feats],
                  "metrics": metrics, "gate": g, "thresholds": thresholds,
                  "trained_at": datetime.now(timezone.utc).isoformat(),
                  "train_end": bundle["train_end"] if bundle else None,
                  "label_definition": f"bullish if {h}-day return > max({settings.neutral_band_k}·σ20·√{h}, "
                                      f"{settings.min_neutral_band:.1%}); bearish if < −band; else neutral",
                  "validation": "expanding walk-forward, 126-day test folds, purge gap = horizon, temperature-scaled"}
        keep = oos[["symbol", "date", f"y_{h}", f"trade_{h}", f"fwd_{h}", f"{best}_bear", f"{best}_neu", f"{best}_bull"]]
        results[h] = {"bundle": bundle, "report": report, "oos": keep}
        with open(path, "wb") as fh:
            pickle.dump(results[h], fh)
    return results
