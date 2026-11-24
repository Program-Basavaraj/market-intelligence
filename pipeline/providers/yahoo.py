"""Yahoo Finance adapter (via the open-source `yfinance` library).

Important, shown on the website as well:
  * Unofficial, research-use data source. Not exchange-licensed, not real-time.
  * Prices are end-of-day / delayed. Never presented as live.
  * Respect Yahoo's terms: personal, non-commercial research use; modest request rates.
"""
from __future__ import annotations

import logging
import time
from datetime import date, datetime, timedelta, timezone

import pandas as pd

from .base import MarketDataProvider, validate_ohlcv

log = logging.getLogger(__name__)


class YahooProvider(MarketDataProvider):
    name = "Yahoo Finance (yfinance)"
    data_type = "historical"

    def __init__(self, batch_size: int = 80, pause: float = 2.0):
        import yfinance  # noqa: F401  (fail early with a clear message if missing)
        self.batch_size = batch_size
        self.pause = pause
        self.failures: dict[str, str] = {}

    def history(self, tickers, start, end=None):
        import yfinance as yf
        out: dict[str, pd.DataFrame] = {}
        end = end or (date.today() + timedelta(days=1))
        for i in range(0, len(tickers), self.batch_size):
            batch = tickers[i:i + self.batch_size]
            raw = None
            for attempt in range(3):
                try:
                    raw = yf.download(batch, start=start.isoformat(), end=end.isoformat(), interval="1d",
                                      group_by="ticker", auto_adjust=False, actions=False,
                                      threads=True, progress=False)
                    break
                except Exception as exc:  # noqa: BLE001
                    log.warning("yfinance batch failed (attempt %s): %s", attempt + 1, exc)
                    time.sleep(self.pause * (attempt + 2))
            if raw is None or raw.empty:
                for t in batch:
                    self.failures[t] = "download failed"
                continue
            fetched = datetime.now(timezone.utc).isoformat()
            for t in batch:
                try:
                    df = raw[t] if isinstance(raw.columns, pd.MultiIndex) else raw
                except KeyError:
                    self.failures[t] = "not returned"
                    continue
                df = df.rename(columns={"Open": "open", "High": "high", "Low": "low", "Close": "close",
                                        "Adj Close": "adj_close", "Volume": "volume"})
                if "close" not in df or df["close"].dropna().empty:
                    self.failures[t] = "no rows"
                    continue
                df.index = pd.to_datetime(df.index).tz_localize(None).normalize()
                df, issues = validate_ohlcv(df)
                df.attrs = {"provider": self.name, "fetched_at": fetched, "data_type": self.data_type,
                            "issues": issues}
                out[t] = df
            time.sleep(self.pause)
        return out

    def fundamentals(self, ticker: str) -> dict:
        """Raw statements + info. Field availability for Indian companies varies; gaps are kept as None."""
        import yfinance as yf
        tk = yf.Ticker(ticker)
        result: dict = {"provider": self.name, "fetched_at": datetime.now(timezone.utc).isoformat(),
                        "data_status": "reported (as published by Yahoo Finance; audit status not indicated)"}
        try:
            result["info"] = {k: v for k, v in (tk.info or {}).items()
                              if isinstance(v, (int, float, str, bool)) or v is None}
        except Exception as exc:  # noqa: BLE001
            result["info"] = {}
            result["info_error"] = str(exc)
        for attr, key in (("income_stmt", "income"), ("balance_sheet", "balance"), ("cashflow", "cashflow"),
                          ("quarterly_income_stmt", "q_income")):
            try:
                df = getattr(tk, attr)
                result[key] = _statement_to_dict(df)
            except Exception as exc:  # noqa: BLE001
                result[key] = {}
                result[f"{key}_error"] = str(exc)
        return result


def _statement_to_dict(df: pd.DataFrame | None) -> dict:
    """{period_iso: {line_item: value}} with most recent period first."""
    if df is None or df.empty:
        return {}
    df = df.copy()
    df.columns = [pd.Timestamp(c).date().isoformat() for c in df.columns]
    out = {}
    for col in sorted(df.columns, reverse=True):
        series = df[col]
        out[col] = {str(k): (None if pd.isna(v) else float(v)) for k, v in series.items()}
    return out
