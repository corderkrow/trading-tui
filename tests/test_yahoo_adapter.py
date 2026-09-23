"""YahooAdapter batch quotes + process-wide adapter wiring."""

from types import SimpleNamespace

import httpx

from app.main import create_app
from app.router.market_data import get_market_adapter
from app.services.adapters.yahoo import YahooAdapter

BASE = "https://query1.finance.yahoo.com"


def _quote(symbol: str, price: float) -> dict:
    return {
        "symbol": symbol,
        "regularMarketPrice": price,
        "regularMarketChangePercent": 1.5,
        "shortName": symbol,
    }


def _mock_client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url=BASE)


async def test_fetch_tickers_uses_one_batch_request():
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        calls.append(url)
        if "fc.yahoo.com" in url:
            return httpx.Response(
                200, headers={"set-cookie": "A3=token; Domain=.yahoo.com; Path=/"}
            )
        if "getcrumb" in url:
            return httpx.Response(200, text="crumb-123")
        assert "v7/finance/quote" in url, url
        assert request.url.params["symbols"] == "AAPL,MSFT,NVDA"
        assert request.url.params["crumb"] == "crumb-123"
        return httpx.Response(
            200,
            json={
                "quoteResponse": {
                    "result": [
                        _quote("AAPL", 100.0),
                        _quote("MSFT", 200.0),
                        _quote("NVDA", 300.0),
                    ]
                }
            },
        )

    adapter = YahooAdapter()
    adapter._client = _mock_client(handler)
    try:
        tickers = await adapter.fetch_tickers(["AAPL", "MSFT", "NVDA"])
    finally:
        await adapter.close()

    assert [t.symbol for t in tickers] == ["AAPL", "MSFT", "NVDA"]
    assert [t.price for t in tickers] == [100.0, 200.0, 300.0]
    quote_calls = [c for c in calls if "v7/finance/quote" in c]
    assert len(quote_calls) == 1, f"expected one batch call, got {len(quote_calls)}"


async def test_fetch_tickers_skips_quotes_without_price():
    def handler(request: httpx.Request) -> httpx.Response:
        if "fc.yahoo.com" in request.url.host:
            return httpx.Response(
                200, headers={"set-cookie": "A3=token; Domain=.yahoo.com; Path=/"}
            )
        if "getcrumb" in str(request.url):
            return httpx.Response(200, text="crumb-123")
        return httpx.Response(
            200,
            json={
                "quoteResponse": {
                    "result": [{"symbol": "HALTED"}, _quote("AAPL", 10.0)]
                }
            },
        )

    adapter = YahooAdapter()
    adapter._client = _mock_client(handler)
    try:
        tickers = await adapter.fetch_tickers(["HALTED", "AAPL"])
    finally:
        await adapter.close()

    assert [t.symbol for t in tickers] == ["AAPL"]


def test_get_market_adapter_returns_app_adapter():
    app = create_app()
    request = SimpleNamespace(app=app)
    assert get_market_adapter(request) is app.state.market_adapter


async def test_lifespan_closes_shared_adapter():
    class FakeAdapter:
        name = "fake"

        def __init__(self) -> None:
            self.closed = False

        async def close(self) -> None:
            self.closed = True

    adapter = FakeAdapter()
    app = create_app(adapter=adapter)
    async with app.router.lifespan_context(app):
        assert adapter.closed is False
    assert adapter.closed is True
