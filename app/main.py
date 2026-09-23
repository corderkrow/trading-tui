"""FastAPI entry point + WebSocket router mount."""

from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI

from app.config import settings
from app.core.exceptions import register_exception_handlers
from app.router.alerts import router as alerts_router
from app.router.market_data import router as market_router
from app.services.adapters import get_adapter
from app.services.adapters.base import MarketDataAdapter
from app.services.alerts.service import AlertService
from app.services.alerts.sqlite_repository import SqliteAlertRepository
from app.services.notifications import NotificationService
from app.services.user_prefs import allowed_channels


@asynccontextmanager
async def _lifespan(app: FastAPI):
    """Release the shared market-data adapter (and its connection pool) on exit."""
    yield
    adapter: MarketDataAdapter = app.state.market_adapter
    await adapter.close()


def create_app(
    alert_service: AlertService | None = None,
    adapter: MarketDataAdapter | None = None,
) -> FastAPI:
    app = FastAPI(
        title="Trading TUI API",
        version="0.2.3",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=_lifespan,
    )
    register_exception_handlers(app)
    app.state.alert_service = alert_service or AlertService(
        repository=SqliteAlertRepository(settings.ALERTS_DB_PATH),
        notifications=NotificationService(delivery_filter=allowed_channels),
    )
    # One adapter per process: reuses the HTTP connection pool, the Yahoo
    # crumb/cookie pair, and avoids leaking a client per request.
    app.state.market_adapter = adapter or get_adapter(settings.ADAPTER_NAME)
    app.include_router(market_router)
    app.include_router(alerts_router)
    return app


def run_api() -> None:
    """Console-script entry (`trading-tui-api`). Run from a dir with .env."""
    uvicorn.run("app.main:app", host="127.0.0.1", port=8333)


app = create_app()
