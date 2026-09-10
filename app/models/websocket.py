"""WebSocket message schema."""

from pydantic import BaseModel


class WSMsg(BaseModel):
    type: str  # "candle", "ticker", "depth"
    symbol: str
    data: dict
