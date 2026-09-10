"""HTTP client for the alerts REST API + UI-facing view model."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

import httpx


class ApiError(Exception):
    """Raised on non-2xx responses; carries the server detail message."""

    def __init__(self, message: str, status_code: int = 0):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


# code -> (symbol, thousands sep, decimal sep, decimals)
CURRENCIES: dict[str, tuple[str, str, str, int]] = {
    "usd": ("$", ",", ".", 2),
    "eur": ("€", ".", ",", 2),
    "gbp": ("£", ",", ".", 2),
    "jpy": ("¥", ",", ".", 0),
    "brl": ("R$ ", ".", ",", 2),
    "cad": ("C$", ",", ".", 2),
    "aud": ("A$", ",", ".", 2),
    "nzd": ("NZ$", ",", ".", 2),
    "sgd": ("S$", ",", ".", 2),
    "hkd": ("HK$", ",", ".", 2),
    "chf": ("CHF ", ",", ".", 2),
    "inr": ("₹", ",", ".", 2),
    "cny": ("CN¥", ",", ".", 2),
    "krw": ("₩", ",", ".", 0),
    "mxn": ("MX$", ",", ".", 2),
    "sek": ("kr ", " ", ",", 2),
}

_currency: str = "usd"


def set_currency(code: str) -> None:
    global _currency
    if code in CURRENCIES:
        _currency = code


def currency_symbol() -> str:
    return CURRENCIES.get(_currency, CURRENCIES["usd"])[0]


def format_price(value: float, code: str | None = None) -> str:
    symbol, thousands, decimal, decimals = CURRENCIES.get(code or _currency, CURRENCIES["usd"])
    body = f"{value:,.{decimals}f}"
    int_part, sep, frac = body.partition(".")
    body = int_part.replace(",", thousands)
    if sep:
        body += decimal + frac
    return f"{symbol}{body}"


@dataclass
class AlertView:
    """UI representation of an alert (separate from domain/DTO)."""

    id: str
    symbol: str
    status: str
    conditions: list[dict] = field(default_factory=list)
    message: str = ""
    expires_at: str | None = None

    @classmethod
    def from_json(cls, data: dict) -> "AlertView":
        return cls(
            id=data["id"],
            symbol=data["symbol"],
            status=data["status"],
            conditions=data.get("conditions", []),
            message=data.get("message", ""),
            expires_at=data.get("expires_at"),
        )

    def condition_text(self) -> str:
        if not self.conditions:
            return "—"
        return self.conditions[0].get("operator", "").title()

    def target_text(self) -> str:
        if not self.conditions:
            return "—"
        value = float(self.conditions[0].get("value", 0))
        return format_price(value)

    def expires_text(self) -> str:
        if not self.expires_at:
            return "—"
        return self.expires_at[:16].replace("T", " ")


@dataclass
class CandleView:
    """UI representation of the latest candle (OHLC)."""

    open: float
    high: float
    low: float
    close: float

    @classmethod
    def from_json(cls, data: dict) -> "CandleView":
        return cls(
            open=float(data["open"]),
            high=float(data["high"]),
            low=float(data["low"]),
            close=float(data["close"]),
        )

    def ohlc_text(self) -> str:
        sym = currency_symbol()
        o, h, l, c = (f"{sym}{QuoteView._compact(v)}" for v in (self.open, self.high, self.low, self.close))
        change = self.close - self.open
        pct = change / self.open * 100 if self.open else 0.0
        style = "green" if change >= 0 else "red"
        return f"O: {o} H: {h} L: {l} C: {c} [{style}]{sym}{change:+,.2f} ({pct:+.2f}%)[/]"


@dataclass
class ScreenerResultView:
    """UI representation of a custom screener page."""

    total: int
    quotes: list[QuoteView]

    @classmethod
    def from_json(cls, data: dict) -> "ScreenerResultView":
        return cls(
            total=data["total"],
            quotes=[QuoteView.from_json(q) for q in data.get("quotes", [])],
        )


@dataclass
class QuoteView:
    """UI representation of a market quote."""

    symbol: str
    price: float
    change_24h: float | None = None
    name: str | None = None
    volume: float | None = None
    market_cap: float | None = None

    @classmethod
    def from_json(cls, data: dict) -> "QuoteView":
        change = data.get("change_24h")
        volume = data.get("volume")
        market_cap = data.get("market_cap")
        return cls(
            symbol=data["symbol"],
            price=float(data["price"]),
            change_24h=float(change) if change is not None else None,
            name=data.get("name"),
            volume=float(volume) if volume is not None else None,
            market_cap=float(market_cap) if market_cap is not None else None,
        )

    def price_text(self) -> str:
        return format_price(self.price)

    def change_text(self) -> str:
        if self.change_24h is None:
            return "—"
        return f"{self.change_24h:+.2f}%"

    def volume_text(self) -> str:
        if self.volume is None:
            return "—"
        return self._compact(self.volume)

    def market_cap_text(self) -> str:
        if self.market_cap is None:
            return "—"
        return f"{currency_symbol()}{self._compact(self.market_cap)}"

    @staticmethod
    def _compact(value: float) -> str:
        """1_350_000 -> 1.35M, 5_562_502_742_016 -> 5.56T"""
        for unit, div in (("T", 1e12), ("B", 1e9), ("M", 1e6), ("K", 1e3)):
            if value >= div:
                return f"{value / div:.2f}{unit}"
        return f"{value:.0f}"


class AlertApiClient(Protocol):
    async def list_alerts(self) -> list[AlertView]: ...
    async def create_alert(self, payload: dict) -> AlertView: ...
    async def delete_alert(self, alert_id: str) -> None: ...
    async def enable_alert(self, alert_id: str) -> AlertView: ...
    async def disable_alert(self, alert_id: str) -> AlertView: ...
    async def get_last_candle(self, symbol: str) -> CandleView | None: ...


class HttpAlertApi:
    """Default client talking to the FastAPI backend."""

    def __init__(self, base_url: str = "http://127.0.0.1:8333") -> None:
        self.base_url = base_url
        self._client = httpx.AsyncClient(base_url=base_url, timeout=10)

    async def close(self) -> None:
        await self._client.aclose()

    async def list_alerts(self) -> list[AlertView]:
        data = await self._request("GET", "/alerts")
        return [AlertView.from_json(item) for item in data]

    async def create_alert(self, payload: dict) -> AlertView:
        data = await self._request("POST", "/alerts", json=payload)
        return AlertView.from_json(data)

    async def delete_alert(self, alert_id: str) -> None:
        await self._request("DELETE", f"/alerts/{alert_id}")

    async def enable_alert(self, alert_id: str) -> AlertView:
        return AlertView.from_json(await self._request("POST", f"/alerts/{alert_id}/enable"))

    async def disable_alert(self, alert_id: str) -> AlertView:
        return AlertView.from_json(await self._request("POST", f"/alerts/{alert_id}/disable"))

    async def get_quotes(self, symbols: list[str]) -> list[QuoteView]:
        data = await self._request("GET", "/market/quotes", params={"symbols": ",".join(symbols)})
        return [QuoteView.from_json(item) for item in data]

    async def get_screeners(self, scr_id: str, count: int = 5) -> list[QuoteView]:
        data = await self._request("GET", "/market/screeners", params={"scr_id": scr_id, "count": count})
        return [QuoteView.from_json(item) for item in data]

    async def search_screeners(
        self,
        filters: dict,
        size: int = 50,
        offset: int = 0,
        sort: str = "marketcap",
    ) -> ScreenerResultView:
        params = {"size": size, "offset": offset, "sort": sort}
        params.update(filters)
        data = await self._request("GET", "/market/screener", params=params)
        return ScreenerResultView.from_json(data)

    async def get_last_candle(self, symbol: str, interval: str = "1d") -> CandleView | None:
        data = await self._request(
            "GET", "/market/candles",
            params={"symbol": symbol, "interval": interval, "limit": 1},
        )
        if not data:
            return None
        return CandleView.from_json(data[-1])

    async def _request(self, method: str, path: str, **kwargs):
        resp = await self._client.request(method, path, **kwargs)
        if resp.status_code >= 400:
            detail = resp.json().get("detail", resp.text) if resp.content else resp.text
            raise ApiError(str(detail), resp.status_code)
        if resp.status_code == 204:
            return None
        return resp.json()