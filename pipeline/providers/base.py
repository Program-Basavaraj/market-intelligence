"""Provider-independent market data interface.

Any data source (Yahoo Finance, a broker API, a licensed vendor) implements
MarketDataProvider. The rest of the pipeline only talks to this interface,
so a provider can be replaced without touching the analytics.

Every OHLCV frame returned MUST have:
  index   : DatetimeIndex (exchange-local trading dates, tz-naive, ascending)
  columns : open, high, low, close, adj_close, volume
  attrs   : {"provider": str, "fetched_at": iso-utc, "data_type": "historical"|"delayed"|"realtime"}
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date

import pandas as pd

OHLCV_COLUMNS = ["open", "high", "low", "close", "adj_close", "volume"]


class MarketDataProvider(ABC):
    name: str = "base"
    data_type: str = "historical"   # honest label shown on the website

    @abstractmethod
    def history(self, tickers: list[str], start: date, end: date | None = None) -> dict[str, pd.DataFrame]:
        """Daily OHLCV per ticker. Missing tickers are simply absent from the result."""

    def intraday(self, ticker: str, interval: str = "5m") -> pd.DataFrame:
        raise NotImplementedError(
            f"{self.name} does not provide authorised intraday data. Configure a broker API adapter.")

    def fundamentals(self, ticker: str) -> dict:
        raise NotImplementedError(f"{self.name} does not provide fundamentals.")


def validate_ohlcv(df: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    """Drop impossible rows and report data-quality issues (never 'repairs' prices)."""
    issues: list[str] = []
    if df is None or df.empty:
        return pd.DataFrame(columns=OHLCV_COLUMNS), ["no data"]
    df = df.copy()
    df = df[~df.index.duplicated(keep="last")].sort_index()
    before = len(df)
    df = df.dropna(subset=["open", "high", "low", "close"])
    bad = (df["high"] < df[["open", "close", "low"]].max(axis=1) - 1e-9) | \
          (df["low"] > df[["open", "close", "high"]].min(axis=1) + 1e-9) | (df["close"] <= 0)
    if bad.any():
        issues.append(f"{int(bad.sum())} inconsistent OHLC rows removed")
        df = df[~bad]
    if len(df) < before and not bad.any():
        issues.append(f"{before - len(df)} rows with missing prices removed")
    df["volume"] = df["volume"].fillna(0)
    if "adj_close" not in df or df["adj_close"].isna().all():
        df["adj_close"] = df["close"]
        issues.append("adjusted close unavailable; using close")
    zero_vol = (df["volume"] == 0).tail(20).sum()
    if zero_vol >= 5:
        issues.append(f"{int(zero_vol)} of last 20 sessions had zero volume (illiquid or suspended)")
    return df[OHLCV_COLUMNS], issues
