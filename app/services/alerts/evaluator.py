"""Background evaluator — keeps stored alerts firing without external ticks.

The REST `/alerts/evaluate` endpoint only fires alerts when a client
explicitly pushes a price; nothing does that in practice, so stored alerts
would never trigger. This module owns a daemon task that:

1. Polls the alert service for the set of symbols holding active alerts.
2. Fetches fresh quotes for those symbols from the market-data adapter.
3. Feeds each tick back through `AlertService.handle_price`.
4. Sweeps expired ACTIVE alerts so statuses stay truthful without API calls.

Loop errors are caught and logged — the monitor keeps running across transient
adapter/network failures.
"""

from __future__ import annotations

import asyncio
import contextlib
import sys
from typing import Protocol

from app.services.adapters.base import MarketDataAdapter
from app.services.alerts.service import AlertService

POLL_SECONDS = 30.0


class AlertPriceFeed(Protocol):
    """Everything the evaluator needs from the app — easy to fake in tests."""

    def alert_service(self) -> AlertService: ...

    def adapter(self) -> MarketDataAdapter: ...


class BackgroundAlertEvaluator:
    def __init__(
        self,
        service: AlertService,
        adapter: MarketDataAdapter,
        poll_seconds: float = POLL_SECONDS,
    ) -> None:
        self._service = service
        self._adapter = adapter
        self._poll_seconds = poll_seconds
        self._task: asyncio.Task | None = None

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None

    async def poll_once(self) -> list[tuple[str, float, int]]:
        """One evaluation pass.

        Returns (symbol, price, events_fired) triples — the endpoint surface
        for tests and observability.
        """
        symbols = sorted(await self._service.active_symbols())
        results: list[tuple[str, float, int]] = []
        if not symbols:
            return results
        tickers = await self._adapter.fetch_tickers(symbols)
        known = {t.symbol for t in tickers}
        for ticker in tickers:
            events = await self._service.handle_price(ticker.symbol, ticker.price)
            if events:
                results.append((ticker.symbol, ticker.price, len(events)))

        # Symbols the adapter silently dropped (halted/delisted) would go
        # un-evaluated forever; sweep their alerts for expiry/pruning here.
        missing = [s for s in symbols if s not in known]
        for symbol in missing:
            await self._service.sweep_symbol(symbol)
        if missing:
            results.extend((s, 0.0, 0) for s in missing)
        return results

    async def _run(self) -> None:
        while True:
            try:
                await self.poll_once()
            except Exception as exc:  # transient network/adapter failures
                print(f"alert evaluator cycle failed: {exc}", file=sys.stderr)
            await asyncio.sleep(self._poll_seconds)
