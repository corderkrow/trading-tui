"""Custom exceptions + HTTP exception handlers."""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.services.alerts.errors import AlertError


class MarketError(Exception):
    """Raised when market data API fails."""

    def __init__(self, message: str = "Market data error", code: int = 500):
        super().__init__(message)
        self.message = message
        self.code = code


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(MarketError)
    async def market_error_handler(_: Request, exc: MarketError) -> JSONResponse:
        return JSONResponse(status_code=exc.code, content={"detail": exc.message})

    @app.exception_handler(AlertError)
    async def alert_error_handler(_: Request, exc: AlertError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.message})

    @app.exception_handler(Exception)
    async def generic_error_handler(_: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error"},
        )
