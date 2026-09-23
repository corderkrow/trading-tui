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
mirrored by the FastAPI app title (`app/main.py`). Tags are named `X.Y.Z`.

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
- Linter / type checker / CI.

## [0.2.1] - 2026-09-23

### Fixed

- **Stale OHLC in the prices screen**: the first candle fetched for a symbol was
  cached for the whole session. Candles now refresh on the configured refresh
  interval, so the OHLC column keeps up with the quotes.
- **Yahoo quotes with no price**: symbols Yahoo returns without a price are now
  skipped instead of failing the whole request with a validation error.
- **Expiration during a list read** wrote one commit per expired alert; expired
  alerts are now persisted in a single transaction.

### Changed

- **One adapter per app**: the market-data adapter (and its HTTP connection
  pool) is created once in `create_app` and closed on shutdown, instead of a new
  adapter + client per request. The Yahoo cookie/crumb pair now survives between
  requests. `create_app` accepts an optional `adapter=` for tests and overrides.
- **Batched Yahoo quotes**: `YahooAdapter.fetch_tickers` issues a single
  `/v7/finance/quote` request, falling back to concurrent per-symbol reads when
  the cookie/crumb pair is unavailable. `ScreenerAuthError` is renamed to
  `YahooAuthError` since it now covers quote auth too.
- **Batched alert persistence**: `AlertService.handle_price` persists all
  evaluated alerts through the new `AlertRepository.update_many`, so a tick
  writes one transaction instead of one commit per alert. The condition strategy
  map is built once per process, and one `MarketContext` is built per alert
  evaluation.
- **Delivery preference caching**: the notification delivery filter reads the
  settings file only when its mtime changes.
- **Prices screen**: filtered rows are computed once per rebuild instead of
  three times, and the page count reuses an already-filtered list.

### Performance

Measured with the new benchmarks (medians over repeated runs):

- `GET /market/quotes` (6 symbols): **1,133 ms → 141 ms**.
- `GET /market/candles` (`limit=1000`): **419 ms → 161 ms**.
- Alert evaluation, 50 alerts: **233 ms → 5.7 ms** per tick, commits per tick
  **50 → 1**.
- Prices screen rebuild, 250 quotes: **1.68 ms → 0.99 ms** (filter scans 3 → 1).

### Added

- Benchmarks: `benchmarks/profile_market.py` and `benchmarks/profile_alerts.py`,
  with recorded runs under `benchmarks/results/`.
- `tests/test_yahoo_adapter.py`: batched quotes, missing prices, the shared
  adapter dependency, and adapter shutdown on lifespan exit.
- Coverage for `update_many`, the delivery-preference cache, and candle
  refresh/cache reuse.

## [0.2.0] - 2026-09-15

### Added

- **Percent-change alert conditions**: new `change_pct` metric with `rises_by`,
  `falls_by`, `turns_positive` and `turns_negative` operators, evaluated against
  the previous tick and selectable in the create-alert modal.
- **Symbol search** (`GET /market/search`): free-text lookup over the full Yahoo
  universe, with fallbacks for concatenated crypto pairs (`btcusd` → `BTC-USD`).
- **Symbol news** (`GET /market/news`): latest per-symbol headlines via Yahoo's
  RSS headline feed.
- **Symbol info screen** in the TUI (select a row): quote stats plus latest news.
- **Server-backed search** in the prices screen: typing a term resolves symbols
  on the exchange and shows the matched quotes.
- **Display settings**: refresh interval (5-60 min), watchlist rotation interval,
  news display toggle and per-asset news count, and a "disable custom alerts"
  switch; the settings modal now shows the app version.

### Changed

- Alert evaluation tracks previous price and percent change per symbol instead of
  per-condition history, enabling the variation and turn conditions.
- `install.sh` installs the package in editable mode; banner colors follow the
  active Textual theme.

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

[Unreleased]: https://github.com/corderkrow/trading-tui/compare/0.2.1...HEAD
[0.2.1]: https://github.com/corderkrow/trading-tui/compare/0.2.0...0.2.1
[0.2.0]: https://github.com/corderkrow/trading-tui/compare/0.1.0...0.2.0
[0.1.0]: https://github.com/corderkrow/trading-tui/releases/tag/0.1.0
