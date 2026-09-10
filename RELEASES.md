# Releases

All notable changes to **trading-tui** are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## Versioning policy

- `MAJOR` — incompatible changes to the REST API or the on-disk alert /
  settings formats.
- `MINOR` — backward-compatible features (new endpoints, adapters, channels,
  TUI capabilities).
- `PATCH` — backward-compatible bug fixes.

The version is defined once in `pyproject.toml` (`[project].version`) and
mirrored by the FastAPI app title (`app/main.py`). Tags are named `vX.Y.Z`.

## [Unreleased]

### Planned

- Live WebSocket market feed (`/market/ws`) — schema (`WSMsg`) exists, endpoint
  not yet mounted.
- Real notification channels (Email, Webhook, Discord, Telegram); `toast`,
  `sound`, `push`, `email` are currently no-op placeholders.
- Portfolio holdings + `portfolio` price-change source.
- Candlestick charts and technical indicators (Plotly is a dependency).
- Binance screeners / custom screener (`NotImplementedError` today).
- Automatic alert evaluation wired to the price stream (currently via
  `POST /alerts/evaluate` only).
- Shared adapter HTTP-client lifecycle; linter / type checker / CI.

## [0.1.0] - unreleased

Initial release.

### Added

- **Market data REST API** (`/market`): candles, quotes, predefined screeners
  (`most_actives` / `gainers` / `losers`) and a custom full-universe screener
  (`region`, `sector`, `mincap`, `maxcap`, sort, pagination).
- **Exchange adapter plugin system**: abstract `MarketDataAdapter`, a registry
  (`register_adapter`), and two adapters — `yahoo` (default, no API key,
  including screeners with automatic cookie+crumb auth) and `binance`
  (candles + quotes).
- **Price alerts** (`/alerts`): CRUD, enable/disable, and `/alerts/evaluate`.
  Conditions support `above` / `below` / `crossing`, `ALL`/`ANY` combination,
  `ONCE`/`EVERY_TIME` triggering, timezone-aware expiration, custom messages,
  and the `ACTIVE → TRIGGERED | EXPIRED | DISABLED` lifecycle.
- **Alert domain + services**: condition strategy factory, observer-style
  `AlertService.handle_price`, and repository abstraction.
- **SQLite persistence** via `aiosqlite` (WAL mode; `ALERTS_DB_PATH`) plus an
  in-memory repository for tests.
- **Notification channels**: `NotificationChannel` protocol, `NotificationService`
  fan-out, the working `in_app` channel, and no-op `toast` / `sound` / `push` /
  `email` placeholders. A global delivery preference filters dispatch.
- **Textual TUI** (`tui_client`): Gruvbox-themed prices screen with predefined
  lists, multiple watchlists, a custom screener, sort (`1`-`5`), change filters
  (`f`/`u`/`d`), search (`/`), pagination (`[`/`]`), latest OHLC and per-symbol
  alert state; alerts list with create modal and enable/disable/delete; and a
  settings modal (`o`).
- **Background price-change monitor**: 60s quote poll with threshold toasts and
  re-arming logic.
- **Currency formatting**: 16 currencies via `CURRENCY`, with locale-aware
  symbols and separators.
- **User settings**: watchlists and notification preferences persisted
  atomically to `~/.config/trading-tui/settings.json`
  (`TRADING_TUI_SETTINGS` override).
- **Packaging & deploy**: `trading-tui` / `trading-tui-api` console scripts,
  `install.sh` installer, multi-stage `Dockerfile`, `docker-compose.yml`, and
  `.env.example`.
- **Tests**: pytest suite covering conditions, the alert service, both
  repositories, the REST surface, notification delivery, settings, and TUI
  flows via Textual's pilot.

[Unreleased]: https://github.com/corderkrow/trading-tui/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/corderkrow/trading-tui/releases/tag/v0.1.0
