"""Technical indicator library — custom, dependency-free (pandas/numpy) implementations.

Conventions (documented so results can be checked against textbooks):
  * EMA is seeded with the SMA of the first n values (StockCharts / textbook convention).
  * Wilder smoothing (RSI, ATR, ADX) uses alpha = 1/n, seeded with a simple mean.
  * Bollinger Bands use the population standard deviation (ddof=0), as John Bollinger specifies.
  * All functions are causal (use only past and current bars) EXCEPT ichimoku()['chikou'],
    which is a display-only line and is never used as a model feature.
Every indicator's formula, meaning and bilingual explanation lives in pipeline/knowledge.py.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


# ---------------------------------------------------------------- moving averages
def sma(s: pd.Series, n: int) -> pd.Series:
    return s.rolling(n, min_periods=n).mean()


def _seeded_recursive(values: np.ndarray, n: int, alpha: float) -> np.ndarray:
    out = np.full(len(values), np.nan)
    valid = np.where(~np.isnan(values))[0]
    if len(valid) < n:
        return out
    start = valid[0]
    seed_end = start + n - 1
    if np.isnan(values[start:seed_end + 1]).any():
        # fall back: seed at first window without gaps
        for i in range(start, len(values) - n + 1):
            if not np.isnan(values[i:i + n]).any():
                seed_end = i + n - 1
                break
        else:
            return out
    out[seed_end] = np.mean(values[seed_end - n + 1:seed_end + 1])
    prev = out[seed_end]
    for i in range(seed_end + 1, len(values)):
        v = values[i]
        if np.isnan(v):
            out[i] = prev
            continue
        prev = alpha * v + (1 - alpha) * prev
        out[i] = prev
    return out


def ema(s: pd.Series, n: int) -> pd.Series:
    return pd.Series(_seeded_recursive(s.to_numpy(dtype=float), n, 2.0 / (n + 1)), index=s.index)


def rma(s: pd.Series, n: int) -> pd.Series:
    """Wilder's moving average (a.k.a. SMMA)."""
    return pd.Series(_seeded_recursive(s.to_numpy(dtype=float), n, 1.0 / n), index=s.index)


def wma(s: pd.Series, n: int) -> pd.Series:
    w = np.arange(1, n + 1, dtype=float)
    return s.rolling(n, min_periods=n).apply(lambda x: np.dot(x, w) / w.sum(), raw=True)


def dema(s: pd.Series, n: int) -> pd.Series:
    e1 = ema(s, n)
    return 2 * e1 - ema(e1, n)


def tema(s: pd.Series, n: int) -> pd.Series:
    e1 = ema(s, n)
    e2 = ema(e1, n)
    return 3 * e1 - 3 * e2 + ema(e2, n)


def hma(s: pd.Series, n: int) -> pd.Series:
    half = max(int(n / 2), 1)
    root = max(int(np.sqrt(n)), 1)
    return wma(2 * wma(s, half) - wma(s, n), root)


# ---------------------------------------------------------------- momentum
def rsi(close: pd.Series, n: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)
    # first change is NaN; Wilder seeds with mean of the first n changes
    avg_gain = rma(gain, n)
    avg_loss = rma(loss, n)
    rs = avg_gain / avg_loss.replace(0, np.nan)
    out = 100 - 100 / (1 + rs)
    out[(avg_loss == 0) & (avg_gain > 0)] = 100.0
    out[(avg_loss == 0) & (avg_gain == 0)] = 50.0
    return out


def macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.DataFrame:
    line = ema(close, fast) - ema(close, slow)
    sig = ema(line, signal)
    return pd.DataFrame({"macd": line, "macd_signal": sig, "macd_hist": line - sig})


def stochastic(df: pd.DataFrame, n: int = 14, d: int = 3) -> pd.DataFrame:
    ll = df["low"].rolling(n).min()
    hh = df["high"].rolling(n).max()
    k = 100 * (df["close"] - ll) / (hh - ll).replace(0, np.nan)
    return pd.DataFrame({"stoch_k": k, "stoch_d": sma(k, d)})


def stoch_rsi(close: pd.Series, n: int = 14, k: int = 3, d: int = 3) -> pd.DataFrame:
    r = rsi(close, n)
    lo, hi = r.rolling(n).min(), r.rolling(n).max()
    raw = 100 * (r - lo) / (hi - lo).replace(0, np.nan)
    kk = sma(raw, k)
    return pd.DataFrame({"stochrsi_k": kk, "stochrsi_d": sma(kk, d)})


def roc(close: pd.Series, n: int = 12) -> pd.Series:
    return 100 * (close / close.shift(n) - 1)


def momentum(close: pd.Series, n: int = 10) -> pd.Series:
    return close - close.shift(n)


def cci(df: pd.DataFrame, n: int = 20) -> pd.Series:
    tp = (df["high"] + df["low"] + df["close"]) / 3
    mean = tp.rolling(n).mean()
    mad = tp.rolling(n).apply(lambda x: np.mean(np.abs(x - x.mean())), raw=True)
    return (tp - mean) / (0.015 * mad.replace(0, np.nan))


def williams_r(df: pd.DataFrame, n: int = 14) -> pd.Series:
    hh = df["high"].rolling(n).max()
    ll = df["low"].rolling(n).min()
    return -100 * (hh - df["close"]) / (hh - ll).replace(0, np.nan)


# ---------------------------------------------------------------- volatility
def true_range(df: pd.DataFrame) -> pd.Series:
    prev = df["close"].shift(1)
    tr = pd.concat([df["high"] - df["low"], (df["high"] - prev).abs(), (df["low"] - prev).abs()], axis=1)
    tr = tr.max(axis=1)
    tr.iloc[0] = df["high"].iloc[0] - df["low"].iloc[0]
    return tr


def atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    return rma(true_range(df), n)


def bollinger(close: pd.Series, n: int = 20, k: float = 2.0) -> pd.DataFrame:
    mid = sma(close, n)
    sd = close.rolling(n).std(ddof=0)
    up, lo = mid + k * sd, mid - k * sd
    return pd.DataFrame({"bb_mid": mid, "bb_upper": up, "bb_lower": lo,
                         "bb_pctb": (close - lo) / (up - lo).replace(0, np.nan),
                         "bb_width": (up - lo) / mid})


def keltner(df: pd.DataFrame, n: int = 20, atr_n: int = 10, k: float = 2.0) -> pd.DataFrame:
    mid = ema(df["close"], n)
    a = atr(df, atr_n)
    return pd.DataFrame({"kc_mid": mid, "kc_upper": mid + k * a, "kc_lower": mid - k * a})


def donchian(df: pd.DataFrame, n: int = 20) -> pd.DataFrame:
    up = df["high"].rolling(n).max()
    lo = df["low"].rolling(n).min()
    return pd.DataFrame({"dc_upper": up, "dc_lower": lo, "dc_mid": (up + lo) / 2})


def stddev(close: pd.Series, n: int = 20) -> pd.Series:
    return close.rolling(n).std(ddof=1)


def historical_volatility(close: pd.Series, n: int = 20, periods: int = 252) -> pd.Series:
    lr = np.log(close / close.shift(1))
    return lr.rolling(n).std(ddof=1) * np.sqrt(periods) * 100


# ---------------------------------------------------------------- volume
def rolling_vwap(df: pd.DataFrame, n: int = 20) -> pd.Series:
    """Rolling n-day VWAP from DAILY bars. True intraday VWAP needs intraday data."""
    tp = (df["high"] + df["low"] + df["close"]) / 3
    pv = (tp * df["volume"]).rolling(n).sum()
    return pv / df["volume"].rolling(n).sum().replace(0, np.nan)


def obv(df: pd.DataFrame) -> pd.Series:
    direction = np.sign(df["close"].diff()).fillna(0)
    return (direction * df["volume"]).cumsum()


def _mfm(df: pd.DataFrame) -> pd.Series:
    rng = (df["high"] - df["low"]).replace(0, np.nan)
    return (((df["close"] - df["low"]) - (df["high"] - df["close"])) / rng).fillna(0)


def ad_line(df: pd.DataFrame) -> pd.Series:
    return (_mfm(df) * df["volume"]).cumsum()


def cmf(df: pd.DataFrame, n: int = 20) -> pd.Series:
    mfv = _mfm(df) * df["volume"]
    return mfv.rolling(n).sum() / df["volume"].rolling(n).sum().replace(0, np.nan)


def mfi(df: pd.DataFrame, n: int = 14) -> pd.Series:
    tp = (df["high"] + df["low"] + df["close"]) / 3
    raw = tp * df["volume"]
    up = raw.where(tp > tp.shift(1), 0.0)
    down = raw.where(tp < tp.shift(1), 0.0)
    pos, neg = up.rolling(n).sum(), down.rolling(n).sum()
    out = 100 - 100 / (1 + pos / neg.replace(0, np.nan))
    out[(neg == 0) & (pos > 0)] = 100.0
    return out


def volume_roc(df: pd.DataFrame, n: int = 14) -> pd.Series:
    return 100 * (df["volume"] / df["volume"].shift(n).replace(0, np.nan) - 1)


def relative_volume(df: pd.DataFrame, n: int = 20) -> pd.Series:
    """Today's volume vs the average of the PREVIOUS n sessions."""
    return df["volume"] / df["volume"].shift(1).rolling(n).mean().replace(0, np.nan)


# ---------------------------------------------------------------- trend
def adx(df: pd.DataFrame, n: int = 14) -> pd.DataFrame:
    up = df["high"].diff()
    down = -df["low"].diff()
    plus_dm = pd.Series(np.where((up > down) & (up > 0), up, 0.0), index=df.index)
    minus_dm = pd.Series(np.where((down > up) & (down > 0), down, 0.0), index=df.index)
    plus_dm.iloc[0] = minus_dm.iloc[0] = np.nan
    tr = true_range(df)
    tr.iloc[0] = np.nan
    s_tr, s_p, s_m = rma(tr, n), rma(plus_dm, n), rma(minus_dm, n)
    pdi = 100 * s_p / s_tr.replace(0, np.nan)
    mdi = 100 * s_m / s_tr.replace(0, np.nan)
    dx = 100 * (pdi - mdi).abs() / (pdi + mdi).replace(0, np.nan)
    return pd.DataFrame({"plus_di": pdi, "minus_di": mdi, "adx": rma(dx, n)})


def parabolic_sar(df: pd.DataFrame, step: float = 0.02, max_af: float = 0.2) -> pd.Series:
    high, low = df["high"].to_numpy(float), df["low"].to_numpy(float)
    n = len(df)
    sar = np.full(n, np.nan)
    if n < 3:
        return pd.Series(sar, index=df.index)
    up = high[1] >= high[0]
    ep = high[1] if up else low[1]
    sar[1] = low[0] if up else high[0]
    af = step
    for i in range(2, n):
        prev = sar[i - 1]
        cur = prev + af * (ep - prev)
        if up:
            cur = min(cur, low[i - 1], low[i - 2])
            if low[i] < cur:
                up, cur, ep, af = False, ep, low[i], step
            elif high[i] > ep:
                ep, af = high[i], min(af + step, max_af)
        else:
            cur = max(cur, high[i - 1], high[i - 2])
            if high[i] > cur:
                up, cur, ep, af = True, ep, high[i], step
            elif low[i] < ep:
                ep, af = low[i], min(af + step, max_af)
        sar[i] = cur
    return pd.Series(sar, index=df.index)


def ichimoku(df: pd.DataFrame, t: int = 9, k: int = 26, b: int = 52) -> pd.DataFrame:
    mid = lambda n: (df["high"].rolling(n).max() + df["low"].rolling(n).min()) / 2  # noqa: E731
    tenkan, kijun = mid(t), mid(k)
    return pd.DataFrame({
        "ichi_tenkan": tenkan, "ichi_kijun": kijun,
        # spans are plotted k bars ahead; the value "at" today was computed k bars ago (causal)
        "ichi_span_a": ((tenkan + kijun) / 2).shift(k),
        "ichi_span_b": mid(b).shift(k),
        "ichi_chikou": df["close"].shift(-k),  # display only - looks ahead, never a feature
    })


def supertrend(df: pd.DataFrame, n: int = 10, mult: float = 3.0) -> pd.DataFrame:
    a = atr(df, n).to_numpy(float)
    hl2 = ((df["high"] + df["low"]) / 2).to_numpy(float)
    close = df["close"].to_numpy(float)
    bu, bl = hl2 + mult * a, hl2 - mult * a
    fu, fl = bu.copy(), bl.copy()
    st = np.full(len(df), np.nan)
    direction = np.zeros(len(df))
    for i in range(1, len(df)):
        if np.isnan(a[i]):
            continue
        if not np.isnan(fu[i - 1]):
            fu[i] = bu[i] if (bu[i] < fu[i - 1] or close[i - 1] > fu[i - 1]) else fu[i - 1]
            fl[i] = bl[i] if (bl[i] > fl[i - 1] or close[i - 1] < fl[i - 1]) else fl[i - 1]
        prev_dir = direction[i - 1] if direction[i - 1] != 0 else 1
        if prev_dir == 1:
            direction[i] = -1 if close[i] < fl[i] else 1
        else:
            direction[i] = 1 if close[i] > fu[i] else -1
        st[i] = fl[i] if direction[i] == 1 else fu[i]
    return pd.DataFrame({"supertrend": st, "supertrend_dir": direction}, index=df.index)


# ---------------------------------------------------------------- price structure
def pivot_points(prev_high: float, prev_low: float, prev_close: float) -> dict:
    p = (prev_high + prev_low + prev_close) / 3
    return {"P": p, "R1": 2 * p - prev_low, "S1": 2 * p - prev_high,
            "R2": p + (prev_high - prev_low), "S2": p - (prev_high - prev_low),
            "R3": prev_high + 2 * (p - prev_low), "S3": prev_low - 2 * (prev_high - p)}


def fibonacci(df: pd.DataFrame, lookback: int = 120) -> dict:
    win = df.tail(lookback)
    hi, lo = float(win["high"].max()), float(win["low"].min())
    hi_i, lo_i = win["high"].idxmax(), win["low"].idxmin()
    rng = hi - lo
    uptrend = lo_i < hi_i   # swing low came first -> retrace down from the high
    ratios = [0.236, 0.382, 0.5, 0.618, 0.786]
    ext = [1.272, 1.618, 2.618]
    if uptrend:
        retr = {f"{r*100:.1f}%": hi - r * rng for r in ratios}
        exts = {f"{r*100:.1f}%": lo + r * rng for r in ext}
    else:
        retr = {f"{r*100:.1f}%": lo + r * rng for r in ratios}
        exts = {f"{r*100:.1f}%": hi - r * rng for r in ext}
    return {"swing_high": hi, "swing_low": lo, "direction": "up" if uptrend else "down",
            "retracement": retr, "extension": exts}


def swing_points(df: pd.DataFrame, w: int = 5) -> tuple[pd.Series, pd.Series]:
    """Confirmed swing highs/lows (need w bars on both sides — so the last w bars have none)."""
    h, l = df["high"], df["low"]
    is_hi = h == h.rolling(2 * w + 1, center=True).max()
    is_lo = l == l.rolling(2 * w + 1, center=True).min()
    return h[is_hi.fillna(False)], l[is_lo.fillna(False)]


def support_resistance(df: pd.DataFrame, lookback: int = 250, w: int = 5, max_levels: int = 3) -> dict:
    win = df.tail(lookback)
    if len(win) < 2 * w + 5:
        return {"support": [], "resistance": []}
    highs, lows = swing_points(win, w)
    price = float(win["close"].iloc[-1])
    tol = float(atr(win, 14).iloc[-1] or price * 0.015) * 0.6
    levels = sorted(list(highs.values) + list(lows.values))
    clusters: list[list[float]] = []
    for lv in levels:
        if clusters and abs(lv - np.mean(clusters[-1])) <= tol:
            clusters[-1].append(lv)
        else:
            clusters.append([lv])
    zones = [{"level": round(float(np.mean(c)), 2), "touches": len(c)} for c in clusters]
    sup = sorted([z for z in zones if z["level"] < price], key=lambda z: -z["level"])[:max_levels]
    res = sorted([z for z in zones if z["level"] > price], key=lambda z: z["level"])[:max_levels]
    return {"support": sup, "resistance": res}


def market_structure(df: pd.DataFrame, w: int = 5) -> dict:
    highs, lows = swing_points(df.tail(250), w)
    if len(highs) < 2 or len(lows) < 2:
        return {"structure": "insufficient swings", "hh": None, "hl": None}
    hh = bool(highs.iloc[-1] > highs.iloc[-2])
    hl = bool(lows.iloc[-1] > lows.iloc[-2])
    if hh and hl:
        s = "uptrend (higher highs and higher lows)"
    elif not hh and not hl:
        s = "downtrend (lower highs and lower lows)"
    else:
        s = "mixed / range-bound"
    return {"structure": s, "hh": hh, "hl": hl,
            "last_swing_high": round(float(highs.iloc[-1]), 2), "last_swing_low": round(float(lows.iloc[-1]), 2)}


def gaps(df: pd.DataFrame) -> pd.Series:
    """+pct gap-up (open above previous high), -pct gap-down (open below previous low), else 0."""
    ph, pl = df["high"].shift(1), df["low"].shift(1)
    up = np.where(df["open"] > ph, 100 * (df["open"] / ph - 1), 0.0)
    dn = np.where(df["open"] < pl, 100 * (df["open"] / pl - 1), 0.0)
    return pd.Series(up + dn, index=df.index)


def candlestick_patterns(df: pd.DataFrame) -> pd.DataFrame:
    o, h, l, c = df["open"], df["high"], df["low"], df["close"]
    body = (c - o).abs()
    rng = (h - l).replace(0, np.nan)
    upper = h - pd.concat([o, c], axis=1).max(axis=1)
    lower = pd.concat([o, c], axis=1).min(axis=1) - l
    trend_down = c.shift(1) < sma(c, 10).shift(1)
    trend_up = c.shift(1) > sma(c, 10).shift(1)
    po, pc = o.shift(1), c.shift(1)
    out = pd.DataFrame(index=df.index)
    out["doji"] = body <= 0.1 * rng
    out["hammer"] = (lower >= 2 * body) & (upper <= 0.3 * body.clip(lower=1e-9) + 0.1 * rng) & trend_down
    out["shooting_star"] = (upper >= 2 * body) & (lower <= 0.3 * body.clip(lower=1e-9) + 0.1 * rng) & trend_up
    out["bullish_engulfing"] = (pc < po) & (c > o) & (c >= po) & (o <= pc) & trend_down
    out["bearish_engulfing"] = (pc > po) & (c < o) & (o >= pc) & (c <= po) & trend_up
    b2 = body.shift(1)
    out["morning_star"] = (c.shift(2) < o.shift(2)) & (b2 < 0.3 * body.shift(2)) & (c > o) & \
                          (c > (o.shift(2) + c.shift(2)) / 2) & trend_down.shift(1, fill_value=False)
    out["evening_star"] = (c.shift(2) > o.shift(2)) & (b2 < 0.3 * body.shift(2)) & (c < o) & \
                          (c < (o.shift(2) + c.shift(2)) / 2) & trend_up.shift(1, fill_value=False)
    return out.fillna(False)


def breakout_signals(df: pd.DataFrame, n: int = 20, vol_x: float = 1.5) -> pd.DataFrame:
    prior_hi = df["high"].shift(1).rolling(n).max()
    prior_lo = df["low"].shift(1).rolling(n).min()
    rv = relative_volume(df, n)
    return pd.DataFrame({"breakout": (df["close"] > prior_hi) & (rv >= vol_x),
                         "breakdown": (df["close"] < prior_lo) & (rv >= vol_x)})


# ---------------------------------------------------------------- relative / advanced
def relative_strength(close: pd.Series, bench: pd.Series, n: int = 63) -> pd.Series:
    """n-day return of the stock minus n-day return of the benchmark (percentage points)."""
    b = bench.reindex(close.index).ffill()
    return 100 * ((close / close.shift(n)) - (b / b.shift(n)))


def beta_corr(close: pd.Series, bench: pd.Series, n: int = 252) -> tuple[float | None, float | None]:
    b = bench.reindex(close.index).ffill()
    r = pd.concat([close.pct_change(), b.pct_change()], axis=1).dropna().tail(n)
    if len(r) < 60:
        return None, None
    cov = np.cov(r.iloc[:, 0], r.iloc[:, 1], ddof=1)
    beta = cov[0, 1] / cov[1, 1] if cov[1, 1] > 0 else None
    corr = float(r.iloc[:, 0].corr(r.iloc[:, 1]))
    return (float(beta) if beta is not None else None), corr


def volatility_regime(close: pd.Series) -> str:
    hv = historical_volatility(close, 20).dropna().tail(252)
    if len(hv) < 60:
        return "unknown"
    pct = float((hv < hv.iloc[-1]).mean())
    return "high" if pct >= 0.8 else "low" if pct <= 0.2 else "normal"


# ---------------------------------------------------------------- bundle
def compute_all(df: pd.DataFrame, bench: pd.Series | None = None) -> pd.DataFrame:
    c = df["close"]
    out = pd.DataFrame(index=df.index)
    for n in (20, 50, 200):
        out[f"sma_{n}"] = sma(c, n)
    for n in (9, 20, 50):
        out[f"ema_{n}"] = ema(c, n)
    out["wma_20"] = wma(c, 20)
    out["dema_20"] = dema(c, 20)
    out["tema_20"] = tema(c, 20)
    out["hma_20"] = hma(c, 20)
    out["rsi_14"] = rsi(c, 14)
    out = out.join(macd(c)).join(stochastic(df)).join(stoch_rsi(c))
    out["roc_12"] = roc(c, 12)
    out["mom_10"] = momentum(c, 10)
    out["cci_20"] = cci(df, 20)
    out["willr_14"] = williams_r(df, 14)
    out = out.join(bollinger(c))
    out["atr_14"] = atr(df, 14)
    out = out.join(keltner(df)).join(donchian(df))
    out["stddev_20"] = stddev(c, 20)
    out["hv_20"] = historical_volatility(c, 20)
    out["vwap_20"] = rolling_vwap(df, 20)
    out["obv"] = obv(df)
    out["ad_line"] = ad_line(df)
    out["cmf_20"] = cmf(df, 20)
    out["mfi_14"] = mfi(df, 14)
    out["vroc_14"] = volume_roc(df, 14)
    out["rel_volume"] = relative_volume(df, 20)
    out = out.join(adx(df))
    out["psar"] = parabolic_sar(df)
    out = out.join(ichimoku(df)).join(supertrend(df))
    out["gap_pct"] = gaps(df)
    out = out.join(breakout_signals(df))
    if bench is not None:
        out["rs_63"] = relative_strength(c, bench, 63)
    return out
