"""Yahoo adapter parsing, tested with a stand-in `yfinance` module (no network)."""
import sys
import types

import numpy as np
import pandas as pd


def _fake_yf(frames):
    mod = types.ModuleType("yfinance")

    def download(tickers, **kw):
        cols = pd.MultiIndex.from_tuples([(t, f) for t in tickers if t in frames for f in frames[t].columns])
        if not len(cols):
            return pd.DataFrame()
        return pd.concat([frames[t] for t in tickers if t in frames], axis=1, keys=[t for t in tickers if t in frames])

    class Ticker:
        def __init__(self, t):
            self.info = {"marketCap": 1e11, "longName": "X", "weird": {"nested": 1}}
            idx = ["Total Revenue", "Net Income"]
            self.income_stmt = pd.DataFrame({pd.Timestamp("2025-03-31"): [100.0, 10.0], pd.Timestamp("2024-03-31"): [90.0, np.nan]}, index=idx)
            self.balance_sheet = pd.DataFrame()
            self.cashflow = None
            self.quarterly_income_stmt = pd.DataFrame()

    mod.download, mod.Ticker = download, Ticker
    return mod


def test_yahoo_history_parsing(monkeypatch):
    idx = pd.date_range("2026-11-17", periods=5, freq="B", tz="Asia/Kolkata")
    good = pd.DataFrame({"Open": [10, 11, 12, 13, 14], "High": [11, 12, 13, 14, 15], "Low": [9, 10, 11, 12, 13],
                         "Close": [10.5, 11.5, 12.5, 13.5, 14.5], "Adj Close": [10.4, 11.4, 12.4, 13.4, 14.4],
                         "Volume": [100, 200, 300, 400, 500]}, index=idx, dtype=float)
    empty = good.copy() * np.nan
    monkeypatch.setitem(sys.modules, "yfinance", _fake_yf({"A.NS": good, "B.NS": empty}))
    from pipeline.providers.yahoo import YahooProvider
    p = YahooProvider(pause=0)
    out = p.history(["A.NS", "B.NS", "C.NS"], start=pd.Timestamp("2026-11-01").date())
    assert list(out) == ["A.NS"]
    df = out["A.NS"]
    assert list(df.columns) == ["open", "high", "low", "close", "adj_close", "volume"]
    assert df.index.tz is None and df.index[0] == pd.Timestamp("2026-11-17")
    assert df.attrs["provider"].startswith("Yahoo") and df.attrs["data_type"] == "historical"
    assert p.failures["B.NS"] == "no rows" and p.failures["C.NS"] == "not returned"


def test_yahoo_fundamentals_parsing(monkeypatch):
    monkeypatch.setitem(sys.modules, "yfinance", _fake_yf({}))
    from pipeline.providers.yahoo import YahooProvider
    f = YahooProvider(pause=0).fundamentals("A.NS")
    assert "weird" not in f["info"]                      # only scalar fields kept
    assert list(f["income"]) == ["2025-03-31", "2024-03-31"]  # latest first
    assert f["income"]["2024-03-31"]["Net Income"] is None    # NaN kept as missing, not invented
    assert f["balance"] == {} and f["cashflow"] == {}
