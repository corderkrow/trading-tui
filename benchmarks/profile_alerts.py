"""Baseline/after profiler for the alert evaluation path.

`AlertService.handle_price` is the hot path: every price tick walks the alert
table and persists the evaluated batch. With the SQLite repository each
persisted alert was a separate `commit()` (one fsync per alert per tick).

This measures wall time and, deterministically, the number of commits.

Run:
    python benchmarks/profile_alerts.py --out benchmarks/results/alerts_baseline.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import aiosqlite  # noqa: E402

from app.models.alert import CreateAlertRequest, ConditionRequest  # noqa: E402
from app.services.alerts.service import AlertService  # noqa: E402
from app.services.alerts.sqlite_repository import SqliteAlertRepository  # noqa: E402

ALERTS = 50
TICKS = 20
SYMBOL = "ETHUSDT"


async def make_service(db_path: str, count: int) -> AlertService:
    service = AlertService(repository=SqliteAlertRepository(db_path))
    request = CreateAlertRequest(
        symbol=SYMBOL,
        # A price no tick reaches, so nothing triggers: isolates the persist path.
        conditions=[ConditionRequest(operator="above", value=1e9)],
        notification_channels=["in_app"],
    )
    for _ in range(count):
        await service.create(request)
    return service


def count_commits():
    """Patch aiosqlite commit() to count fsync-inducing calls."""
    state = {"n": 0}
    orig = aiosqlite.Connection.commit

    async def counting(self):
        state["n"] += 1
        return await orig(self)

    aiosqlite.Connection.commit = counting
    return state, orig


async def run() -> dict:
    with tempfile.TemporaryDirectory() as tmp:
        db = str(Path(tmp) / "alerts.db")

        state, orig = count_commits()
        try:
            service = await make_service(db, ALERTS)
        finally:
            aiosqlite.Connection.commit = orig

        # time the read path alone (the full-table scan per tick)
        t = time.perf_counter()
        await service.repository.list()
        list_ms = (time.perf_counter() - t) * 1000

        state, orig = count_commits()
        try:
            t = time.perf_counter()
            for _ in range(TICKS):
                await service.handle_price(SYMBOL, 100.0)
            elapsed = time.perf_counter() - t
        finally:
            aiosqlite.Connection.commit = orig

        await service.repository.close()

        return {
            "alerts": ALERTS,
            "ticks": TICKS,
            "list_only_ms": round(list_ms, 2),
            "handle_price_total_ms": round(elapsed * 1000, 2),
            "handle_price_ms_per_tick": round(elapsed / TICKS * 1000, 2),
            "commits_total": state["n"],
            "commits_per_tick": round(state["n"] / TICKS, 2),
        }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, help="write JSON results to this path")
    args = parser.parse_args()

    results = asyncio.run(run())
    text = json.dumps(results, indent=2)
    print(text)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text + "\n", encoding="utf-8")
        print(f"\nwrote {args.out}", file=sys.stderr)


if __name__ == "__main__":
    main()
