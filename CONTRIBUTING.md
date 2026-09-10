# Contributing to trading-tui

Thanks for taking the time to contribute. This document covers how to set up the
project, run it, test it, and get changes merged.

By participating you agree to the [Code of Conduct](CODE_OF_CONDUCT.md).

## Getting started

### Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) (recommended) or plain `pip`
- A cloned repo with the dev dependencies installed:

```bash
git clone https://github.com/corderkrow/trading-tui.git
cd trading-tui
uv pip install -e ".[dev]"
```

### Environment

The API reads configuration from `.env` at import time, so a `.env` is required
before the server starts:

```bash
cp .env.example .env
```

Key variables (see `app/config.py`):

| Variable | Default | Purpose |
|----------|---------|---------|
| `ADAPTER_NAME` | `yahoo` | `yahoo` or `binance` |
| `DEFAULT_SYMBOL` | `BTC-USD` | Default symbol for the TUI |
| `ALERTS_DB_PATH` | `alerts.db` | SQLite alerts database |
| `CURRENCY` | `usd` | Price formatting currency |
| `BINANCE_API_KEY` / `BINANCE_SECRET_KEY` | empty | Binance credentials |

TUI user preferences are stored separately in
`~/.config/trading-tui/settings.json` (override with `TRADING_TUI_SETTINGS`).

## Running the project

```bash
# API server (port 8333)
uvicorn app.main:app --reload --port 8333

# TUI client (spawns the API if needed)
uv run python -m tui_client.app
```

OpenAPI docs are served at http://127.0.0.1:8333/docs.

## Testing

```bash
# Full suite
pytest

# Single file / test
pytest tests/test_alert_service.py
pytest tests/test_conditions.py::test_crossing_transition
```

Rules:

- Every behavior change needs a test. Bug fixes should include a regression
  test that fails before the fix.
- Async tests use `pytest-asyncio` in `auto` mode (configured in
  `pyproject.toml`); just write `async def test_...`.
- TUI tests use Textual's `run_test()` pilot. Do not use `sleep`; await the app
  state instead.
- Keep tests hermetic: use the in-memory alert repository and mocked channels /
  adapters rather than hitting the network.

Make sure `pytest` passes before opening a pull request.

## Project layout

```
app/                 FastAPI server
  config.py          Settings (pydantic-settings)
  main.py            App factory + composition root
  models/            Pydantic DTOs (candles, tickers, alerts, websocket)
  router/            /market and /alerts endpoints
  services/          Business logic
    adapters/        Exchange adapters + registry
    alerts/          Alert domain, conditions, repository, service
    notifications.py Notification channel abstraction
    user_prefs.py    Reads the TUI delivery preference
tui_client/          Textual TUI
  api.py             HTTP client + view models
  screens/           Prices, alert list, create-alert, settings
  monitor.py         Background price-change monitor
  settings.py        Persisted user settings
tests/               pytest suite
```

### Architecture rules

- Keep the domain (`app/services/alerts/domain.py`) storage- and UI-agnostic.
- DTOs (`app/models/`) are separate from the domain and from the TUI view model
  (`tui_client/api.py`). Do not leak one layer into another.
- Wire dependencies through the composition root (`app/main.py`), not with
  module-level globals.
- The TUI never evaluates alert conditions — it goes through the REST API.

## Adding an exchange adapter

1. Subclass `MarketDataAdapter` in `app/services/adapters/base.py` and implement
   `fetch_candles`, `fetch_tickers`, and the `name` property. Override
   `fetch_screeners` / `fetch_screener_search` if the exchange supports them
   (raise `NotImplementedError` otherwise — the router maps it to HTTP 400).
2. Register it in `register_default_adapters()` in
   `app/services/adapters/registry.py`.
3. Add tests with a mocked HTTP client; never call a live exchange in tests.
4. Document any new env vars in `.env.example` and the README.

## Adding a notification channel

Implement the `NotificationChannel` protocol in
`app/services/notifications.py` and register it in `default_channels()`. Do not
change `AlertService` — it fans events out to whatever channels exist.

## Adding an alert condition

1. Add the operator to `Operator` in `app/services/alerts/domain.py`.
2. Register a strategy in `app/services/alerts/conditions.py` (use
   `build_condition` as the factory).
3. Surface it in the TUI create-alert modal (`tui_client/screens/create_alert.py`)
   if it is user-facing.
4. Add edge-case tests, including the previous-price behavior for `crossing`.

## Style

- Python is formatted to a 79-column soft limit; keep lines reasonably short and
  split long calls rather than exceeding it.
- Use type hints on functions and public attributes.
- Prefer dataclasses / Pydantic models over loose dicts at layer boundaries.
- Async-first: never block the event loop; use `httpx.AsyncClient` and
  `aiosqlite`.
- No new runtime dependency without discussion in an issue first.

There is no linter, formatter, or type checker configured yet — match the
surrounding code and keep diffs focused.

## Commit and pull request guidelines

- Use [Conventional Commits](https://www.conventionalcommits.org/) style
  subjects: `feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`.
- One logical change per commit; keep commits small and reviewable.
- A pull request should:
  - explain **what** changed and **why**;
  - link any related issue;
  - include tests and updated docs where behavior changed;
  - pass `pytest` locally.
- Do not commit secrets, `.env`, or `alerts.db`.

## Reporting bugs and requesting features

Open an issue with:

- steps to reproduce (for bugs);
- expected vs. actual behavior;
- your Python version, OS, and `ADAPTER_NAME`;
- relevant logs or the failing request/response.

For security issues, do not open a public issue — contact the maintainers
privately first.
