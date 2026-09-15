"""Yahoo Finance adapter implementation — no API key required."""

import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime

import httpx

from app.models.candle import CandleOHLCV
from app.models.ticker import NewsHit, SearchHit, Ticker
from app.services.adapters.base import MarketDataAdapter

# Yahoo interval mapping
_INTERVAL_MAP: dict[str, str] = {
    "1m": "1m",
    "5m": "5m",
    "15m": "15m",
    "30m": "30m",
    "1h": "1h",
    "1d": "1d",
    "1w": "1wk",
    "1M": "1mo",
}

SCREENER_IDS: dict[str, str] = {
    "most_actives": "most_actives",
    "gainers": "day_gainers",
    "losers": "day_losers",
}

SCREENER_FIELDS: dict[str, str] = {
    "marketcap": "intradaymarketcap",
    "percentchange": "percentchange",
    "price": "regularMarketPrice",
}


class ScreenerAuthError(Exception):
    """Crumb could not be obtained from Yahoo."""


class YahooAdapter(MarketDataAdapter):
    name = "yahoo"

    def __init__(self, base_url: str = "https://query1.finance.yahoo.com"):
        self.base_url = base_url
        self._client = httpx.AsyncClient(
            base_url=base_url,
            timeout=15,
            headers={"User-Agent": "Mozilla/5.0"},
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
        )
        self._crumb: str | None = None
        self._cookie: str | None = None

    async def close(self) -> None:
        await self._client.aclose()

    async def fetch_candles(self, symbol: str, interval: str, limit: int) -> list[CandleOHLCV]:
        yahoo_interval = _INTERVAL_MAP.get(interval, interval)
        resp = await self._client.get(
            f"/v8/finance/chart/{symbol}",
            params={
                "interval": yahoo_interval,
                "range": self._range_for_limit(yahoo_interval, limit),
            },
        )
        resp.raise_for_status()
        data = resp.json()["chart"]["result"][0]
        timestamps = data["timestamp"]
        ohlcv = data["indicators"]["quote"][0]
        return [
            CandleOHLCV(
                timestamp=int(ts) * 1000,
                open=float(o or 0),
                high=float(h or 0),
                low=float(l or 0),
                close=float(c or 0),
                volume=float(v or 0),
            )
            for ts, o, h, l, c, v in zip(
                timestamps,
                ohlcv["open"],
                ohlcv["high"],
                ohlcv["low"],
                ohlcv["close"],
                ohlcv["volume"],
            )
        ]

    @staticmethod
    def _to_ticker(q: dict) -> Ticker:
        """Map a Yahoo quote dict to a Ticker (extra fields optional)."""
        return Ticker(
            symbol=q["symbol"],
            price=float(q.get("regularMarketPrice") or 0),
            change_24h=q.get("regularMarketChangePercent"),
            name=q.get("shortName") or q.get("displayName"),
            volume=q.get("regularMarketVolume"),
            market_cap=q.get("marketCap") or q.get("intradaymarketcap"),
        )

    async def fetch_tickers(self, symbols: list[str]) -> list[Ticker]:
        results: list[Ticker] = []
        for symbol in symbols:
            resp = await self._client.get(
                f"/v8/finance/chart/{symbol}",
                params={"interval": "1d", "range": "1d"},
            )
            resp.raise_for_status()
            meta = resp.json()["chart"]["result"][0]["meta"]
            results.append(
                Ticker(
                    symbol=meta["symbol"],
                    price=float(meta["regularMarketPrice"]),
                    change_24h=meta.get("regularMarketChangePercent"),
                )
            )
        return results

    async def fetch_screeners(self, scr_id: str, count: int = 5) -> list[Ticker]:
        """Predefined Yahoo screeners: most_actives, day_gainers, day_losers."""
        resp = await self._client.get(
            "/v1/finance/screener/predefined/saved",
            params={"count": count, "scrIds": SCREENER_IDS[scr_id]},
        )
        resp.raise_for_status()
        quotes = resp.json()["finance"]["result"][0]["quotes"]
        return [self._to_ticker(q) for q in quotes]

    # quote-asset suffixes users type without a dash: "btcusd", "bnbusdt"
    _QUOTE_SUFFIXES = ("usdt", "usdc", "busd", "fdusd", "tusd", "usd")

    @classmethod
    def _crypto_query_variants(cls, query: str) -> list[str]:
        """Alternative queries for concatenated crypto pairs like "btcusd"."""
        q = query.strip().lower()
        variants: list[str] = []
        for suffix in cls._QUOTE_SUFFIXES:
            if q.endswith(suffix) and len(q) > len(suffix):
                base = q[: -len(suffix)]
                variants.append(f"{base}-{suffix}")
                variants.append(base)
                break
        return variants

    async def search_symbols(self, query: str, limit: int = 10) -> list[SearchHit]:
        """Free-text symbol lookup over the full Yahoo universe."""
        hits = await self._search_symbols_raw(query, limit)
        if hits:
            return hits
        # Yahoo search doesn't match concatenated pairs ("btcusd"); retry dashed/base form
        for variant in self._crypto_query_variants(query):
            hits = await self._search_symbols_raw(variant, limit)
            if hits:
                return hits
        return hits

    async def _search_symbols_raw(self, query: str, limit: int = 10) -> list[SearchHit]:
        resp = await self._client.get(
            "/v1/finance/search",
            params={"q": query, "quotesCount": limit, "newsCount": 0, "listsCount": 0},
        )
        resp.raise_for_status()
        hits = []
        for q in resp.json().get("quotes", []):
            if not q.get("symbol") or q.get("quoteType") in ("OPTION", "FUTURE"):
                continue
            name = q.get("shortname") or q.get("longname") or q.get("shortName") or q.get("longName")
            hits.append(
                SearchHit(
                    symbol=q["symbol"],
                    name=name,
                    exchange=q.get("exchDisp") or q.get("exchange"),
                    quote_type=q.get("quoteType"),
                )
            )
        return hits

    async def fetch_news(self, symbol: str, limit: int = 10) -> list[NewsHit]:
        """Latest news for the symbol (Yahoo per-symbol RSS headline feed)."""
        resp = await self._client.get(
            "https://feeds.finance.yahoo.com/rss/2.0/headline",
            params={"s": symbol, "region": "US", "lang": "en-US"},
        )
        resp.raise_for_status()
        channel = ET.fromstring(resp.text).find("channel")
        if channel is None:
            return []
        hits: list[NewsHit] = []
        for item in channel.findall("item"):
            title = item.findtext("title")
            if not title:
                continue
            hits.append(
                NewsHit(
                    title=title,
                    link=item.findtext("link"),
                    publisher=item.findtext("source"),
                    published_at=self._parse_pubdate(item.findtext("pubDate")),
                )
            )
            if len(hits) >= limit:
                break
        return hits

    @staticmethod
    def _parse_pubdate(value: str | None) -> int | None:
        if not value:
            return None
        try:
            return int(parsedate_to_datetime(value).timestamp())
        except (TypeError, ValueError):
            return None

    async def _get_crumb(self) -> tuple[str, str]:
        """Cookie A3 + crumb pair required by the custom screener endpoint."""
        if self._crumb and self._cookie:
            return self._crumb, self._cookie
        cookies = httpx.Cookies()
        resp = await self._client.get("https://fc.yahoo.com")
        # fc.yahoo.com can return 404 while still setting the A3 cookie
        for cookie in resp.cookies.jar:
            if cookie.name == "A3":
                cookies.set("A3", cookie.value, domain=".yahoo.com")
        if not cookies.get("A3"):
            raise ScreenerAuthError("Yahoo did not issue an A3 cookie")
        crumb = await self._client.get("/v1/test/getcrumb", cookies=cookies)
        crumb.raise_for_status()
        crumb_text = crumb.text.strip()
        if not crumb_text:
            raise ScreenerAuthError("Yahoo returned an empty crumb")
        self._crumb = crumb_text
        self._cookie = cookies.get("A3")
        return self._crumb, self._cookie

    async def fetch_screener_search(
        self,
        filters: dict,
        size: int = 50,
        offset: int = 0,
        sort_field: str = "marketcap",
        sort_type: str = "desc",
    ) -> dict:
        """Custom Bloomberg-style screener over the full Yahoo universe."""
        operand = lambda field, value: {"operator": "eq", "operands": [field, value]}
        ops = [operand("region", filters.get("region", "us"))]
        if filters.get("sector"):
            # Yahoo expects title case: "technology" -> "Technology", "financial_services" -> "Financial Services"
            ops.append(operand("sector", filters["sector"].replace("_", " ").title()))
        if filters.get("mincap") is not None:
            ops.append(
                {"operator": "gt", "operands": ["intradaymarketcap", filters["mincap"]]}
            )
        if filters.get("maxcap") is not None:
            ops.append(
                {"operator": "lt", "operands": ["intradaymarketcap", filters["maxcap"]]}
            )
        body = {
            "size": size,
            "offset": offset,
            "sortField": SCREENER_FIELDS.get(sort_field, "intradaymarketcap"),
            "sortType": sort_type.upper(),
            "quoteType": "EQUITY",
            "query": {"operator": "and", "operands": ops},
            "userId": "",
            "userIdType": "guid",
        }
        crumb, cookie = await self._get_crumb()
        resp = await self._client.post(
            "/v1/finance/screener",
            params={"crumb": crumb},
            cookies=httpx.Cookies({"A3": cookie}),
            json=body,
        )
        if resp.status_code == 401:
            # stale crumb — refresh once and retry
            self._crumb = None
            self._cookie = None
            crumb, cookie = await self._get_crumb()
            resp = await self._client.post(
                "/v1/finance/screener",
                params={"crumb": crumb},
                cookies=httpx.Cookies({"A3": cookie}),
                json=body,
            )
        resp.raise_for_status()
        result = resp.json()["finance"]["result"][0]
        return {
            "total": result.get("total", 0),
            "quotes": [self._to_ticker(q) for q in result.get("quotes", [])],
        }

    @staticmethod
    def _range_for_limit(interval: str, limit: int) -> str:
        unit = interval[-1]
        val = int(interval[:-1])
        total_minutes = val * limit
        if total_minutes <= 60:
            return f"{total_minutes}m"
        if total_minutes <= 1440:
            return f"{total_minutes // 60}d"
        days = total_minutes // 1440
        if days <= 365:
            return f"{days}d"
        return f"{days // 365}y"
