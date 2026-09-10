"""Abstract base adapter for market data sources."""

from abc import ABC, abstractmethod

from app.models.candle import CandleOHLCV
from app.models.ticker import Ticker


class MarketDataAdapter(ABC):
    """Interface all exchange adapters must implement."""

    @abstractmethod
    async def fetch_candles(self, symbol: str, interval: str, limit: int) -> list[CandleOHLCV]: ...

    @abstractmethod
    async def fetch_tickers(self, symbols: list[str]) -> list[Ticker]: ...

    async def fetch_screeners(self, scr_id: str, count: int) -> list[Ticker]:
        raise NotImplementedError(f"Adapter {self.name} does not support screeners")

    @property
    @abstractmethod
    def name(self) -> str: ...