"""Central configuration.

All secrets come from environment variables (never from source code).
Tunable research parameters live in config/settings.json so they can be
changed without touching code.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
IST = ZoneInfo("Asia/Kolkata")


def _load_settings() -> dict:
    path = Path(os.environ.get("MI_SETTINGS", ROOT / "config" / "settings.json"))
    if path.exists():
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    return {}


@dataclass
class Settings:
    # Where generated JSON for the website is written
    output_dir: Path = field(default_factory=lambda: Path(os.environ.get("MI_OUTPUT_DIR", ROOT / "site" / "data")))
    # Private working cache (prices, models, fundamentals) - not published
    cache_dir: Path = field(default_factory=lambda: Path(os.environ.get("MI_CACHE_DIR", ROOT / ".cache")))
    # Persistent state (alert de-duplication, news history) - published to data branch
    state_dir: Path = field(default_factory=lambda: Path(os.environ.get("MI_STATE_DIR", ROOT / "site" / "data" / "state")))

    universe: str = "nifty500"          # nifty50 | nifty100 | nifty200 | nifty500 | all_nse
    history_years: int = 5
    chart_days: int = 260               # bars published per stock page
    fundamentals_per_run: int = 80      # incremental refresh, oldest first
    fundamentals_max_age_days: int = 14
    min_median_traded_value_cr: float = 1.0   # liquidity filter (₹ crore / day)
    stale_after_days: int = 4           # calendar days before data is flagged stale
    risk_free_rate: float = 0.065       # annual, used in Sharpe/Sortino
    horizons: list = field(default_factory=lambda: [2, 5, 10])
    neutral_band_k: float = 0.5         # neutral band = k * sigma_daily * sqrt(h)
    min_neutral_band: float = 0.004     # never narrower than ~round-trip cost
    retrain_every_days: int = 7
    gate_min_brier_skill: float = 0.005  # model must beat base rates out-of-sample
    gate_min_samples: int = 2000
    costs: dict = field(default_factory=lambda: {
        "brokerage_pct": 0.03, "stt_pct": 0.10, "exchange_pct": 0.00297,
        "stamp_buy_pct": 0.015, "sebi_pct": 0.0001, "gst_pct": 18.0, "slippage_pct": 0.10,
    })
    usd_inr_fallback: float = 84.0       # only used to convert $ order values; marked as estimate
    alerts: dict = field(default_factory=lambda: {
        "min_probability": 0.60, "min_order_size_ratio_pct": 5.0,
        "volume_spike_x": 3.0, "max_per_run": 25,
    })
    news_feeds: list = field(default_factory=list)

    # Secrets (environment only)
    telegram_token: str | None = field(default_factory=lambda: os.environ.get("TELEGRAM_BOT_TOKEN") or None)
    telegram_chat_id: str | None = field(default_factory=lambda: os.environ.get("TELEGRAM_CHAT_ID") or None)

    @classmethod
    def load(cls) -> "Settings":
        s = cls()
        for key, value in _load_settings().items():
            if key.startswith("_"):
                continue
            if hasattr(s, key) and key not in ("telegram_token", "telegram_chat_id"):
                current = getattr(s, key)
                if isinstance(current, dict) and isinstance(value, dict):
                    current.update(value)
                elif isinstance(current, Path):
                    setattr(s, key, Path(value))
                else:
                    setattr(s, key, value)
        if os.environ.get("MI_UNIVERSE"):
            s.universe = os.environ["MI_UNIVERSE"]
        for d in (s.output_dir, s.cache_dir, s.state_dir):
            Path(d).mkdir(parents=True, exist_ok=True)
        return s
