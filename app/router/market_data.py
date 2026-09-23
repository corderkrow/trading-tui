"""Market data REST endpoints."""

from fastapi import APIRouter, Depends, Query, Request
from app.models.candle import CandleOHLCV
from app.models.ticker import NewsHit, ScreenerResult, SearchHit, Ticker
from app.services.adapters.base import MarketDataAdapter
from app.services.market_data import (
    fetch_candles_async,
    fetch_news,
    fetch_screener_search,
    fetch_screeners,
    fetch_search_symbols,
    fetch_ticker,
)

SCREENER_IDS = {"most_actives", "gainers", "losers"}
SCREENER_SORTS = {"marketcap", "percentchange", "price"}

router = APIRouter(prefix="/market", tags=["market"])


def get_market_adapter(request: Request) -> MarketDataAdapter:
    """Return the process-wide adapter created in `create_app`."""
    return request.app.state.market_adapter


@router.get("/candles", response_model=list[CandleOHLCV])
async def get_candles(
    symbol: str = Query(..., description="Trading pair, e.g. BTCUSDT"),
    interval: str = Query("1h", description="Kline interval"),
    limit: int = Query(500, ge=1, le=1000, description="Number of candles"),
    adapter: MarketDataAdapter = Depends(get_market_adapter),
):
    return await fetch_candles_async(adapter=adapter, symbol=symbol, interval=interval, limit=limit)


@router.get("/quotes", response_model=list[Ticker])
async def get_quotes(
    symbols: str = Query(..., description="Comma-separated symbols, e.g. BTCUSDT,ETHUSDT"),
    adapter: MarketDataAdapter = Depends(get_market_adapter),
):
    symbol_list = [s.strip().upper() for s in symbols.split(",") if s.strip()]
    if not symbol_list:
        from app.core.exceptions import MarketError
        raise MarketError(message="No valid symbols provided", code=400)
    return await fetch_ticker(adapter=adapter, symbol_list=symbol_list)


@router.get("/search", response_model=list[SearchHit])
async def search_symbols(
    q: str = Query(..., min_length=1, description="Free-text symbol query, e.g. apple, BTC"),
    limit: int = Query(10, ge=1, le=25, description="Max results"),
    adapter: MarketDataAdapter = Depends(get_market_adapter),
):
    try:
        return await fetch_search_symbols(adapter=adapter, query=q, limit=limit)
    except NotImplementedError as exc:
        from app.core.exceptions import MarketError
        raise MarketError(message=str(exc), code=400) from exc


@router.get("/news", response_model=list[NewsHit])
async def get_news(
    symbol: str = Query(..., description="Symbol, e.g. BTC-USD, AAPL"),
    limit: int = Query(10, ge=1, le=25, description="Max items"),
    adapter: MarketDataAdapter = Depends(get_market_adapter),
):
    try:
        return await fetch_news(adapter=adapter, symbol=symbol, limit=limit)
    except NotImplementedError as exc:
        from app.core.exceptions import MarketError
        raise MarketError(message=str(exc), code=400) from exc


@router.get("/screeners", response_model=list[Ticker])
async def get_screeners(
    scr_id: str = Query("most_actives", description="most_actives | gainers | losers"),
    count: int = Query(250, ge=1, le=250, description="Number of quotes"),
    adapter: MarketDataAdapter = Depends(get_market_adapter),
):
    if scr_id not in SCREENER_IDS:
        from app.core.exceptions import MarketError
        raise MarketError(message=f"Unknown screener '{scr_id}'", code=400)
    try:
        return await fetch_screeners(adapter=adapter, scr_id=scr_id, count=count)
    except NotImplementedError as exc:
        from app.core.exceptions import MarketError
        raise MarketError(message=str(exc), code=400) from exc


@router.get("/screener", response_model=ScreenerResult)
async def search_screener(
    region: str = Query("us", description="Market region, e.g. us, br, de"),
    sector: str | None = Query(None, description="Sector, e.g. technology, financial_services"),
    mincap: float | None = Query(None, ge=1, description="Minimum market cap in USD"),
    maxcap: float | None = Query(None, ge=1, description="Maximum market cap in USD"),
    sort: str = Query("marketcap", description="marketcap | percentchange | price"),
    size: int = Query(50, ge=1, le=250, description="Quotes per page"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    adapter: MarketDataAdapter = Depends(get_market_adapter),
):
    if sort not in SCREENER_SORTS:
        from app.core.exceptions import MarketError
        raise MarketError(message=f"Unknown sort '{sort}'", code=400)
    filters = {
        "region": region,
        "sector": sector,
        "mincap": mincap,
        "maxcap": maxcap,
    }
    try:
        result = await fetch_screener_search(
            adapter=adapter,
            filters=filters,
            size=size,
            offset=offset,
            sort_field=sort,
            sort_type="desc",
        )
    except NotImplementedError as exc:
        from app.core.exceptions import MarketError
        raise MarketError(message=str(exc), code=400) from exc
    return ScreenerResult(total=result["total"], quotes=result["quotes"])