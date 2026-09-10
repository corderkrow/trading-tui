"""REST API tests for /market/screeners endpoint."""

import httpx

from app.main import create_app
from app.models.ticker import Ticker
from app.router.market_data import get_market_adapter

BASE = "http://test"


class FakeScreenerAdapter:
    name = "fake"

    def __init__(self) -> None:
        self.last_search: dict | None = None

    async def fetch_screeners(self, scr_id: str, count: int) -> list[Ticker]:
        return [
            Ticker(symbol=f"{scr_id}-{i}", price=200.0, change_24h=0.5)
            for i in range(count)
        ]

    async def fetch_screener_search(
        self, filters: dict, size: int = 50, offset: int = 0, sort_field: str = "marketcap", sort_type: str = "desc"
    ) -> dict:
        self.last_search = {"filters": filters, "size": size, "offset": offset, "sort_field": sort_field}
        return {
            "total": 20047,
            "quotes": [
                Ticker(symbol=f"F{i}", price=float(i + 1), change_24h=0.1 * i)
                for i in range(size)
            ],
        }


class NoScreenerAdapter:
    """Adapter without screener support (like Binance)."""

    name = "binance"

    async def fetch_screeners(self, scr_id: str, count: int) -> list[Ticker]:
        raise NotImplementedError("Adapter binance does not support screeners")

    async def fetch_screener_search(
        self, filters: dict, size: int = 50, offset: int = 0, sort_field: str = "marketcap", sort_type: str = "desc"
    ) -> dict:
        raise NotImplementedError("Adapter binance does not support screeners")


def make_client(adapter):
    app = create_app()
    app.dependency_overrides[get_market_adapter] = lambda: adapter
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=BASE)


async def test_screeners_default_most_actives():
    async with make_client(FakeScreenerAdapter()) as client:
        resp = await client.get("/market/screeners")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body) == 250
        assert body[0]["symbol"] == "most_actives-0"
        assert body[0]["price"] == 200.0
        assert body[0]["change_24h"] == 0.5


async def test_screeners_explicit_mode_and_count():
    async with make_client(FakeScreenerAdapter()) as client:
        resp = await client.get("/market/screeners", params={"scr_id": "gainers", "count": 3})
        assert resp.status_code == 200
        assert [q["symbol"] for q in resp.json()] == ["gainers-0", "gainers-1", "gainers-2"]


async def test_screeners_unknown_scr_id_returns_400():
    async with make_client(FakeScreenerAdapter()) as client:
        resp = await client.get("/market/screeners", params={"scr_id": "banana"})
        assert resp.status_code == 400
        assert "banana" in resp.json()["detail"]


async def test_screeners_count_out_of_range_returns_422():
    async with make_client(FakeScreenerAdapter()) as client:
        resp = await client.get("/market/screeners", params={"count": 0})
        assert resp.status_code == 422
        resp = await client.get("/market/screeners", params={"count": 251})
        assert resp.status_code == 422


async def test_screeners_unsupported_adapter_returns_400():
    async with make_client(NoScreenerAdapter()) as client:
        resp = await client.get("/market/screeners")
        assert resp.status_code == 400
        assert "does not support screeners" in resp.json()["detail"]


async def test_screener_search_default():
    adapter = FakeScreenerAdapter()
    async with make_client(adapter) as client:
        resp = await client.get("/market/screener")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 20047
        assert len(body["quotes"]) == 50
        assert body["quotes"][0]["symbol"] == "F0"
        assert adapter.last_search["filters"]["region"] == "us"
        assert adapter.last_search["size"] == 50
        assert adapter.last_search["sort_field"] == "marketcap"


async def test_screener_search_with_filters():
    adapter = FakeScreenerAdapter()
    async with make_client(adapter) as client:
        resp = await client.get(
            "/market/screener",
            params={"sector": "technology", "mincap": 1000000000, "sort": "percentchange", "size": 10},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["quotes"]) == 10
        filters = adapter.last_search["filters"]
        assert filters["sector"] == "technology"
        assert filters["mincap"] == 1000000000
        assert adapter.last_search["sort_field"] == "percentchange"
        assert adapter.last_search["size"] == 10


async def test_screener_search_bad_sort_returns_400():
    async with make_client(FakeScreenerAdapter()) as client:
        resp = await client.get("/market/screener", params={"sort": "banana"})
        assert resp.status_code == 400
        assert "banana" in resp.json()["detail"]


async def test_screener_search_size_out_of_range_returns_422():
    async with make_client(FakeScreenerAdapter()) as client:
        resp = await client.get("/market/screener", params={"size": 251})
        assert resp.status_code == 422


async def test_screener_search_unsupported_adapter_returns_400():
    async with make_client(NoScreenerAdapter()) as client:
        resp = await client.get("/market/screener")
        assert resp.status_code == 400
        assert "does not support screeners" in resp.json()["detail"]