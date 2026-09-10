"""TUI tests using Textual's pilot — no arbitrary sleeps."""

from __future__ import annotations

import pytest
from rich.text import Text
from textual.widgets import Button, Checkbox, DataTable, Input, Label, Static

from tui_client.api import AlertView, ApiError, CandleView, QuoteView
from tui_client.app import AlertsApp
from tui_client.screens.alert_list import AlertListScreen
from tui_client.screens.create_alert import CreateAlertModal
from tui_client.screens.prices import DEFAULT_WATCHLIST, PricesScreen


class FakeApi:
    def __init__(self, alerts: list[AlertView] | None = None) -> None:
        self.alerts = list(alerts or [])
        self.created: list[dict] = []
        self.deleted: list[str] = []
        self.enabled: list[str] = []
        self.disabled: list[str] = []
        self.list_calls = 0
        self.fail_create: str | None = None

    async def list_alerts(self) -> list[AlertView]:
        self.list_calls += 1
        return list(self.alerts)

    async def create_alert(self, payload: dict) -> AlertView:
        if self.fail_create:
            raise ApiError(self.fail_create, 422)
        alert = AlertView(
            id=f"a{len(self.created)}",
            symbol=payload["symbol"],
            status="ACTIVE",
            conditions=payload["conditions"],
            message=payload.get("message", ""),
        )
        self.created.append(payload)
        self.alerts.append(alert)
        return alert

    async def delete_alert(self, alert_id: str) -> None:
        self.deleted.append(alert_id)
        self.alerts = [a for a in self.alerts if a.id != alert_id]

    async def enable_alert(self, alert_id: str) -> AlertView:
        self.enabled.append(alert_id)
        return self.alerts[0]

    async def disable_alert(self, alert_id: str) -> AlertView:
        self.disabled.append(alert_id)
        return self.alerts[0]

    async def get_quotes(self, symbols: list[str]) -> list[QuoteView]:
        return [
            QuoteView(symbol=s, price=100.0, change_24h=1.5 if s != "NVDA" else -2.5)
            for s in symbols
        ]

    async def get_last_candle(self, symbol: str) -> CandleView | None:
        return CandleView(open=100.0, high=105.0, low=95.0, close=102.0)

    async def get_screeners(self, scr_id: str, count: int = 5) -> list[QuoteView]:
        self.screener_calls = getattr(self, "screener_calls", [])
        self.screener_calls.append(scr_id)
        return [
            QuoteView(
                symbol=f"{scr_id}-{i}",
                price=float(200 + i),
                change_24h=0.5 + 0.01 * i,
                name=f"Company {i}",
                volume=1_000.0 * i,
                market_cap=1e9 * i,
            )
            for i in range(count)
        ]

    async def search_screeners(self, filters: dict, size: int = 50, offset: int = 0, sort: str = "marketcap"):
        from tui_client.api import ScreenerResultView

        self.screener_search = getattr(self, "screener_search", [])
        self.screener_search.append({"filters": filters, "size": size, "sort": sort})
        quotes = [
            QuoteView(symbol=f"F{i}", price=float(i), change_24h=0.1 * i)
            for i in range(min(size, 3))
        ]
        return ScreenerResultView(total=20047, quotes=quotes)


def sample_alert(symbol: str, status: str = "ACTIVE") -> AlertView:
    return AlertView(
        id=f"id-{symbol}",
        symbol=symbol,
        status=status,
        conditions=[{"operator": "crossing", "value": 3794.94}],
        message=f"{symbol} Crossing 3794.94",
    )


async def wait_until(pilot, condition, tries: int = 200) -> bool:
    for _ in range(tries):
        if condition():
            return True
        await pilot.pause()
    return condition()


def table_rows(app) -> int:
    return len(app.screen.query_one("#alerts-table", DataTable).rows)


def plain(cell: str) -> str:
    return Text.from_markup(cell).plain


def modal_open(app) -> bool:
    return isinstance(app.screen, CreateAlertModal)


def error_text(modal: CreateAlertModal) -> str:
    return str(modal.query_one("#error", Label).render())


def open_modal(pilot) -> CreateAlertModal:
    return pilot.app.screen  # modal is the top screen


@pytest.fixture
async def pilot_app():
    api = FakeApi(
        [sample_alert("ETHUSDT"), sample_alert("BTCUSDT")]
    )
    app = AlertsApp(api=api, default_symbol="BTCUSDT")
    async with app.run_test() as pilot:
        # main screen is Prices; navigate to alerts for alert-focused tests
        for _ in range(200):
            if isinstance(app.screen, AlertListScreen):
                break
            await pilot.press("a")
            await pilot.pause()
        yield app, pilot, api


@pytest.fixture
async def prices_app():
    api = FakeApi([sample_alert("ETHUSDT")])
    app = AlertsApp(api=api, default_symbol="BTCUSDT")
    async with app.run_test() as pilot:
        yield app, pilot, api


async def test_list_displays_alerts(pilot_app):
    app, pilot, api = pilot_app
    assert await wait_until(pilot, lambda: table_rows(app) == 2)
    table = app.screen.query_one("#alerts-table", DataTable)
    assert plain(table.get_row_at(0)[0]) == "ETHUSDT"
    assert "Crossing" in table.get_row_at(0)
    assert plain(table.get_row_at(1)[3]) == "ACTIVE"


async def test_open_modal_and_cancel_with_escape(pilot_app):
    app, pilot, _ = pilot_app
    await pilot.press("n")
    assert await wait_until(pilot, lambda: modal_open(app))
    await pilot.press("escape")
    assert await wait_until(pilot, lambda: not modal_open(app))


async def test_create_alert_full_flow(pilot_app):
    app, pilot, api = pilot_app
    await pilot.press("n")
    assert await wait_until(pilot, lambda: modal_open(app))
    modal = open_modal(pilot)

    modal.query_one("#symbol", Input).value = "ETHUSDT"
    modal.query_one("#val-0", Input).value = "4000"
    modal.query_one("#expiry", Input).value = "2099-01-01T00:00:00Z"
    modal.query_one("#message", Input).value = "To the moon"
    modal.query_one("#ch-toast", Checkbox).value = True

    modal.query_one("#create", Button).press()
    assert await wait_until(pilot, lambda: len(api.created) == 1)
    assert await wait_until(pilot, lambda: not modal_open(app))

    payload = api.created[0]
    assert payload["symbol"] == "ETHUSDT"
    assert payload["conditions"] == [{"metric": "price", "operator": "crossing", "value": 4000.0}]
    assert payload["trigger_mode"] == "ONCE"
    assert payload["notification_channels"] == ["in_app", "toast"]
    assert payload["message"] == "To the moon"
    assert await wait_until(pilot, lambda: table_rows(app) == 3)  # 2 original + 1 new


async def test_add_second_condition(pilot_app):
    app, pilot, api = pilot_app
    await pilot.press("n")
    assert await wait_until(pilot, lambda: modal_open(app))
    modal = open_modal(pilot)

    modal.query_one("#add-condition", Button).press()
    assert await wait_until(pilot, lambda: modal.query("#val-1"))

    modal.query_one("#symbol", Input).value = "BTCUSDT"
    modal.query_one("#val-0", Input).value = "100000"
    modal.query_one("#val-1", Input).value = "90000"
    modal.query_one("#expiry", Input).value = "2099-01-01T00:00:00Z"
    modal.query_one("#create", Button).press()

    assert await wait_until(pilot, lambda: len(api.created) == 1)
    assert len(api.created[0]["conditions"]) == 2


async def test_validation_errors_displayed(pilot_app):
    app, pilot, api = pilot_app
    await pilot.press("n")
    assert await wait_until(pilot, lambda: modal_open(app))
    modal = open_modal(pilot)

    modal.query_one("#symbol", Input).value = "ETHUSDT"
    # empty value -> number parse error
    modal.query_one("#create", Button).press()
    assert await wait_until(pilot, lambda: "must be a number" in error_text(modal))
    assert api.created == []

    # non-positive value
    modal.query_one("#val-0", Input).value = "0"
    modal.query_one("#create", Button).press()
    assert await wait_until(
        pilot, lambda: "greater than 0" in error_text(modal)
    )

    # no notification channels
    modal.query_one("#val-0", Input).value = "100"
    modal.query_one("#ch-in_app", Checkbox).value = False
    modal.query_one("#create", Button).press()
    assert await wait_until(
        pilot, lambda: "notification channel" in error_text(modal)
    )
    modal.query_one("#ch-in_app", Checkbox).value = True

    # past expiration
    modal.query_one("#expiry", Input).value = "2020-01-01T00:00:00Z"
    modal.query_one("#create", Button).press()
    assert await wait_until(
        pilot, lambda: "Expiration must be in the future" in error_text(modal)
    )
    assert api.created == []


async def test_api_error_surfaces_in_modal(pilot_app):
    app, pilot, api = pilot_app
    api.fail_create = "Unknown notification channel(s): slack"
    await pilot.press("n")
    assert await wait_until(pilot, lambda: modal_open(app))
    modal = open_modal(pilot)
    modal.query_one("#val-0", Input).value = "100"
    modal.query_one("#expiry", Input).value = "2099-01-01T00:00:00Z"
    modal.query_one("#create", Button).press()
    assert await wait_until(
        pilot, lambda: "slack" in error_text(modal)
    )
    assert modal_open(app)  # modal stays open


async def test_enable_disable_delete_actions(pilot_app):
    app, pilot, api = pilot_app
    assert await wait_until(pilot, lambda: table_rows(app) == 2)

    await pilot.press("d")
    assert await wait_until(pilot, lambda: len(api.disabled) == 1)
    assert await wait_until(pilot, lambda: table_rows(app) == 2)

    await pilot.press("e")
    assert await wait_until(pilot, lambda: len(api.enabled) == 1)

    await pilot.press("x")
    assert await wait_until(pilot, lambda: len(api.deleted) == 1)
    assert await wait_until(pilot, lambda: table_rows(app) == 1)


async def test_main_screen_shows_prices(prices_app):
    app, pilot, _ = prices_app
    assert isinstance(app.screen, PricesScreen)
    prices = app.screen.query_one("#prices-table", DataTable)
    assert await wait_until(pilot, lambda: len(prices.rows) == 25)  # screener count
    mode = app.screen.query_one("#mode-label", Static)
    assert "Top (most active)" in str(mode.render())


async def test_prices_watchlist_shows_colored_change(prices_app):
    app, pilot, _ = prices_app
    await pilot.press("w")  # personal watchlist mode
    prices = app.screen.query_one("#prices-table", DataTable)
    assert await wait_until(pilot, lambda: len(prices.rows) == len(DEFAULT_WATCHLIST))
    assert prices.row_count == len(DEFAULT_WATCHLIST)
    # NVDA is -2.5 (red), others +1.5 (green)
    nvda = next(q for q in app.screen._quotes if q.symbol == "NVDA")
    assert nvda.change_24h == -2.5
    assert nvda.change_text() == "-2.50%"
    eth = next(q for q in app.screen._quotes if q.symbol == "ETH-USD")
    assert eth.change_text() == "+1.50%"
    # cells carry color markup: red for negative, green for positive
    rows = [prices.get_row_at(i) for i in range(prices.row_count)]
    nvda_cell = next(r[3] for r in rows if plain(r[0]) == "NVDA")
    assert nvda_cell == "[red]-2.50%[/]"
    eth_cell = next(r[3] for r in rows if plain(r[0]) == "ETH-USD")
    assert eth_cell == "[green]+1.50%[/]"


async def test_screener_modes_toggle(prices_app):
    app, pilot, api = prices_app
    prices = app.screen.query_one("#prices-table", DataTable)
    # default: most_actives screener
    assert await wait_until(pilot, lambda: len(prices.rows) == 25)
    assert api.screener_calls[-1] == "most_actives"
    assert plain(prices.get_row_at(0)[0]) == "most_actives-0"

    await pilot.press("g")
    assert await wait_until(pilot, lambda: api.screener_calls[-1] == "gainers")
    assert plain(prices.get_row_at(0)[0]) == "gainers-0"

    await pilot.press("l")
    assert await wait_until(pilot, lambda: api.screener_calls[-1] == "losers")
    assert plain(prices.get_row_at(0)[0]) == "losers-0"

    await pilot.press("w")
    assert await wait_until(pilot, lambda: len(prices.rows) == len(DEFAULT_WATCHLIST))
    assert plain(prices.get_row_at(0)[0]) == "BTC-USD"


async def test_screener_custom_mode(prices_app):
    app, pilot, api = prices_app
    prices = app.screen.query_one("#prices-table", DataTable)
    assert await wait_until(pilot, lambda: len(prices.rows) == 25)

    await pilot.press("s")
    filter_input = app.screen.query_one("#filter", Input)
    assert await wait_until(pilot, lambda: filter_input is not None)
    filter_input.value = "sector:technology mincap:1b sort:percentchange"
    await pilot.press("enter")
    assert await wait_until(pilot, lambda: getattr(api, "screener_search", []) != [])
    search = api.screener_search[-1]
    assert search["filters"] == {"region": "us", "sector": "technology", "mincap": 1000000000.0}
    assert search["sort"] == "percentchange"
    assert plain(prices.get_row_at(0)[0]) == "F0"
    mode = app.screen.query_one("#mode-label", Static)
    assert "20,047" in str(mode.render())


async def test_symbol_search_filters_rows(prices_app):
    app, pilot, _ = prices_app
    prices = app.screen.query_one("#prices-table", DataTable)
    assert await wait_until(pilot, lambda: len(prices.rows) == 25)
    await pilot.press("/")
    search = app.screen.query_one("#search", Input)
    assert await wait_until(pilot, lambda: search.has_focus)
    await pilot.press("m", "o", "s", "t", "_", "a", "c", "t", "i", "v", "e", "s", "-", "1")
    assert await wait_until(pilot, lambda: plain(prices.get_row_at(0)[0]) == "most_actives-1")
    mode = app.screen.query_one("#mode-label", Static)
    assert "1/5" in str(mode.render())  # 111 matches -> 5 pages
    await pilot.press("ctrl+a", "backspace")
    assert await wait_until(pilot, lambda: len(prices.rows) == 25)


async def test_screener_sort_by_price(prices_app):
    app, pilot, _ = prices_app
    prices = app.screen.query_one("#prices-table", DataTable)
    assert await wait_until(pilot, lambda: len(prices.rows) == 25)  # first page of 250
    # price desc on first press (biggest first)
    await pilot.press("2")
    assert await wait_until(pilot, lambda: plain(prices.get_row_at(0)[0]) == "most_actives-249")
    # press again -> ascending
    await pilot.press("2")
    assert await wait_until(pilot, lambda: plain(prices.get_row_at(0)[0]) == "most_actives-0")
    mode = app.screen.query_one("#mode-label", Static)
    assert "Price ▲" in str(mode.render())


async def test_screener_pagination(prices_app):
    app, pilot, _ = prices_app
    prices = app.screen.query_one("#prices-table", DataTable)
    assert await wait_until(pilot, lambda: len(prices.rows) == 25)
    await pilot.press("]")
    assert await wait_until(pilot, lambda: plain(prices.get_row_at(0)[0]) == "most_actives-25")
    mode = app.screen.query_one("#mode-label", Static)
    assert "2/10" in str(mode.render())
    await pilot.press("[")
    assert await wait_until(pilot, lambda: plain(prices.get_row_at(0)[0]) == "most_actives-0")
    assert "1/10" in str(mode.render())


async def test_screener_extra_columns(prices_app):
    app, pilot, _ = prices_app
    prices = app.screen.query_one("#prices-table", DataTable)
    assert await wait_until(pilot, lambda: len(prices.rows) == 25)
    row = prices.get_row_at(0)
    assert row[1] == "Company 0"  # name
    assert row[5] == "0"          # volume 0 compacts to "0"
    assert len(prices.columns) == 8


async def test_prices_screen_shows_quotes(pilot_app):
    app, pilot, api = pilot_app
    assert await wait_until(pilot, lambda: table_rows(app) == 2)
    await pilot.press("p")
    await pilot.pause()
    assert isinstance(app.screen, PricesScreen)
    prices = app.screen.query_one("#prices-table", DataTable)
    assert await wait_until(pilot, lambda: len(prices.rows) == 25)
    assert api.screener_calls[-1] == "most_actives"
    await pilot.press("a")
    await pilot.pause()
    assert not isinstance(app.screen, PricesScreen)
    assert isinstance(app.screen, AlertListScreen)