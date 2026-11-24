from .base import MarketDataProvider, OHLCV_COLUMNS, validate_ohlcv

__all__ = ["MarketDataProvider", "OHLCV_COLUMNS", "validate_ohlcv", "get_provider"]


def get_provider(name: str = "yahoo") -> MarketDataProvider:
    if name == "yahoo":
        from .yahoo import YahooProvider
        return YahooProvider()
    raise ValueError(f"Unknown provider '{name}'. Implement MarketDataProvider for a broker API.")
