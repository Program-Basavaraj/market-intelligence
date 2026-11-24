"""Deterministic synthetic market data — used ONLY in tests, never published."""
from __future__ import annotations

from datetime import date, datetime, timezone

import numpy as np
import pandas as pd

from pipeline.providers.base import MarketDataProvider, validate_ohlcv


def synthetic_ohlcv(n: int = 900, seed: int = 0, ar: float = 0.0, start: str = "2022-01-03",
                    drift: float = 0.0003, vol: float = 0.018, price: float = 500.0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    eps = rng.normal(0, vol, n)
    r = np.zeros(n)
    for i in range(n):
        r[i] = drift + (ar * r[i - 1] if i else 0) + eps[i]
    close = price * np.exp(np.cumsum(r))
    open_ = close * np.exp(rng.normal(0, vol / 4, n))
    high = np.maximum(open_, close) * np.exp(np.abs(rng.normal(0, vol / 2, n)))
    low = np.minimum(open_, close) * np.exp(-np.abs(rng.normal(0, vol / 2, n)))
    volume = rng.integers(200_000, 2_000_000, n).astype(float)
    idx = pd.bdate_range(start, periods=n)
    return pd.DataFrame({"open": open_, "high": high, "low": low, "close": close, "adj_close": close,
                         "volume": volume}, index=idx)


class FakeProvider(MarketDataProvider):
    name = "Synthetic test provider"
    data_type = "historical"

    def __init__(self, tickers: list[str], n: int = 900, ar: float = 0.0, end: str | None = None):
        self.failures = {}
        self.data = {}
        for i, t in enumerate(tickers):
            df = synthetic_ohlcv(n, seed=i, ar=ar)
            if end:
                df.index = pd.bdate_range(end=end, periods=n)
            self.data[t] = df

    def history(self, tickers, start, end=None):
        out = {}
        for t in tickers:
            if t in self.data:
                df, _ = validate_ohlcv(self.data[t][self.data[t].index >= pd.Timestamp(start)])
                df.attrs = {"provider": self.name, "fetched_at": datetime.now(timezone.utc).isoformat(),
                            "data_type": self.data_type, "issues": []}
                out[t] = df
            else:
                self.failures[t] = "unknown ticker"
        return out

    def fundamentals(self, ticker):
        return {"provider": self.name, "fetched_at": datetime.now(timezone.utc).isoformat(), "info": {
                    "marketCap": 5e11, "sharesOutstanding": 1e9, "bookValue": 120.0, "trailingEps": 25.0,
                    "dividendYield": 0.012, "earningsGrowth": 0.15},
                "income": {"2025-03-31": {"Total Revenue": 4e11, "EBITDA": 8e10, "EBIT": 6e10, "Net Income": 3.5e10,
                                          "Interest Expense": 5e9, "Diluted EPS": 25.0, "Gross Profit": 1.5e11,
                                          "Operating Income": 6e10},
                           "2024-03-31": {"Total Revenue": 3.5e11, "EBITDA": 7.2e10, "EBIT": 5.4e10, "Net Income": 3e10,
                                          "Interest Expense": 5e9, "Diluted EPS": 21.0}},
                "balance": {"2025-03-31": {"Total Assets": 6e11, "Current Assets": 2.5e11, "Current Liabilities": 1.5e11,
                                           "Inventory": 5e10, "Accounts Receivable": 6e10, "Total Debt": 1e11,
                                           "Stockholders Equity": 2.8e11, "Cash And Cash Equivalents": 3e10},
                            "2024-03-31": {"Total Assets": 5.5e11, "Current Assets": 2.2e11, "Current Liabilities": 1.4e11,
                                           "Inventory": 4.6e10, "Accounts Receivable": 5.4e10, "Total Debt": 1.05e11,
                                           "Stockholders Equity": 2.5e11}},
                "cashflow": {"2025-03-31": {"Operating Cash Flow": 4e10, "Capital Expenditure": -1.5e10,
                                            "Investing Cash Flow": -2e10, "Financing Cash Flow": -1e10},
                             "2024-03-31": {"Operating Cash Flow": 3.4e10, "Capital Expenditure": -1.2e10}}}


def fake_master(n: int = 12) -> pd.DataFrame:
    rows = []
    sectors = ["Capital Goods", "Information Technology", "Financial Services", "Healthcare"]
    for i in range(n):
        sym = f"TEST{i:02d}"
        rows.append({"symbol": sym, "name": f"Testcompany {chr(65 + i)} Industries Ltd", "isin": f"INE00000{i:04d}",
                     "bse_code": str(500000 + i), "series": "EQ", "sector": sectors[i % 4], "industry": sectors[i % 4],
                     "listing_date": "", "listing_status": "Listed", "instrument_type": "Equity",
                     "exchanges": "NSE,BSE", "cap_category": ["Large", "Mid", "Small"][i % 3],
                     "cap_source": "test", "indices": "nifty500", "yahoo_nse": f"{sym}.NS", "yahoo_bse": ""})
    return pd.DataFrame(rows)
