# trading-tui

## Project

Python 3.12 · FastAPI backend + Textual TUI client · async-first market data
Adapter pattern for exchange integrations · Pydantic v2 models · pydantic-settings for config

## Repo Layout

- `app/` — FastAPI server (entry: `app.main:app`)
  - `app/config.py` — `Settings` via pydantic-settings, reads `.env`
  - `app/models/` — Pydantic schemas (`CandleOHLCV`, `Ticker`, `WSMsg`)
  - `app/router/` — FastAPI routers (`/market/candles`, `/market/quotes`, `/market/screeners`, `/market/screener`; `/alerts`)
  - `app/services/` — business logic + adapter layer
  - `app/services/adapters/` — exchange adapter plugin system
- `tui_client/` — Textual TUI (screens: prices, alert list, create-alert modal; `api.py` HTTP client)
- `content_engine/` — YouTube series planning docs (not code)
- `benchmarks/` — empty
- `scripts/` — empty

## Dev Commands

```bash
# Install (editable)
uv pip install -e ".[dev]"

# Run API server
uvicorn app.main:app --reload

# Run tests
pytest

# Run single test
pytest tests/path/to/test.py::test_name
```

No linter, formatter, or typechecker configured yet. No Makefile or task runner.

## Key Architecture Notes

- **Adapter registry** (`app/services/adapters/registry.py`): exchanges register via `register_adapter()`. Default: `"yahoo"` → `YahooAdapter`. New adapters subclass `MarketDataAdapter` (abstract base in `base.py`).
- **Config**: `Settings` singleton from `app.config`. Env vars: `BINANCE_API_KEY`, `BINANCE_SECRET_KEY`, `DEFAULT_SYMBOL`, `ADAPTER_NAME`. Loads `.env` at import time.
- **API routes** under `/market` prefix. Dependency-injected adapter resolved from `settings.ADAPTER_NAME`.
- **WebSocket**: schema defined (`WSMsg`) but not yet mounted on the router.
- **Alerts storage**: SQLite via `aiosqlite` (`SqliteAlertRepository`, WAL mode). Path from `ALERTS_DB_PATH` (default project root `alerts.db`); Docker mounts a named volume at `/app/data`.
- **Docker**: `docker-compose.yml` runs API on port 8333, reads `.env`.

## Gotchas

- `.env` exists in repo (sets `ADAPTER_NAME=yahoo`, `DEFAULT_SYMBOL=BTC-USD`). API won't start without one (Pydantic settings loads at import).
- Screeners (`/market/screeners`, `/market/screener`) implemented only on `YahooAdapter`; `BinanceAdapter` raises `NotImplementedError` → 400.
- Adapter instances are created per-request via FastAPI DI — no shared client lifecycle.
- Binance adapter uses `httpx.AsyncClient` with 10s timeout, 20 max connections.
- TUI `AlertsApp` reuses a live server on :8333 if found — kill stale uvicorn/docker after changing `ADAPTER_NAME`.
- User-facing `trading-tui` launcher uses `/home/piryguiry/.local/share/trading-tui/venv` with a **non-editable** pip copy (`install.sh` installs from `$SRC_DIR`). Repo fixes are invisible to that TUI until reinstalled: `~/.local/share/trading-tui/venv/bin/python -m pip install --quiet <repo>`. Verify with `diff` of `tui_client/screens/prices.py` checksums.
