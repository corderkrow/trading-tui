"""Pydantic schemas for ticker data."""

from pydantic import BaseModel, Field


class Ticker(BaseModel):
    symbol: str = Field(..., description="Trading pair, e.g. BTCUSDT")
    price: float = Field(..., gt=0, description="Last trade price")
    change_24h: float | None = Field(default=None, description="24h change in percent")
    name: str | None = Field(default=None, description="Company short name")
    volume: float | None = Field(default=None, description="Regular market volume")
    market_cap: float | None = Field(default=None, description="Market capitalization")


class ScreenerResult(BaseModel):
    total: int = Field(..., description="Total matches in the full universe")
    quotes: list[Ticker] = Field(default_factory=list)


class QuoteResponse(BaseModel):
    symbol: str
    price: float
    change_24h: float | None = None
    volume_24h: float | None = None