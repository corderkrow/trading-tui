# trading-tui

## Project

Python 3.12 · FastAPI backend + Textual TUI client · async-first market data
Adapter pattern for exchange integrations · Pydantic v2 models · pydantic-settings for config

## Project Rules

Rules live in `.ai/rules/` (one folder per area, body in `RULES.md`). OpenCode V2 does not auto-load them. At the start of a task:

1. Read the index: [`.ai/rules/README.md`](.ai/rules/README.md)
2. Open every rule that applies to the task — mandatory before any design/UI work (`brand/RULES.md`).

Update the index table when adding a rule (see "Adding a rule" there).

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

<!-- gitbutler-agent-setup:start -->
## Version control

- Use GitButler (`but`) for version-control inspection and write operations, including status, diffs, branching, committing, pushing, and history edits.
- Assume multiple agents may be working in this repository. Do not move, amend, squash, discard, commit, push, or otherwise modify another agent's work unless the user asks.
- For commit just/only/specific changes on a new branch (selected-change requests), use the two-command fast path from the GitButler skill: `but diff`, then `but commit -b <branch> -m "message" <id> <id>`.
- For that fast path, after the commit succeeds, stop and summarize; do not run separate branch, staging, status, or diff commands unless the commit output is missing information you need.
- Use the installed GitButler skill for command recipes and syntax before guessing flags, using `--help`, or translating Git habits directly.
- Mutation commands report their result without appending workspace status. Add `--status-after` only when the next step needs resulting workspace IDs or details; otherwise do not rerun status or diff to verify success.
- Use a dedicated GitButler branch for each agent session, unless the user asks for a different branch structure. Commit only changes that belong to that session.
- Do not push or open pull requests unless the user asks.
- Keep commit messages and pull request descriptions succinct: explain what changed, why it changed, and any important decision.

### Amend local fixes into the right commits

- For small cleanup or follow-up fixes, amend an unpublished local commit when the change clearly belongs with that commit's intent.
- Do not create tiny fixup commits unless the user asks.
- Use GitButler to move the relevant changes into the commit where they belong.
- Ask before rewriting pushed, reviewed, shared, or ambiguous history.

### Split unrelated changes into separate commits

- If one file contains unrelated changes, split them by hunk instead of committing the whole file.
- Keep tests with the behavior they verify.
- Split generated output, docs-only edits, or mechanical cleanup into separate commits when each commit remains coherent on its own.
- If the split is ambiguous, summarize the options before committing.
<!-- gitbutler-agent-setup:end -->
