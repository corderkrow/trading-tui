"""SQLite-backed AlertRepository (aiosqlite, WAL mode).

Connection is opened lazily on first operation, so importing this module or
building the app never touches the filesystem. Swap-in replacement for
InMemoryAlertRepository — same AlertRepository protocol.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime

import aiosqlite

from app.services.alerts.domain import (
    Alert,
    AlertStatus,
    ConditionSpec,
    MatchMode,
    Operator,
    TriggerMode,
)
from app.services.alerts.errors import AlertNotFound

_SCHEMA = """
CREATE TABLE IF NOT EXISTS alerts (
    id TEXT PRIMARY KEY,
    symbol TEXT NOT NULL,
    conditions TEXT NOT NULL,
    match_mode TEXT NOT NULL,
    trigger_mode TEXT NOT NULL,
    expires_at TEXT,
    message TEXT NOT NULL,
    notification_channels TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    triggered_at TEXT,
    last_evaluated_at TEXT
)
"""


def _to_row(alert: Alert) -> tuple:
    return (
        alert.id,
        alert.symbol,
        json.dumps(
            [
                {"metric": c.metric, "operator": c.operator.value, "value": c.value}
                for c in alert.conditions
            ]
        ),
        alert.match_mode.value,
        alert.trigger_mode.value,
        _to_dt(alert.expires_at),
        alert.message,
        json.dumps(alert.notification_channels),
        alert.status.value,
        _to_dt(alert.created_at),
        _to_dt(alert.triggered_at),
        _to_dt(alert.last_evaluated_at),
    )


def _from_row(row: sqlite3.Row) -> Alert:
    return Alert(
        id=row["id"],
        symbol=row["symbol"],
        conditions=[
            ConditionSpec(
                metric=c["metric"],
                operator=Operator(c["operator"]),
                value=c["value"],
            )
            for c in json.loads(row["conditions"])
        ],
        match_mode=MatchMode(row["match_mode"]),
        trigger_mode=TriggerMode(row["trigger_mode"]),
        expires_at=_from_dt(row["expires_at"]),
        message=row["message"],
        notification_channels=json.loads(row["notification_channels"]),
        status=AlertStatus(row["status"]),
        created_at=_from_dt(row["created_at"]),
        triggered_at=_from_dt(row["triggered_at"]),
        last_evaluated_at=_from_dt(row["last_evaluated_at"]),
    )


def _to_dt(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _from_dt(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value is not None else None


class SqliteAlertRepository:
    """AlertRepository backed by a single SQLite file. WAL for concurrent reads."""

    def __init__(self, db_path: str = "alerts.db") -> None:
        self._db_path = db_path
        self._conn: aiosqlite.Connection | None = None

    async def _connect(self) -> aiosqlite.Connection:
        if self._conn is None:
            conn = await aiosqlite.connect(self._db_path)
            conn.row_factory = sqlite3.Row
            await conn.execute("PRAGMA journal_mode=WAL")
            await conn.execute(_SCHEMA)
            await conn.commit()
            self._conn = conn
        return self._conn

    async def create(self, alert: Alert) -> Alert:
        conn = await self._connect()
        await conn.execute(
            "INSERT OR REPLACE INTO alerts VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            _to_row(alert),
        )
        await conn.commit()
        return alert

    async def get(self, alert_id: str) -> Alert:
        conn = await self._connect()
        async with conn.execute(
            "SELECT * FROM alerts WHERE id = ?", (alert_id,)
        ) as cur:
            row = await cur.fetchone()
        if row is None:
            raise AlertNotFound(alert_id)
        return _from_row(row)

    async def list(self) -> list[Alert]:
        conn = await self._connect()
        async with conn.execute(
            "SELECT * FROM alerts ORDER BY rowid"
        ) as cur:
            return [_from_row(row) for row in await cur.fetchall()]

    async def update(self, alert: Alert) -> Alert:
        conn = await self._connect()
        cur = await conn.execute(
            "UPDATE alerts SET symbol=?, conditions=?, match_mode=?, trigger_mode=?,"
            " expires_at=?, message=?, notification_channels=?, status=?,"
            " created_at=?, triggered_at=?, last_evaluated_at=? WHERE id=?",
            (*_to_row(alert)[1:], alert.id),
        )
        if cur.rowcount == 0:
            raise AlertNotFound(alert.id)
        await conn.commit()
        return alert

    async def delete(self, alert_id: str) -> None:
        conn = await self._connect()
        cur = await conn.execute("DELETE FROM alerts WHERE id = ?", (alert_id,))
        if cur.rowcount == 0:
            raise AlertNotFound(alert_id)
        await conn.commit()

    async def close(self) -> None:
        """Release the connection (and its worker thread)."""
        if self._conn is not None:
            await self._conn.close()
            self._conn = None