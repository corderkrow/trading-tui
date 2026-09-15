"""Fetch market data via adapter pattern."""

from app.models.candle import CandleOHLCV
from app.models.ticker import NewsHit, SearchHit, Ticker
from app.services.adapters.base import MarketDataAdapter


async def fetch_candles_async(
    adapter: MarketDataAdapter,
    symbol: str,
    interval: str = "1h",
    limit: int = 500,
) -> list[CandleOHLCV]:
    return await adapter.fetch_candles(symbol=symbol, interval=interval, limit=limit)


async def fetch_ticker(adapter: MarketDataAdapter, symbol_list: list[str]) -> list[Ticker]:
    return await adapter.fetch_tickers(symbol_list)


async def fetch_search_symbols(
    adapter: MarketDataAdapter, query: str, limit: int = 10
) -> list[SearchHit]:
    return await adapter.search_symbols(query=query, limit=limit)


async def fetch_screeners(adapter: MarketDataAdapter, scr_id: str, count: int) -> list[Ticker]:
    return await adapter.fetch_screeners(scr_id=scr_id, count=count)


async def fetch_news(adapter: MarketDataAdapter, symbol: str, limit: int = 10) -> list[NewsHit]:
    return await adapter.fetch_news(symbol=symbol, limit=limit)


async def fetch_screener_search(
    adapter: MarketDataAdapter,
    filters: dict,
    size: int,
    offset: int,
    sort_field: str,
    sort_type: str,
) -> dict:
    return await adapter.fetch_screener_search(
        filters=filters,
        size=size,
        offset=offset,
        sort_field=sort_field,
        sort_type=sort_type,
    )