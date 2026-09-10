"""Pydantic schemas for candle data."""

from pydantic import BaseModel, Field


class CandleOHLCV(BaseModel):
    timestamp: int = Field(..., description="Unix ms")
    open: float
    high: float
    low: float
    close: float
    volume: float
