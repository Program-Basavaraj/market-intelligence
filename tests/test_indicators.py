"""Indicator tests against published examples and independent slow reference implementations."""
import numpy as np
import pandas as pd
import pytest

from pipeline import indicators as ind
from tests.fakes import synthetic_ohlcv

# StockCharts RSI worked example (closes) and its published RSI values
SC_CLOSE = [44.3389, 44.0902, 44.1497, 43.6124, 44.2779, 44.8264, 45.0955, 45.4245, 45.8433, 46.0826,
            45.8931, 46.0328, 45.6140, 46.2820, 46.2820, 46.0028, 46.0328, 46.4116, 46.2222, 45.6439]
SC_RSI = [70.53, 66.32, 66.55, 69.41, 66.36, 57.97]


def test_rsi_matches_stockcharts_example():
    r = ind.rsi(pd.Series(SC_CLOSE), 14)
    assert r.iloc[:14].isna().all()
    np.testing.assert_allclose(r.iloc[14:].round(2).tolist(), SC_RSI, atol=0.01)


def test_rsi_bounds_and_flat_series():
    df = synthetic_ohlcv(300)
    r = ind.rsi(df["close"]).dropna()
    assert r.between(0, 100).all()
    flat = ind.rsi(pd.Series([100.0] * 30)).dropna()
    assert (flat == 50).all()
    rising = ind.rsi(pd.Series(np.arange(1, 40, dtype=float))).dropna()
    assert (rising == 100).all()


def test_sma_ema_wma_known_values():
    s = pd.Series([100, 102, 101, 104, 103], dtype=float)
    assert ind.sma(s, 5).iloc[-1] == pytest.approx(102.0)
    e = ind.ema(pd.Series([1, 2, 3, 4, 5, 6], dtype=float), 3)
    # seed = mean(1,2,3) = 2; alpha = 0.5 -> 3, 4, 5
    assert e.tolist()[2:] == pytest.approx([2, 3, 4, 5])
    assert ind.wma(pd.Series([100, 102, 104], dtype=float), 3).iloc[-1] == pytest.approx((100 + 204 + 312) / 6)


def test_dema_tema_hma_track_a_linear_trend_without_lag():
    s = pd.Series(np.arange(300, dtype=float))
    assert ind.dema(s, 10).iloc[-1] == pytest.approx(299, abs=1e-6)
    assert ind.tema(s, 10).iloc[-1] == pytest.approx(299, abs=1e-6)
    # HMA(16) with integer windows has a residual lag of 2/3 bar on a straight line; EMA(10) lags 4.5 bars
    assert ind.hma(s, 16).iloc[-1] == pytest.approx(299 - 2 / 3, abs=1e-9)
    assert 299 - ind.ema(s, 10).iloc[-1] == pytest.approx(4.5, abs=1e-6)


def test_macd_identity():
    c = synthetic_ohlcv(200)["close"]
    m = ind.macd(c)
    np.testing.assert_allclose((ind.ema(c, 12) - ind.ema(c, 26)).dropna(), m["macd"].dropna())
    np.testing.assert_allclose((m["macd"] - m["macd_signal"]).dropna(), m["macd_hist"].dropna())


def test_bollinger_uses_population_std():
    s = pd.Series(np.arange(1, 21, dtype=float))
    bb = ind.bollinger(s, 20, 2)
    sd = np.std(np.arange(1, 21), ddof=0)
    assert bb["bb_upper"].iloc[-1] == pytest.approx(10.5 + 2 * sd)
    assert bb["bb_pctb"].iloc[-1] == pytest.approx((20 - (10.5 - 2 * sd)) / (4 * sd))


def _atr_reference(df, n=14):
    h, l, c = df["high"].values, df["low"].values, df["close"].values
    tr = [h[0] - l[0]] + [max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1])) for i in range(1, len(df))]
    out = [np.nan] * len(df)
    out[n - 1] = sum(tr[:n]) / n
    for i in range(n, len(df)):
        out[i] = (out[i - 1] * (n - 1) + tr[i]) / n
    return np.array(out)


def test_atr_matches_wilder_reference():
    df = synthetic_ohlcv(120, seed=3)
    np.testing.assert_allclose(ind.atr(df, 14).values, _atr_reference(df), equal_nan=True, rtol=1e-10)


def _adx_reference(df, n=14):
    h, l, c = df["high"].values, df["low"].values, df["close"].values
    N = len(df)
    tr, pdm, mdm = np.zeros(N), np.zeros(N), np.zeros(N)
    for i in range(1, N):
        up, dn = h[i] - h[i - 1], l[i - 1] - l[i]
        pdm[i] = up if up > dn and up > 0 else 0
        mdm[i] = dn if dn > up and dn > 0 else 0
        tr[i] = max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1]))
    def wilder(x):
        o = np.full(N, np.nan)
        o[n] = x[1:n + 1].mean()
        for i in range(n + 1, N):
            o[i] = (o[i - 1] * (n - 1) + x[i]) / n
        return o
    s_tr, s_p, s_m = wilder(tr), wilder(pdm), wilder(mdm)
    pdi, mdi = 100 * s_p / s_tr, 100 * s_m / s_tr
    dx = 100 * np.abs(pdi - mdi) / (pdi + mdi)
    adx = np.full(N, np.nan)
    adx[2 * n - 1] = np.nanmean(dx[n:2 * n])
    for i in range(2 * n, N):
        adx[i] = (adx[i - 1] * (n - 1) + dx[i]) / n
    return pdi, mdi, adx


def test_adx_matches_wilder_reference():
    df = synthetic_ohlcv(150, seed=5)
    a = ind.adx(df, 14)
    pdi, mdi, adx = _adx_reference(df)
    np.testing.assert_allclose(a["plus_di"].values, pdi, equal_nan=True, rtol=1e-9)
    np.testing.assert_allclose(a["minus_di"].values, mdi, equal_nan=True, rtol=1e-9)
    np.testing.assert_allclose(a["adx"].values, adx, equal_nan=True, rtol=1e-9)


def test_stochastic_and_williams_example():
    df = pd.DataFrame({"high": [110.0] * 14, "low": [90.0] * 14, "close": [100.0] * 13 + [105.0], "open": [100.0] * 14,
                       "volume": [1.0] * 14})
    assert ind.stochastic(df)["stoch_k"].iloc[-1] == pytest.approx(75)
    assert ind.williams_r(df).iloc[-1] == pytest.approx(-25)


def test_obv_and_relative_volume():
    df = pd.DataFrame({"close": [10, 11, 10.5, 10.5, 12], "volume": [100, 200, 150, 120, 300],
                       "high": [10, 11, 11, 11, 12], "low": [9, 10, 10, 10, 11], "open": [10, 10, 11, 10.5, 11]}, dtype=float)
    assert ind.obv(df).tolist() == [0, 200, 50, 50, 350]
    rv = ind.relative_volume(df, 2)
    assert rv.iloc[-1] == pytest.approx(300 / ((150 + 120) / 2))


def test_pivots_example():
    p = ind.pivot_points(110, 100, 106)
    assert p["P"] == pytest.approx(105.3333, abs=1e-3)
    assert p["R1"] == pytest.approx(110.6667, abs=1e-3)
    assert p["S1"] == pytest.approx(100.6667, abs=1e-3)


def test_supertrend_and_psar_follow_trend():
    n = 200
    up = pd.DataFrame({"close": np.linspace(100, 200, n)})
    up["open"], up["high"], up["low"], up["volume"] = up["close"] - 0.2, up["close"] + 1, up["close"] - 1, 1e5
    assert ind.supertrend(up)["supertrend_dir"].iloc[-1] == 1
    assert ind.parabolic_sar(up).iloc[-1] < up["close"].iloc[-1]


def test_indicators_are_causal_no_lookahead():
    """Values on day t must not change when future bars are added (except display-only chikou)."""
    df = synthetic_ohlcv(400, seed=9)
    bench = synthetic_ohlcv(400, seed=99)["close"]
    full = ind.compute_all(df, bench).drop(columns=["ichi_chikou"])
    part = ind.compute_all(df.iloc[:300], bench.iloc[:300]).drop(columns=["ichi_chikou"])
    pd.testing.assert_frame_equal(full.iloc[:300].astype(float), part.astype(float), check_exact=False, rtol=1e-9)


def test_support_resistance_and_fibonacci_shapes():
    df = synthetic_ohlcv(300, seed=4)
    sr = ind.support_resistance(df)
    price = df["close"].iloc[-1]
    assert all(z["level"] < price for z in sr["support"])
    assert all(z["level"] > price for z in sr["resistance"])
    fib = ind.fibonacci(df)
    assert fib["swing_low"] <= min(fib["retracement"].values()) <= max(fib["retracement"].values()) <= fib["swing_high"]


def test_candlestick_engulfing_detection():
    base = [100 - i for i in range(12)]  # downtrend
    o = base[:-1] + [87.0]
    c = [b - 0.5 for b in base[:-2]] + [88.0 - 0.8, 90.0]
    df = pd.DataFrame({"open": o, "close": c})
    df["high"] = df[["open", "close"]].max(axis=1) + 0.2
    df["low"] = df[["open", "close"]].min(axis=1) - 0.2
    df["volume"] = 1e5
    pats = ind.candlestick_patterns(df)
    assert bool(pats["bullish_engulfing"].iloc[-1])
