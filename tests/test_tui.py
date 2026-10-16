"""TUI tests using Textual's pilot — no arbitrary sleeps."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from rich.text import Text
from textual.widgets import Button, DataTable, Input, Select, SelectionList, Static, Tabs

from tui_client.api import AlertView, ApiError, CandleView, QuoteView
from tui_client.alerts.screens import (
    AlertScreen,
    ConditionEditorScreen,
    ExpirationScreen,
    MessageScreen,
    NotificationsScreen,
)
from tui_client.app import AlertsApp
from tui_client.screens.alert_list import AlertListScreen
from tui_client.screens.prices import (
    DEFAULT_WATCHLIST,
    AddSymbolModal,
    ConfirmModal,
    NameModal,
    PricesScreen,
)
from tui_client.screens.settings import SettingsModal
from tui_client.screens.symbol_info import SymbolInfoScreen
from tui_client.themes import DANGER, SUCCESS
from tui_client.widgets import SymbolAutoComplete


class FakeApi:
    def __init__(self, alerts: list[AlertView] | None = None) -> None:
        self.alerts = list(alerts or [])
        self.created: list[dict] = []
        self.updated: list[tuple[str, dict]] = []
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

    async def update_alert(self, alert_id: str, payload: dict) -> AlertView:
        self.updated.append((alert_id, payload))
        alert = AlertView(
            id=alert_id,
            symbol=payload["symbol"],
            status="ACTIVE",
            conditions=payload["conditions"],
            message=payload.get("message", ""),
        )
        self.alerts = [alert if a.id == alert_id else a for a in self.alerts]
        return alert

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
        self._universe = [f"{scr_id}-{i}" for i in range(count)]
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

    async def search_symbols(self, query: str, limit: int = 10):
        from tui_client.api import SearchHitView

        universe = getattr(self, "_universe", [])
        matched = [s for s in universe if query in s.lower()]
        return [SearchHitView(symbol=s, name=s) for s in matched]

    async def search_screeners(self, filters: dict, size: int = 50, offset: int = 0, sort: str = "marketcap"):
        from tui_client.api import ScreenerResultView

        self.screener_search = getattr(self, "screener_search", [])
        self.screener_search.append({"filters": filters, "size": size, "sort": sort})
        self._universe = [f"F{i}" for i in range(size)]
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
    return isinstance(app.screen, AlertScreen)


def open_modal(pilot) -> AlertScreen:
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
    assert plain(table.get_row_at(0)[1]) == "$100.00"
    assert plain(table.get_row_at(0)[2]) == "▲ +1.50%"
    assert plain(table.get_row_at(0)[3]) == "Crossing"
    assert plain(table.get_row_at(1)[6]) == "ACTIVE"


async def test_list_shows_empty_hint_when_no_alerts():
    app = AlertsApp(api=FakeApi([]), default_symbol="BTCUSDT")
    async with app.run_test() as pilot:
        for _ in range(200):
            if isinstance(app.screen, AlertListScreen):
                break
            await pilot.press("a")
            await pilot.pause()
        hint = app.screen.query_one("#alerts-hint", Static)
        assert "No alerts yet" in str(hint.render())


async def test_open_modal_and_cancel_with_escape(pilot_app):
    app, pilot, _ = pilot_app
    await pilot.press("n")
    assert await wait_until(pilot, lambda: modal_open(app))
    await pilot.press("escape")
    assert await wait_until(pilot, lambda: not modal_open(app))


async def test_sub_screens_update_modal(pilot_app):
    app, pilot, api = pilot_app
    await pilot.press("n")
    assert await wait_until(pilot, lambda: modal_open(app))
    modal = open_modal(pilot)

    # Message sub-screen
    modal.query_one("#message", Button).press()
    assert await wait_until(pilot, lambda: isinstance(app.screen, MessageScreen))
    app.screen.query_one("#message-text").text = "{{ticker}} broke out"
    app.screen.query_one("#message-ok", Button).press()
    assert await wait_until(pilot, lambda: modal_open(app))
    assert modal.query_one("#message", Button).label.plain == "{{ticker}} broke out >"

    # Notifications sub-screen
    modal.query_one("#notifications", Button).press()
    assert await wait_until(pilot, lambda: isinstance(app.screen, NotificationsScreen))
    sel = app.screen.query_one("#notifications-list", SelectionList)
    sel.select("Email")
    sel.deselect("Sound")
    app.screen.query_one("#notifications-ok", Button).press()
    assert await wait_until(pilot, lambda: modal_open(app))
    assert modal.query_one("#notifications", Button).label.plain == "App, Toasts, Email >"

    # Expiration sub-screen
    modal.query_one("#expiration", Button).press()
    assert await wait_until(pilot, lambda: isinstance(app.screen, ExpirationScreen))
    app.screen.query_one("#expiration-ok", Button).press()
    assert await wait_until(pilot, lambda: modal_open(app))

    # payload reflects the edited message + notifications
    modal.query_one("#value", Input).value = "100"
    await pilot.pause()
    modal.query_one("#create", Button).press()
    assert await wait_until(pilot, lambda: len(api.created) == 1)
    assert api.created[0]["message"] == "{{ticker}} broke out"
    assert api.created[0]["notification_channels"] == ["in_app", "toast", "email"]


async def test_create_alert_full_flow(pilot_app):
    app, pilot, api = pilot_app
    await pilot.press("n")
    assert await wait_until(pilot, lambda: modal_open(app))
    modal = open_modal(pilot)

    modal.query_one("#symbol", Input).value = "ETH-USD"
    modal.query_one("#value", Input).value = "4000"
    await pilot.pause()
    assert modal.query_one("#message", Button).label.plain == "ETH-USD Price Crossing 4,000.00 >"

    modal.query_one("#create", Button).press()
    assert await wait_until(pilot, lambda: len(api.created) == 1)
    assert await wait_until(pilot, lambda: not modal_open(app))

    payload = api.created[0]
    assert payload["symbol"] == "ETH-USD"
    assert payload["conditions"] == [{"metric": "price", "operator": "crossing", "value": 4000.0}]
    assert payload["trigger_mode"] == "ONCE"
    assert payload["notification_channels"] == ["in_app", "toast", "sound"]
    assert payload["message"] == "ETH-USD Price Crossing 4,000.00"
    assert await wait_until(pilot, lambda: table_rows(app) == 3)  # 2 original + 1 new


async def test_create_alert_symbol_autocomplete(pilot_app):
    app, pilot, _ = pilot_app
    await pilot.press("n")
    assert await wait_until(pilot, lambda: modal_open(app))
    modal = open_modal(pilot)
    symbol = modal.query_one("#symbol", Input)
    symbol.focus()
    symbol.value = ""
    await pilot.pause()
    autocomplete = modal.query_one(SymbolAutoComplete)
    # Watchlist symbols seed the list, so focusing shows suggestions before typing.
    assert await wait_until(
        pilot,
        lambda: autocomplete.display and autocomplete.option_list.option_count > 0,
    )
    await pilot.press("e", "t", "h")
    assert await wait_until(
        pilot,
        lambda: autocomplete.display and autocomplete.option_list.option_count > 0,
    )
    await pilot.press("enter")
    assert await wait_until(pilot, lambda: symbol.value == "ETH-USD")
    assert await wait_until(pilot, lambda: not autocomplete.display)
    assert modal.query_one("#message", Button).label.plain == "ETH-USD Price Crossing 0.00 >"


async def test_create_alert_symbol_search_error_keeps_modal(pilot_app):
    app, pilot, api = pilot_app

    async def boom(query: str, limit: int = 10):
        raise RuntimeError("search endpoint exploded")

    api.search_symbols = boom
    await pilot.press("n")
    assert await wait_until(pilot, lambda: modal_open(app))
    modal = open_modal(pilot)
    symbol = modal.query_one("#symbol", Input)
    symbol.focus()
    symbol.value = ""
    await pilot.pause()
    await pilot.press("e", "t", "h")
    await pilot.pause()
    assert modal_open(app)
    assert symbol.value == "eth"


async def test_message_auto_updates_until_edited(pilot_app):
    app, pilot, _ = pilot_app
    await pilot.press("n")
    assert await wait_until(pilot, lambda: modal_open(app))
    modal = open_modal(pilot)

    modal.query_one("#operator", Select).value = "Greater than"
    modal.query_one("#value", Input).value = "100"
    await pilot.pause()
    assert modal.query_one("#message", Button).label.plain == "BTCUSDT Price Greater than 100.00 >"

    # user edit wins — later changes no longer regenerate the message
    modal._handle_message("custom {{ticker}} text")
    modal.query_one("#value", Input).value = "200"
    await pilot.pause()
    assert modal.query_one("#message", Button).label.plain == "custom {{ticker}} text >"


async def test_create_alert_focuses_symbol_and_clears_value(pilot_app):
    app, pilot, _ = pilot_app
    await pilot.press("n")
    assert await wait_until(pilot, lambda: modal_open(app))
    modal = open_modal(pilot)
    symbol = modal.query_one("#symbol", Input)
    value = modal.query_one("#value", Input)

    assert await wait_until(pilot, lambda: symbol.has_focus)
    assert value.value == "0.00"

    value.focus()
    await pilot.pause()
    assert value.value == ""


async def test_edit_refreshes_placeholder_message(pilot_app):
    app, pilot, _ = pilot_app
    assert await wait_until(pilot, lambda: table_rows(app) == 2)
    table = app.screen.query_one("#alerts-table", DataTable)
    table.move_cursor(row=0)  # ETHUSDT, message "ETHUSDT Crossing 3794.94"
    await pilot.pause()
    await pilot.press("enter")
    assert await wait_until(pilot, lambda: isinstance(app.screen, AlertScreen))
    modal = app.screen
    assert await wait_until(pilot, lambda: bool(modal.query("#value")))

    # auto-generated message follows the edited value
    modal.query_one("#value", Input).value = "250"
    await pilot.pause()
    assert modal.query_one("#message", Button).label.plain == (
        "ETHUSDT Price Crossing 250.00 >"
    )

    # a user-written message stays untouched
    modal._handle_message("my custom alert")
    modal.query_one("#value", Input).value = "300"
    await pilot.pause()
    assert modal.query_one("#message", Button).label.plain == "my custom alert >"


async def test_add_second_condition(pilot_app):
    app, pilot, api = pilot_app
    await pilot.press("n")
    assert await wait_until(pilot, lambda: modal_open(app))
    modal = open_modal(pilot)

    modal.query_one("#value", Input).value = "100000"
    await pilot.pause()
    await pilot.press("ctrl+n")
    assert await wait_until(pilot, lambda: isinstance(app.screen, ConditionEditorScreen))
    app.screen.query_one("#value", Input).value = "90000"
    await pilot.pause()
    await pilot.press("ctrl+s")
    assert await wait_until(pilot, lambda: isinstance(app.screen, AlertScreen))

    modal.query_one("#create", Button).press()

    assert await wait_until(pilot, lambda: len(api.created) == 1)
    assert len(api.created[0]["conditions"]) == 2


async def test_validation_errors_keep_modal_open(pilot_app):
    app, pilot, api = pilot_app
    await pilot.press("n")
    assert await wait_until(pilot, lambda: modal_open(app))
    modal = open_modal(pilot)

    # empty value -> number parse error
    modal.query_one("#value", Input).value = ""
    await pilot.pause()
    modal.query_one("#create", Button).press()
    await pilot.pause()
    assert api.created == []
    assert modal_open(app)

    # non-positive value
    modal.query_one("#value", Input).value = "0"
    await pilot.pause()
    modal.query_one("#create", Button).press()
    await pilot.pause()
    assert api.created == []
    assert modal_open(app)

    # no notification channels
    modal.query_one("#value", Input).value = "100"
    await pilot.pause()
    modal.query_one("#notifications", Button).press()
    assert await wait_until(pilot, lambda: isinstance(app.screen, NotificationsScreen))
    app.screen.query_one("#notifications-list", SelectionList).deselect_all()
    app.screen.query_one("#notifications-ok", Button).press()
    assert await wait_until(pilot, lambda: modal_open(app))
    modal.query_one("#create", Button).press()
    await pilot.pause()
    assert api.created == []
    assert modal_open(app)

    # past expiration
    modal._notifications = ["App"]
    modal._expires_at = datetime.now().astimezone() - timedelta(days=1)
    modal.query_one("#create", Button).press()
    await pilot.pause()
    assert api.created == []
    assert modal_open(app)


async def test_api_error_surfaces(pilot_app):
    app, pilot, api = pilot_app
    api.fail_create = "Unknown notification channel(s): slack"
    await pilot.press("n")
    assert await wait_until(pilot, lambda: modal_open(app))
    modal = open_modal(pilot)
    modal.query_one("#value", Input).value = "100"
    modal.query_one("#create", Button).press()
    assert await wait_until(pilot, lambda: not modal_open(app))
    assert api.created == []
    assert table_rows(app) == 2  # list unchanged


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
    assert nvda_cell == f"[{DANGER}]▼ -2.50%[/]"
    eth_cell = next(r[3] for r in rows if plain(r[0]) == "ETH-USD")
    assert eth_cell == f"[{SUCCESS}]▲ +1.50%[/]"


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
    assert app.focused is app.screen.query_one("#prices-table", DataTable)
    await pilot.press("/")
    assert app.focused is filter_input
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


async def test_tab_cycles_top_level_tabs_and_alerts(prices_app):
    app, pilot, _ = prices_app
    prices = app.screen.query_one("#prices-table", DataTable)
    assert await wait_until(pilot, lambda: len(prices.rows) == 25)

    for expected in ("g", "l", "w", "s"):
        await pilot.press("tab")
        assert await wait_until(pilot, lambda: app.screen.mode == expected)

    await pilot.press("tab")
    assert await wait_until(pilot, lambda: isinstance(app.screen, AlertListScreen))

    await pilot.press("tab")
    assert await wait_until(pilot, lambda: isinstance(app.screen, PricesScreen))
    assert app.screen.mode == "t"
    tabs = app.screen.query_one("#mode-tabs", Tabs)
    assert tabs.active == "t"
    label = app.screen.query_one("#mode-label", Static)
    assert "Top" in str(label.render())


async def test_alerts_tab_stays_active_after_markets_tab(prices_app):
    app, pilot, _ = prices_app
    prices = app.screen.query_one("#prices-table", DataTable)
    assert await wait_until(pilot, lambda: len(prices.rows) == 25)

    await pilot.press("a")
    assert await wait_until(pilot, lambda: isinstance(app.screen, AlertListScreen))

    # Activating a markets tab while Alerts is mounted navigates to Prices...
    app.screen.query_one("#mode-tabs", Tabs).active = "t"
    assert await wait_until(pilot, lambda: isinstance(app.screen, PricesScreen))

    # ...and returning to Alerts must re-arm the Alerts tab, not the stale one.
    await pilot.press("a")
    assert await wait_until(pilot, lambda: isinstance(app.screen, AlertListScreen))
    assert app.screen.query_one("#mode-tabs", Tabs).active == "a"


async def test_ctrl_right_cycles_watchlists():
    from tui_client.settings import UserSettings

    user = UserSettings()
    user.watchlist.mode = "multiple"
    user.watchlist.watchlists = {"default": ["BTC-USD"], "crypto": ["ETH-USD"]}
    app = AlertsApp(api=FakeApi([sample_alert("ETHUSDT")]), user=user)
    async with app.run_test() as pilot:
        await pilot.press("w")
        assert await wait_until(pilot, lambda: app.screen.active_watchlist == "default")
        await pilot.press("ctrl+right")
        assert await wait_until(pilot, lambda: app.screen.active_watchlist == "crypto")


async def test_watchlist_add_symbol(monkeypatch):
    from tui_client.settings import UserSettings

    monkeypatch.setattr("tui_client.app.save_settings", lambda *a, **k: None)
    user = UserSettings()
    user.watchlist.mode = "multiple"
    user.watchlist.watchlists = {"default": ["BTC-USD", "ETH-USD"], "crypto": ["SOL-USD"]}
    app = AlertsApp(api=FakeApi(), user=user)
    async with app.run_test() as pilot:
        await pilot.press("w")
        screen = app.screen
        prices = screen.query_one("#prices-table", DataTable)
        assert await wait_until(pilot, lambda: len(prices.rows) == 2)

        await pilot.press("plus")
        assert await wait_until(pilot, lambda: isinstance(app.screen, AddSymbolModal))
        app.screen.query_one("#wl-symbol", Input).value = "msft"
        app.screen.query_one("#wl-target", Select).value = "crypto"
        await pilot.pause()
        app.screen.query_one("#add", Button).press()

        assert await wait_until(pilot, lambda: "MSFT" in user.watchlist.watchlists["crypto"])
        assert user.watchlist.watchlists["crypto"] == ["SOL-USD", "MSFT"]
        assert user.watchlist.watchlists["default"] == ["BTC-USD", "ETH-USD"]


async def test_watchlist_add_uses_active_by_default(monkeypatch):
    from tui_client.settings import UserSettings

    monkeypatch.setattr("tui_client.app.save_settings", lambda *a, **k: None)
    user = UserSettings()
    user.watchlist.mode = "multiple"
    user.watchlist.watchlists = {"default": ["BTC-USD", "ETH-USD"], "crypto": ["SOL-USD"]}
    app = AlertsApp(api=FakeApi(), user=user)
    async with app.run_test() as pilot:
        await pilot.press("w")
        screen = app.screen
        prices = screen.query_one("#prices-table", DataTable)
        assert await wait_until(pilot, lambda: len(prices.rows) == 2)

        await pilot.press("plus")
        assert await wait_until(pilot, lambda: isinstance(app.screen, AddSymbolModal))
        app.screen.query_one("#wl-symbol", Input).value = "msft"
        await pilot.pause()
        app.screen.query_one("#add", Button).press()

        assert await wait_until(pilot, lambda: "MSFT" in screen.watchlist)
        assert user.watchlist.watchlists["default"] == ["BTC-USD", "ETH-USD", "MSFT"]
        assert await wait_until(pilot, lambda: len(prices.rows) == 3)


async def test_watchlist_new_and_delete(monkeypatch):
    from tui_client.settings import UserSettings

    monkeypatch.setattr("tui_client.app.save_settings", lambda *a, **k: None)
    user = UserSettings()
    user.watchlist.mode = "multiple"
    user.watchlist.watchlists = {"default": ["BTC-USD"]}
    app = AlertsApp(api=FakeApi(), user=user)
    async with app.run_test() as pilot:
        await pilot.press("w")
        screen = app.screen
        assert await wait_until(pilot, lambda: screen.active_watchlist == "default")

        # create
        await pilot.press("n")
        assert await wait_until(pilot, lambda: isinstance(app.screen, NameModal))
        app.screen.query_one("#wl-name", Input).value = "crypto"
        app.screen.query_one("#create", Button).press()
        assert await wait_until(pilot, lambda: screen.active_watchlist == "crypto")
        assert "crypto" in user.watchlist.watchlists

        # delete
        await pilot.press("D")
        assert await wait_until(pilot, lambda: isinstance(app.screen, ConfirmModal))
        app.screen.query_one("#confirm", Button).press()
        assert await wait_until(pilot, lambda: "crypto" not in screen.watchlists)
        assert "crypto" not in user.watchlist.watchlists
        assert screen.active_watchlist == "default"


async def test_alert_creation_after_deleting_active_watchlist(monkeypatch):
    """Deleting the active list must not break alert creation (dangling active)."""
    from tui_client.settings import UserSettings

    monkeypatch.setattr("tui_client.app.save_settings", lambda *a, **k: None)
    user = UserSettings()
    user.watchlist.mode = "multiple"
    user.watchlist.watchlists = {"default": ["BTC-USD"], "crypto": ["ETH-USD"]}
    app = AlertsApp(api=FakeApi(), user=user)
    async with app.run_test() as pilot:
        await pilot.press("w")
        screen = app.screen
        await pilot.press("ctrl+right")
        assert await wait_until(pilot, lambda: screen.active_watchlist == "crypto")

        await pilot.press("D")
        assert await wait_until(pilot, lambda: isinstance(app.screen, ConfirmModal))
        app.screen.query_one("#confirm", Button).press()
        assert await wait_until(pilot, lambda: "crypto" not in user.watchlist.watchlists)

        # the active pointer must still resolve
        assert user.watchlist.active_symbols() == ["BTC-USD"]

        # and the create-alert modal must open and build a payload
        await pilot.press("a")
        assert await wait_until(pilot, lambda: isinstance(app.screen, AlertListScreen))
        await pilot.press("n")
        assert await wait_until(pilot, lambda: isinstance(app.screen, AlertScreen))
        app.screen.query_one("#symbol", Input).value = "BTCUSDT"
        app.screen.query_one("#value", Input).value = "50000"
        await pilot.pause()
        app.screen.action_create()
        await pilot.pause()
        assert await wait_until(pilot, lambda: bool(app.api.created))


async def test_watchlist_rename(monkeypatch):
    from tui_client.settings import UserSettings

    monkeypatch.setattr("tui_client.app.save_settings", lambda *a, **k: None)
    user = UserSettings()
    user.watchlist.mode = "multiple"
    user.watchlist.watchlists = {"default": ["BTC-USD"], "crypto": ["ETH-USD"]}
    app = AlertsApp(api=FakeApi(), user=user)
    async with app.run_test() as pilot:
        await pilot.press("w")
        screen = app.screen
        assert await wait_until(pilot, lambda: screen.active_watchlist == "default")

        await pilot.press("ctrl+right")
        assert await wait_until(pilot, lambda: screen.active_watchlist == "crypto")

        await pilot.press("e")
        assert await wait_until(pilot, lambda: isinstance(app.screen, NameModal))
        app.screen.query_one("#wl-name", Input).value = "alts"
        app.screen.query_one("#create", Button).press()

        assert await wait_until(pilot, lambda: screen.active_watchlist == "alts")
        assert "alts" in user.watchlist.watchlists
        assert "crypto" not in user.watchlist.watchlists
        assert user.watchlist.watchlists["alts"] == ["ETH-USD"]


async def test_watchlist_remove_from_other_list(monkeypatch):
    from tui_client.settings import UserSettings

    monkeypatch.setattr("tui_client.app.save_settings", lambda *a, **k: None)
    user = UserSettings()
    user.watchlist.mode = "multiple"
    user.watchlist.watchlists = {"default": ["BTC-USD"], "crypto": ["ETH-USD"]}
    app = AlertsApp(api=FakeApi(), user=user)
    async with app.run_test() as pilot:
        await pilot.press("w")
        screen = app.screen
        prices = screen.query_one("#prices-table", DataTable)
        assert await wait_until(pilot, lambda: len(prices.rows) == 1)

        # search shows a symbol that lives on another list
        api = app.api
        api._universe = ["ETH-USD"]
        search = screen.query_one("#search", Input)
        search.value = "ETH-USD"
        assert await wait_until(pilot, lambda: any(q.symbol == "ETH-USD" for q in screen._quotes))
        prices.move_cursor(row=0)
        await pilot.pause()
        await pilot.press("x")

        assert await wait_until(pilot, lambda: "ETH-USD" not in screen.watchlists["crypto"])
        assert user.watchlist.watchlists["crypto"] == []


@pytest.mark.parametrize(
    "remove_key",
    ["x", "delete", "backspace", "ctrl+h", "minus", "shift+delete", "ctrl+delete"],
)
async def test_watchlist_remove_symbol(monkeypatch, remove_key):
    from tui_client.settings import UserSettings

    monkeypatch.setattr("tui_client.app.save_settings", lambda *a, **k: None)
    user = UserSettings()
    user.watchlist.watchlists = {"default": ["BTC-USD", "ETH-USD"]}
    app = AlertsApp(api=FakeApi(), user=user)
    async with app.run_test() as pilot:
        await pilot.press("w")
        prices = app.screen.query_one("#prices-table", DataTable)
        assert await wait_until(pilot, lambda: len(prices.rows) == 2)

        prices.move_cursor(row=0)
        await pilot.pause()
        await pilot.press(remove_key)

        assert await wait_until(pilot, lambda: "BTC-USD" not in app.screen.watchlist)
        assert user.watchlist.watchlists["default"] == ["ETH-USD"]
        assert await wait_until(pilot, lambda: len(prices.rows) == 1)


async def test_candles_refetch_when_cache_stale(prices_app):
    app, pilot, api = prices_app
    prices = app.screen.query_one("#prices-table", DataTable)
    assert await wait_until(pilot, lambda: len(prices.rows) == 25)

    calls: list[str] = []
    original = api.get_last_candle

    async def counting(symbol: str):
        calls.append(symbol)
        return await original(symbol)

    api.get_last_candle = counting
    screen = app.screen
    screen._candles_at = -10_000.0  # far past any TTL -> cache is stale
    await screen.reload()

    assert calls, "stale candle cache should be refreshed"
    assert screen._candles_at > 0.0


async def test_candles_reused_when_cache_fresh(prices_app):
    import time

    app, pilot, api = prices_app
    prices = app.screen.query_one("#prices-table", DataTable)
    assert await wait_until(pilot, lambda: len(prices.rows) == 25)

    calls: list[str] = []
    original = api.get_last_candle

    async def counting(symbol: str):
        calls.append(symbol)
        return await original(symbol)

    api.get_last_candle = counting
    screen = app.screen
    screen._candles_at = time.monotonic()  # fresh
    await screen.reload()

    assert calls == [], "fresh candle cache should not hit the API"


async def test_symbol_info_create_alert_flow(prices_app):
    app, pilot, api = prices_app
    prices = app.screen.query_one("#prices-table", DataTable)
    assert await wait_until(pilot, lambda: len(prices.rows) == 25)
    quote = app.screen._quotes[0]

    app.push_screen(SymbolInfoScreen(app.api, quote))
    assert await wait_until(pilot, lambda: isinstance(app.screen, SymbolInfoScreen))
    assert await wait_until(pilot, lambda: bool(app.screen.query("#create-alert")))

    app.screen.query_one("#create-alert", Button).press()
    assert await wait_until(pilot, lambda: isinstance(app.screen, AlertScreen))
    assert await wait_until(pilot, lambda: bool(app.screen.query("#symbol")))
    assert app.screen.query_one("#symbol", Input).value == quote.symbol.upper()

    app.screen.query_one("#value", Input).value = "100"
    await pilot.pause()
    await pilot.press("ctrl+s")

    assert await wait_until(pilot, lambda: len(api.created) == 1)
    assert api.created[0]["symbol"] == quote.symbol.upper()
    assert api.created[0]["conditions"][0]["value"] == 100.0


async def test_symbol_info_lists_edits_and_deletes_alerts():
    api = FakeApi([sample_alert("BTC-USD")])
    app = AlertsApp(api=api, default_symbol="BTC-USD")
    async with app.run_test() as pilot:
        assert await wait_until(pilot, lambda: isinstance(app.screen, PricesScreen))
        quote = QuoteView(symbol="BTC-USD", price=100.0, change_24h=1.0)
        app.push_screen(SymbolInfoScreen(app.api, quote))
        assert await wait_until(pilot, lambda: isinstance(app.screen, SymbolInfoScreen))
        assert await wait_until(pilot, lambda: bool(app.screen.query("#symbol-alerts")))

        table = app.screen.query_one("#symbol-alerts", DataTable)
        assert await wait_until(pilot, lambda: len(table.rows) == 1)
        table.move_cursor(row=0)
        await pilot.pause()

        # edit → dialog prefilled → save issues a PUT
        app.screen.query_one("#edit-alert", Button).press()
        assert await wait_until(pilot, lambda: isinstance(app.screen, AlertScreen))
        assert await wait_until(pilot, lambda: bool(app.screen.query("#symbol")))
        assert app.screen.query_one("#symbol", Input).value == "BTC-USD"
        assert app.screen.query_one("#value", Input).value == "3,794.94"
        app.screen.query_one("#value", Input).value = "250"
        await pilot.pause()
        await pilot.press("ctrl+s")

        assert await wait_until(pilot, lambda: bool(api.updated))
        alert_id, payload = api.updated[0]
        assert alert_id == "id-BTC-USD"
        assert payload["conditions"][0]["value"] == 250.0
        assert await wait_until(pilot, lambda: isinstance(app.screen, SymbolInfoScreen))

        # delete → DELETE issued, table empties
        assert await wait_until(pilot, lambda: len(table.rows) == 1)
        table.move_cursor(row=0)
        await pilot.pause()
        app.screen.query_one("#delete-alert", Button).press()
        assert await wait_until(pilot, lambda: "id-BTC-USD" in api.deleted)
        assert await wait_until(pilot, lambda: len(table.rows) == 0)


async def test_alert_list_row_selected_opens_editor_and_updates(pilot_app):
    app, pilot, api = pilot_app
    assert await wait_until(pilot, lambda: table_rows(app) == 2)
    table = app.screen.query_one("#alerts-table", DataTable)
    table.move_cursor(row=0)  # ETHUSDT
    await pilot.pause()

    # Enter / double-click both post DataTable.RowSelected → prefilled editor.
    await pilot.press("enter")
    assert await wait_until(pilot, lambda: isinstance(app.screen, AlertScreen))
    assert await wait_until(pilot, lambda: bool(app.screen.query("#symbol")))
    assert app.screen.query_one("#symbol", Input).value == "ETHUSDT"
    assert app.screen.query_one("#value", Input).value == "3,794.94"

    app.screen.query_one("#value", Input).value = "250"
    await pilot.pause()
    await pilot.press("ctrl+s")

    assert await wait_until(pilot, lambda: bool(api.updated))
    alert_id, payload = api.updated[0]
    assert alert_id == "id-ETHUSDT"
    assert payload["conditions"][0]["value"] == 250.0
    assert await wait_until(pilot, lambda: isinstance(app.screen, AlertListScreen))


async def test_settings_save_allows_empty_watchlist(monkeypatch):
    """An empty-symbol watchlist (created when the last list is deleted) must
    round-trip through the settings modal instead of blocking save."""
    from tui_client.settings import UserSettings

    monkeypatch.setattr("tui_client.screens.settings.save_settings", lambda *a, **k: None)
    user = UserSettings()
    user.watchlist.watchlists = {"default": []}
    app = AlertsApp(api=FakeApi(), user=user)
    async with app.run_test() as pilot:
        await pilot.press("o")
        assert await wait_until(pilot, lambda: isinstance(app.screen, SettingsModal))
        app.screen.query_one("#save", Button).press()
        assert await wait_until(pilot, lambda: not isinstance(app.screen, SettingsModal))
        assert app.user.watchlist.watchlists == {"default": []}
