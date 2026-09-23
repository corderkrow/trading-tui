"""Pilot tests for the multi-condition ``AlertScreen`` (Textual ``run_test``)."""

from __future__ import annotations

import pytest
from textual.app import App
from textual.widgets import Button, Input, Select, Static

from tui_client.alerts.models import MAX_CONDITIONS, AlertSpec
from tui_client.alerts.screens import AlertScreen, ConditionEditorScreen
from tui_client.alerts.widgets import ConditionList


class AlertHost(App[None]):
    """Minimal host so the modal can be exercised on its own."""

    def __init__(self, **alert_kwargs) -> None:
        super().__init__()
        self.result: AlertSpec | None = None
        self._alert_kwargs = alert_kwargs

    def on_mount(self) -> None:
        self.push_screen(AlertScreen(**self._alert_kwargs), self._store)

    def _store(self, spec: AlertSpec | None) -> None:
        self.result = spec


async def wait_until(pilot, predicate, tries: int = 200) -> bool:
    for _ in range(tries):
        if predicate():
            return True
        await pilot.pause()
    return predicate()


async def add_condition(
    pilot,
    value: str,
    operator: str = "Crossing",
    timeframe: str = "1m",
) -> None:
    """Open the editor via ``ctrl+n``, fill it and confirm."""
    app = pilot.app
    await pilot.press("ctrl+n")
    assert await wait_until(pilot, lambda: isinstance(app.screen, ConditionEditorScreen))
    editor = app.screen
    editor.query_one("#operator", Select).value = operator
    editor.query_one("#timeframe", Select).value = timeframe
    editor.query_one("#value", Input).value = value
    await pilot.pause()
    await pilot.press("ctrl+s")
    assert await wait_until(pilot, lambda: isinstance(app.screen, AlertScreen))


@pytest.fixture
async def alert_app():
    app = AlertHost(default_symbol="BTCUSDT")
    async with app.run_test(size=(80, 30)) as pilot:
        await wait_until(pilot, lambda: isinstance(app.screen, AlertScreen))
        yield app, pilot


def list_conditions(app) -> list:
    return list(app.screen.query_one("#condition-list", ConditionList).conditions)


async def test_mode_a_inline_initially(alert_app):
    app, _ = alert_app
    assert app.screen.query_one("#condition-inline").display is True
    assert app.screen.query_one("#condition-list", ConditionList).display is False


async def test_add_up_to_max_then_blocked(alert_app):
    app, pilot = alert_app
    for index in range(MAX_CONDITIONS - 1):  # inline holds condition #1
        await add_condition(pilot, str(100 + index))

    assert len(list_conditions(app)) == MAX_CONDITIONS
    add_button = app.screen.query_one("#add_condition", Button)
    assert add_button.disabled is True
    assert add_button.label.plain == f"+ Add condition ({MAX_CONDITIONS}/{MAX_CONDITIONS})"

    await pilot.press("ctrl+n")  # noop at the cap
    await pilot.pause()
    assert isinstance(app.screen, AlertScreen)
    assert len(list_conditions(app)) == MAX_CONDITIONS


async def test_second_condition_switches_to_mode_b(alert_app):
    app, pilot = alert_app
    await add_condition(pilot, "200", operator="Greater than", timeframe="15m")

    assert app.screen.query_one("#condition-inline").display is False
    assert app.screen.query_one("#condition-list", ConditionList).display is True
    assert len(list_conditions(app)) == 2


async def test_delete_down_to_one_restores_mode_a(alert_app):
    app, pilot = alert_app
    app.screen.query_one("#value", Input).value = "100"
    await pilot.pause()
    await add_condition(pilot, "200", timeframe="15m")
    await add_condition(pilot, "300", timeframe="1h")

    condition_list = app.screen.query_one("#condition-list", ConditionList)
    expected = len(list_conditions(app))
    for _ in range(2):
        condition_id = list(condition_list.conditions)[-1].id
        app.screen.query_one(f"#remove-{condition_id}", Button).press()
        expected -= 1
        assert await wait_until(pilot, lambda: len(list_conditions(app)) == expected)

    assert len(list_conditions(app)) == 1
    assert app.screen.query_one("#condition-inline").display is True
    assert app.screen.query_one("#condition-list", ConditionList).display is False
    # surviving condition hydrated into the inline form, state preserved
    assert app.screen.query_one("#value", Input).value == "100.00"


async def test_preview_opens_prefilled_editor_and_updates_in_place(alert_app):
    app, pilot = alert_app
    app.screen.query_one("#value", Input).value = "100"
    await pilot.pause()
    await add_condition(pilot, "200", operator="Greater than", timeframe="15m")

    condition_list = app.screen.query_one("#condition-list", ConditionList)
    order = [c.id for c in condition_list.conditions]
    original = list(condition_list.conditions)[1]

    app.screen.query_one(f"#preview-{original.id}", Button).press()
    assert await wait_until(pilot, lambda: isinstance(app.screen, ConditionEditorScreen))

    editor = app.screen
    assert editor.query_one("#value", Input).value.replace(",", "") == "200.00"
    editor.query_one("#value", Input).value = "250"
    await pilot.pause()
    await pilot.press("ctrl+s")
    assert await wait_until(pilot, lambda: isinstance(app.screen, AlertScreen))

    updated = list(condition_list.conditions)[1]
    assert updated.id == original.id
    assert updated.value == 250.0
    assert [c.id for c in condition_list.conditions] == order


async def test_editor_delete_removes_condition(alert_app):
    app, pilot = alert_app
    await add_condition(pilot, "200")
    condition_list = app.screen.query_one("#condition-list", ConditionList)
    target = list(condition_list.conditions)[1]

    app.screen.query_one(f"#preview-{target.id}", Button).press()
    assert await wait_until(pilot, lambda: isinstance(app.screen, ConditionEditorScreen))
    app.screen.query_one("#editor-delete", Button).press()

    assert await wait_until(pilot, lambda: isinstance(app.screen, AlertScreen))
    assert await wait_until(pilot, lambda: len(list_conditions(app)) == 1)
    assert app.screen.query_one("#condition-inline").display is True


async def test_invalid_value_rejected(alert_app):
    app, pilot = alert_app
    alert = app.screen
    await pilot.press("ctrl+n")
    assert await wait_until(pilot, lambda: isinstance(app.screen, ConditionEditorScreen))
    editor = app.screen
    editor.query_one("#value", Input).value = "0"
    await pilot.pause()
    await pilot.press("ctrl+s")
    await pilot.pause()
    assert isinstance(app.screen, ConditionEditorScreen)  # stayed open
    assert list(alert.query_one("#condition-list", ConditionList).conditions) == []


async def test_create_returns_spec_with_conditions(alert_app):
    app, pilot = alert_app
    app.screen.query_one("#value", Input).value = "100"
    await pilot.pause()
    await add_condition(pilot, "200", operator="Greater than", timeframe="15m")

    await pilot.press("ctrl+s")
    assert await wait_until(pilot, lambda: app.result is not None)

    spec = app.result
    assert spec is not None
    assert spec.symbol == "BTCUSDT"
    assert len(spec.conditions) == 2
    assert spec.conditions[0].value == 100.0
    assert spec.conditions[1].timeframe == "15m"


async def test_single_condition_is_list_of_one(alert_app):
    app, pilot = alert_app
    app.screen.query_one("#value", Input).value = "42"
    await pilot.pause()
    await pilot.press("ctrl+s")
    assert await wait_until(pilot, lambda: app.result is not None)
    assert app.result is not None
    assert len(app.result.conditions) == 1


async def test_symbol_change_updates_default_message(alert_app):
    app, pilot = alert_app
    app.screen.query_one("#symbol", Input).value = "ETH-USD"
    await pilot.pause()
    label = app.screen.query_one("#message", Button).label.plain
    assert label == "ETH-USD Price Crossing 0.00 >"


async def test_message_stops_regenerating_after_manual_edit(alert_app):
    app, pilot = alert_app
    app.screen._handle_message("custom {{ticker}} text")
    app.screen.query_one("#value", Input).value = "200"
    await pilot.pause()
    assert app.screen.query_one("#message", Button).label.plain == "custom {{ticker}} text >"


async def test_and_separators_and_timeframe_hint(alert_app):
    app, pilot = alert_app
    await add_condition(pilot, "200", timeframe="15m")
    await add_condition(pilot, "300", timeframe="1h")

    assert await wait_until(pilot, lambda: len(app.screen.query(".and-sep")) == 2)
    hint = app.screen.query_one("#timeframe-hint", Static)
    assert hint.display is True
    assert "Checks every 1m (smallest timeframe)" in str(hint.render())
