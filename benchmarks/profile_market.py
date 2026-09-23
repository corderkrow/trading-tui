"""Baseline/after profiler for the market-data path.

Measures the structural costs behind the survey findings:
  * per-request adapter + httpx.AsyncClient construction (leak / pool churn)
  * serial N+1 fan-out in YahooAdapter.fetch_tickers
  * end-to-end ASGI latency for /market/quotes and /market/candles

Run:
    python benchmarks/profile_market.py --live --out benchmarks/results/baseline.json

Live mode hits the real Yahoo endpoints; keep the symbol list and repeat counts
small to stay under rate limits. Results are JSON so baseline/after runs diff.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import statistics
import sys
import time
from contextlib import AsyncExitStack
from pathlib import Path

# Keep the profiler off the repo's alerts.db (settings load at import time).
os.environ.setdefault("ALERTS_DB_PATH", ":memory:")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx  # noqa: E402

from app.main import create_app  # noqa: E402
from app.services.adapters.yahoo import YahooAdapter  # noqa: E402

SYMBOLS = ["AAPL", "MSFT", "NVDA", "BTC-USD", "ETH-USD", "TSLA"]
ASGI_BASE = "http://bench"


def _ms(seconds: float) -> float:
    return round(seconds * 1000, 2)


def _stats(samples: list[float]) -> dict:
    return {
        "n": len(samples),
        "mean_ms": _ms(statistics.mean(samples)),
        "median_ms": _ms(statistics.median(samples)),
        "min_ms": _ms(min(samples)),
        "max_ms": _ms(max(samples)),
    }


async def bench_construct(repeat: int = 100) -> dict:
    """Cost of building one YahooAdapter (one fresh httpx.AsyncClient + pool)."""
    samples: list[float] = []
    adapters = []
    for _ in range(repeat):
        t = time.perf_counter()
        adapter = YahooAdapter()
        samples.append(time.perf_counter() - t)
        adapters.append(adapter)
    for adapter in adapters:
        await adapter.close()
    return _stats(samples)


async def bench_client_churn(repeat: int = 5) -> dict:
    """Count AsyncClient instances created vs closed across ASGI requests.

    Uses DI exactly as production (`Depends(get_market_adapter)`), so any
    newly constructed-but-unclosed client shows up here. ASGITransport skips
    lifespan, so the app's lifespan is entered manually to exercise shutdown.
    """
    created = 0
    closed = 0
    orig_init = httpx.AsyncClient.__init__
    orig_close = httpx.AsyncClient.aclose

    def counting_init(self, *args, **kwargs):
        nonlocal created
        created += 1
        return orig_init(self, *args, **kwargs)

    async def counting_close(self):
        nonlocal closed
        closed += 1
        return await orig_close(self)

    httpx.AsyncClient.__init__ = counting_init
    httpx.AsyncClient.aclose = counting_close
    try:
        app = create_app()
        transport = httpx.ASGITransport(app=app)
        async with AsyncExitStack() as stack:
            if hasattr(app.state, "market_adapter"):
                await stack.enter_async_context(app.router.lifespan_context(app))
            client = await stack.enter_async_context(
                httpx.AsyncClient(transport=transport, base_url=ASGI_BASE)
            )
            for _ in range(repeat):
                resp = await client.get(
                    "/market/quotes", params={"symbols": ",".join(SYMBOLS[:2])}
                )
                resp.raise_for_status()
    finally:
        httpx.AsyncClient.__init__ = orig_init
        httpx.AsyncClient.aclose = orig_close

    return {"requests": repeat, "clients_created": created, "clients_closed": closed}


async def bench_tickers_fetch(adapter: YahooAdapter) -> dict:
    """Real latency of fetch_tickers for 1 vs N symbols (per-symbol cost)."""
    t = time.perf_counter()
    await adapter.fetch_tickers(SYMBOLS[:1])
    one = time.perf_counter() - t

    t = time.perf_counter()
    await adapter.fetch_tickers(SYMBOLS)
    six = time.perf_counter() - t
    return {
        "one_symbol_ms": _ms(one),
        "six_symbols_ms": _ms(six),
        "per_symbol_ms": _ms(six / len(SYMBOLS)),
    }


async def bench_quotes_concurrent(adapter: YahooAdapter) -> dict:
    """Target cost: N quote fetches issued concurrently on one shared client."""
    async def one(symbol: str):
        return await adapter._client.get(
            f"/v8/finance/chart/{symbol}",
            params={"interval": "1d", "range": "1d"},
        )

    t = time.perf_counter()
    await asyncio.gather(*(one(s) for s in SYMBOLS))
    return {"six_symbols_concurrent_ms": _ms(time.perf_counter() - t)}


async def bench_asgi_quotes(repeat: int = 3) -> dict:
    app = create_app()
    transport = httpx.ASGITransport(app=app)
    samples: list[float] = []
    async with httpx.AsyncClient(transport=transport, base_url=ASGI_BASE) as client:
        for _ in range(repeat):
            t = time.perf_counter()
            resp = await client.get(
                "/market/quotes", params={"symbols": ",".join(SYMBOLS)}
            )
            resp.raise_for_status()
            samples.append(time.perf_counter() - t)
    return _stats(samples)


async def bench_asgi_candles(repeat: int = 3) -> dict:
    app = create_app()
    transport = httpx.ASGITransport(app=app)
    samples: list[float] = []
    async with httpx.AsyncClient(transport=transport, base_url=ASGI_BASE) as client:
        for _ in range(repeat):
            t = time.perf_counter()
            resp = await client.get(
                "/market/candles",
                params={"symbol": "AAPL", "interval": "1d", "limit": 1000},
            )
            resp.raise_for_status()
            samples.append(time.perf_counter() - t)
    return _stats(samples)


async def run(live: bool) -> dict:
    results: dict = {}

    results["adapter_construct"] = await bench_construct()

    if not live:
        results["_note"] = "network-free sections only (pass --live for Yahoo calls)"
        return results

    adapter = YahooAdapter()
    try:
        results["quotes_concurrent_target"] = await bench_quotes_concurrent(adapter)
        results["tickers_fetch"] = await bench_tickers_fetch(adapter)
    finally:
        await adapter.close()

    results["client_churn"] = await bench_client_churn()
    results["asgi_quotes_6"] = await bench_asgi_quotes()
    results["asgi_candles_1000"] = await bench_asgi_candles()
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="hit real Yahoo endpoints")
    parser.add_argument("--out", type=Path, help="write JSON results to this path")
    args = parser.parse_args()

    results = asyncio.run(run(args.live))
    text = json.dumps(results, indent=2)
    print(text)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text + "\n", encoding="utf-8")
        print(f"\nwrote {args.out}", file=sys.stderr)


if __name__ == "__main__":
    main()
