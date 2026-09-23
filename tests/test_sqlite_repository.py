"""SqliteAlertRepository behavior + persistence tests."""

from datetime import datetime, timedelta, timezone

import pytest

from app.services.alerts.domain import (
    Alert,
    AlertStatus,
    ConditionSpec,
    MatchMode,
    Operator,
    TriggerMode,
)
from app.services.alerts.errors import AlertNotFound
from app.services.alerts.repository import InMemoryAlertRepository
from app.services.alerts.sqlite_repository import SqliteAlertRepository
from tests.conftest import FakeClock


@pytest.fixture
async def repo_factory(tmp_path):
    """Build SqliteAlertRepository instances and close them after each test.

    aiosqlite spawns a worker thread per connection; leaving one open when
    pytest-asyncio closes the event loop raises PytestUnhandledThreadExceptionWarning.
    """

    repos: list[SqliteAlertRepository] = []

    def repo_factory(path: str | None = None) -> SqliteAlertRepository:
        repo = SqliteAlertRepository(path or str(tmp_path / "alerts.db"))
        repos.append(repo)
        return repo

    yield repo_factory
    for repo in repos:
        await repo.close()


def make_alert(**overrides) -> Alert:
    body = dict(
        symbol="ETHUSDT",
        conditions=[ConditionSpec(operator=Operator.ABOVE, value=100.0)],
        match_mode=MatchMode.ALL,
        trigger_mode=TriggerMode.ONCE,
        expires_at=datetime(2099, 1, 1, tzinfo=timezone.utc),
        message="ETHUSDT Above 100",
        notification_channels=["in_app", "toast"],
        status=AlertStatus.ACTIVE,
    )
    body.update(overrides)
    return Alert(**body)


async def test_create_get_roundtrip(tmp_path, repo_factory):
    repo = repo_factory()
    alert = make_alert()
    await repo.create(alert)
    got = await repo.get(alert.id)
    assert got == alert
    assert got.conditions == [ConditionSpec(operator=Operator.ABOVE, value=100.0)]
    assert got.expires_at == datetime(2099, 1, 1, tzinfo=timezone.utc)
    assert got.expires_at.tzinfo is not None


async def test_list_returns_insertion_order(tmp_path, repo_factory):
    repo = repo_factory()
    first = make_alert(symbol="BTCUSDT")
    second = make_alert(symbol="ETHUSDT")
    await repo.create(first)
    await repo.create(second)
    assert [a.id for a in await repo.list()] == [first.id, second.id]


async def test_update_persists_changes(tmp_path, repo_factory):
    repo = repo_factory()
    alert = make_alert()
    await repo.create(alert)
    alert.status = AlertStatus.DISABLED
    alert.triggered_at = datetime(2091, 5, 5, tzinfo=timezone.utc)
    await repo.update(alert)
    got = await repo.get(alert.id)
    assert got.status == AlertStatus.DISABLED
    assert got.triggered_at == alert.triggered_at


async def test_missing_alert_raises_not_found(tmp_path, repo_factory):
    repo = repo_factory()
    with pytest.raises(AlertNotFound):
        await repo.get("nope")
    with pytest.raises(AlertNotFound):
        await repo.update(make_alert(id="nope"))
    with pytest.raises(AlertNotFound):
        await repo.delete("nope")


async def test_delete_removes_alert(tmp_path, repo_factory):
    repo = repo_factory()
    alert = make_alert()
    await repo.create(alert)
    await repo.delete(alert.id)
    with pytest.raises(AlertNotFound):
        await repo.get(alert.id)


async def test_persists_across_instances(tmp_path, repo_factory):
    """File survives a fresh repository (simulates server restart)."""
    path = str(tmp_path / "alerts.db")
    repo1 = repo_factory(path)
    alert = make_alert()
    await repo1.create(alert)

    repo2 = repo_factory(path)
    assert await repo2.get(alert.id) == alert


async def test_wal_mode_enabled(tmp_path, repo_factory):
    import aiosqlite

    repo = repo_factory()
    await repo.create(make_alert())
    async with aiosqlite.connect(str(tmp_path / "alerts.db")) as conn:
        async with conn.execute("PRAGMA journal_mode") as cur:
            assert (await cur.fetchone())[0].lower() == "wal"


async def test_service_flow_with_sqlite(tmp_path, repo_factory):
    """Real AlertService over SQLite: expiry, disable skip, once-only trigger."""
    from app.services.alerts.service import AlertService
    from app.services.notifications import NotificationService

    clock = FakeClock()
    repo = repo_factory()
    service = AlertService(repository=repo, notifications=NotificationService(), clock=clock)

    expires = clock() + timedelta(days=1)
    alert = make_alert(expires_at=expires, trigger_mode=TriggerMode.ONCE)
    await repo.create(alert)

    # Expiry: alert flips to EXPIRED, never evaluated
    clock.advance(days=2)
    events = await service.handle_price("ETHUSDT", 150.0)
    assert events == []
    assert (await service.get(alert.id)).status == AlertStatus.EXPIRED

    # New alert triggers ONCE, then stays TRIGGERED across price updates
    fresh = make_alert(symbol="BTCUSDT", expires_at=None)
    await repo.create(fresh)
    events = await service.handle_price("BTCUSDT", 120.0)
    assert len(events) == 1
    assert (await service.get(fresh.id)).status == AlertStatus.TRIGGERED
    assert (await service.handle_price("BTCUSDT", 999.0)) == []

    # Disabled alerts are skipped
    disabled = make_alert(symbol="SOLUSDT", expires_at=None, status=AlertStatus.DISABLED)
    await repo.create(disabled)
    assert await service.handle_price("SOLUSDT", 999.0) == []


async def test_update_many_persists_batch(tmp_path, repo_factory):
    repo = repo_factory()
    first = make_alert(symbol="BTCUSDT")
    second = make_alert(symbol="ETHUSDT")
    await repo.create(first)
    await repo.create(second)
    first.status = AlertStatus.DISABLED
    second.status = AlertStatus.EXPIRED
    await repo.update_many([first, second])
    assert (await repo.get(first.id)).status == AlertStatus.DISABLED
    assert (await repo.get(second.id)).status == AlertStatus.EXPIRED


async def test_update_many_missing_alert_raises(tmp_path, repo_factory):
    repo = repo_factory()
    with pytest.raises(AlertNotFound):
        await repo.update_many([make_alert(id="nope")])


async def test_swap_parity_with_inmemory(tmp_path, repo_factory):
    """Same operations behave identically on both repository implementations."""
    for repo in (InMemoryAlertRepository(), repo_factory()):
        alert = make_alert()
        await repo.create(alert)
        assert (await repo.get(alert.id)).id == alert.id
        assert len(await repo.list()) == 1
        with pytest.raises(AlertNotFound):
            await repo.get("missing")