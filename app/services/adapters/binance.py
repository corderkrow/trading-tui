"""Binance adapter implementation."""

import json

import httpx

from app.models.candle import CandleOHLCV
from app.models.ticker import Ticker
from app.services.adapters.base import MarketDataAdapter


class BinanceAdapter(MarketDataAdapter):
    name = "binance"

    def __init__(self, base_url: str = "https://api.binance.com"):
        self.base_url = base_url
        self._client = httpx.AsyncClient(
            base_url=base_url,
            timeout=10,
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def fetch_candles(self, symbol: str, interval: str, limit: int) -> list[CandleOHLCV]:
        resp = await self._client.get(
            "/api/v3/klines",
            params={"symbol": symbol, "interval": interval, "limit": limit},
        )
        resp.raise_for_status()
        raw = resp.json()
        return [
            CandleOHLCV(timestamp=c[0], open=float(c[1]), high=float(c[2]),
                        low=float(c[3]), close=float(c[4]), volume=float(c[5]))
            for c in raw
        ]

    async def fetch_tickers(self, symbols: list[str]) -> list[Ticker]:
        resp = await self._client.get(
            "/api/v3/ticker/price",
            params={"symbols": json.dumps(symbols)},
        )
        resp.raise_for_status()
        raw = resp.json()
        return [Ticker(symbol=r["symbol"], price=float(r["price"])) for r in raw]