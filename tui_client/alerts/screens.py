"""Multi-condition alert dialog — TradingView-style.

``AlertScreen`` collects and validates intent and dismisses with an
:class:`~alerts.models.AlertSpec`; persistence stays with the caller. It has two
condition modes:

* **Mode A** (1 condition): the inline source/operator/value form.
* **Mode B** (2+ conditions): a :class:`~alerts.widgets.ConditionList` of preview
  buttons separated by ``AND``.

Adding the second condition promotes the dialog to Mode B; deleting back down to
one condition restores Mode A with the surviving condition hydrated into the
inline form.

Reference: https://www.tradingview.com/support/solutions/43000761492-multi-condition-alerts/
"""

from __future__ import annotations

from datetime import datetime, timedelta
from uuid import uuid4

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Grid, Horizontal, Vertical, VerticalScroll
from textual.css.query import NoMatches
from textual.screen import ModalScreen
from textual.widgets import (
    Button,
    Input,
    Label,
    Select,
    SelectionList,
    Static,
    TextArea,
)

from tui_client.alerts.models import (
    DEFAULT_NOTIFICATIONS,
    DEFAULT_TIMEFRAME,
    MAX_CONDITIONS,
    NOTIFICATIONS,
    OPERATORS,
    SOURCES,
    TF_SECONDS,
    TIMEFRAMES,
    TRIGGERS,
    VALUE_TYPES,
    AlertSpec,
    Condition,
)
from tui_client.alerts.widgets import ConditionList, ConditionRow, PriceInput
from tui_client.api import AlertApiClient, ApiError, SearchHitView
from tui_client.widgets import SymbolAutoComplete

EXPIRATION_FORMAT = "%B %d, %Y at %H:%M"

EXPIRATION_PRESETS = [
    ("1 hour", timedelta(hours=1)),
    ("1 day", timedelta(days=1)),
    ("7 days", timedelta(days=7)),
    ("30 days", timedelta(days=30)),
    ("90 days", timedelta(days=90)),
    ("1 year", timedelta(days=365)),
]


# ── Sub-screens ──────────────────────────────────────────────


class MessageScreen(ModalScreen[str | None]):
    """Free-text alert message editor (supports ``{{ticker}}`` placeholders)."""

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("ctrl+s", "ok", "OK"),
    ]

    def __init__(self, message: str = "") -> None:
        super().__init__()
        self._message = message

    def compose(self) -> ComposeResult:
        with Vertical(id="message-dialog"):
            yield Label("Message", id="message-title")
            yield TextArea(self._message, id="message-text")
            with Horizontal(id="message-actions"):
                yield Button("Cancel", id="message-cancel")
                yield Button("OK", id="message-ok", variant="primary")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "message-ok":
            self.action_ok()
        elif event.button.id == "message-cancel":
            self.action_cancel()

    def action_ok(self) -> None:
        self.dismiss(self.query_one("#message-text", TextArea).text)

    def action_cancel(self) -> None:
        self.dismiss(None)


class NotificationsScreen(ModalScreen[list[str] | None]):
    """Multi-select of notification channels."""

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("ctrl+s", "ok", "OK"),
    ]

    def __init__(self, selected: list[str] | None = None) -> None:
        super().__init__()
        self._selected = (
            list(selected) if selected is not None else list(DEFAULT_NOTIFICATIONS)
        )

    def compose(self) -> ComposeResult:
        with Vertical(id="notifications-dialog"):
            yield Label("Notifications", id="notifications-title")
            yield SelectionList(
                *[(name, name, name in self._selected) for name in NOTIFICATIONS],
                id="notifications-list",
            )
            with Horizontal(id="notifications-actions"):
                yield Button("Cancel", id="notifications-cancel")
                yield Button("OK", id="notifications-ok", variant="primary")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "notifications-ok":
            self.action_ok()
        elif event.button.id == "notifications-cancel":
            self.action_cancel()

    def action_ok(self) -> None:
        selected = list(self.query_one("#notifications-list", SelectionList).selected)
        self.dismiss([name for name in NOTIFICATIONS if name in selected])

    def action_cancel(self) -> None:
        self.dismiss(None)


class ExpirationScreen(ModalScreen[datetime | None]):
    """Preset expiration picker; returns an aware datetime."""

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("ctrl+s", "ok", "OK"),
    ]

    def __init__(self, current: datetime | None = None) -> None:
        super().__init__()
        self._current = current

    def compose(self) -> ComposeResult:
        now = datetime.now().astimezone()
        presets = [
            (f"{label} · {self._fmt(now + delta)}", label)
            for label, delta in EXPIRATION_PRESETS
        ]
        with Vertical(id="expiration-dialog"):
            yield Label("Expiration", id="expiration-title")
            yield SelectionList(
                *[(prompt, label, label == "30 days") for prompt, label in presets],
                id="expiration-list",
            )
            with Horizontal(id="expiration-actions"):
                yield Button("Cancel", id="expiration-cancel")
                yield Button("OK", id="expiration-ok", variant="primary")

    @staticmethod
    def _fmt(moment: datetime) -> str:
        return moment.strftime(EXPIRATION_FORMAT)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "expiration-ok":
            self.action_ok()
        elif event.button.id == "expiration-cancel":
            self.action_cancel()

    def action_ok(self) -> None:
        selected = list(self.query_one("#expiration-list", SelectionList).selected)
        label = selected[0] if selected else "30 days"
        delta = dict(EXPIRATION_PRESETS).get(label, timedelta(days=30))
        self.dismiss(datetime.now().astimezone() + delta)

    def action_cancel(self) -> None:
        self.dismiss(None)


class ConditionEditorScreen(ModalScreen[Condition | None]):
    """Add or edit a single condition.

    Dismisses with the new/edited :class:`Condition`. ``Delete`` (edit only)
    sets :attr:`deleted` and dismisses ``None`` so the caller can tell a delete
    apart from a cancel.
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("ctrl+s", "confirm", "Save"),
    ]

    def __init__(self, condition: Condition | None = None) -> None:
        super().__init__()
        self._condition = condition
        self.deleted = False

    def compose(self) -> ComposeResult:
        condition = self._condition
        editing = condition is not None
        with Vertical(id="condition-editor"):
            yield Label(
                "Edit condition" if editing else "Add condition",
                id="condition-editor-title",
            )
            with Grid(id="condition-editor-fields"):
                yield Label("Source", classes="label")
                yield Select(
                    [(s, s) for s in SOURCES],
                    value=condition.source if editing else "Price",
                    allow_blank=False,
                    id="source",
                )
                yield Label("Operator", classes="label")
                yield Select(
                    [(s, s) for s in OPERATORS],
                    value=condition.operator if editing else "Crossing",
                    allow_blank=False,
                    id="operator",
                )
                yield Label("Value type", classes="label")
                yield Select(
                    [(s, s) for s in VALUE_TYPES],
                    value=condition.value_type if editing else "Value",
                    allow_blank=False,
                    id="value_type",
                )
                yield Label("Value", classes="label")
                yield PriceInput("", id="value", restrict=r"[0-9.,]*")
                yield Label("Timeframe", classes="label")
                yield Select(
                    [(tf, tf) for tf in TIMEFRAMES],
                    value=condition.timeframe if editing else DEFAULT_TIMEFRAME,
                    allow_blank=False,
                    id="timeframe",
                )
            with Horizontal(id="condition-editor-actions"):
                if editing:
                    yield Button("Delete", id="editor-delete", classes="danger")
                yield Static(classes="spacer")
                yield Button("Cancel", id="editor-cancel")
                yield Button(
                    "Save" if editing else "Add",
                    id="editor-confirm",
                    variant="primary",
                )

    def on_mount(self) -> None:
        if self._condition is not None and self._condition.value is not None:
            self.query_one("#value", PriceInput).value = f"{self._condition.value:,.2f}"
        self.query_one("#value", PriceInput).focus()

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id == "value_type":
            value_input = self.query_one("#value", PriceInput)
            value_input.disabled = event.value == "Indicator"

    def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id
        if button_id == "editor-confirm":
            self.action_confirm()
        elif button_id == "editor-cancel":
            self.action_cancel()
        elif button_id == "editor-delete":
            self.action_delete()

    def _reject(self, message: str) -> None:
        self.notify(message, severity="error")
        self.query_one("#value", PriceInput).focus()

    def action_confirm(self) -> None:
        value_type = str(self.query_one("#value_type", Select).value)
        value: float | None = None
        if value_type != "Indicator":
            raw = self.query_one("#value", PriceInput).value.replace(",", "").strip()
            try:
                value = float(raw)
            except ValueError:
                self._reject("Value must be a number")
                return
            if value <= 0:
                self._reject("Value must be greater than 0")
                return

        condition = Condition(
            source=str(self.query_one("#source", Select).value),
            operator=str(self.query_one("#operator", Select).value),
            value_type=value_type,
            value=value,
            timeframe=str(self.query_one("#timeframe", Select).value),
        )
        if self._condition is not None:
            condition.id = self._condition.id
        self.dismiss(condition)

    def action_delete(self) -> None:
        self.deleted = True
        self.dismiss(None)

    def action_cancel(self) -> None:
        self.dismiss(None)


# ── Main modal ───────────────────────────────────────────────


class AlertScreen(ModalScreen[AlertSpec | None]):
    """Collects a multi-condition alert and dismisses with an ``AlertSpec``."""

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("ctrl+s", "create", "Create"),
        Binding("ctrl+n", "add_condition", "Add condition", show=False),
        Binding("delete", "delete_condition", "Remove condition", show=False),
    ]

    CSS_PATH = "alert.tcss"

    def __init__(
        self,
        default_symbol: str = "BTCUSD",
        symbols: list[str] | None = None,
        api: AlertApiClient | None = None,
    ) -> None:
        super().__init__()
        self.default_symbol = default_symbol.upper()
        options = [self.default_symbol, *(symbols or [])]
        self.symbols = list(dict.fromkeys(options))
        self._api = api
        self._symbol_autocomplete: SymbolAutoComplete | None = None
        self._symbol_timer = None
        self._inline_id = uuid4().hex[:8]
        self._inline_timeframe = DEFAULT_TIMEFRAME
        self._message = ""
        self._message_dirty = False
        self._notifications = list(DEFAULT_NOTIFICATIONS)
        self._expires_at = datetime.now().astimezone() + timedelta(days=30)

    def compose(self) -> ComposeResult:
        symbol_input = Input(
            self.default_symbol, id="symbol", restrict=r"[A-Za-z0-9.\-]*"
        )
        with Vertical(id="dialog"):
            with Horizontal(id="header"):
                yield Label("Create alert on", id="title")
                yield symbol_input
                yield Static(classes="spacer")
                yield Button("⊞", id="templates", classes="icon")
                yield Button("✕", id="close", classes="icon")
            with VerticalScroll(id="body"):
                with Grid(classes="section", id="condition"):
                    yield Label("Condition", classes="label")
                    with Vertical(id="condition-controls"):
                        with Vertical(id="condition-inline"):
                            yield Select(
                                [(s, s) for s in SOURCES],
                                value="Price",
                                allow_blank=False,
                                id="source",
                            )
                            yield Select(
                                [(s, s) for s in OPERATORS],
                                value="Crossing",
                                allow_blank=False,
                                id="operator",
                            )
                            with Horizontal(classes="value-row"):
                                yield Select(
                                    [(s, s) for s in VALUE_TYPES],
                                    value="Value",
                                    allow_blank=False,
                                    id="value_type",
                                )
                                yield PriceInput(
                                    "0.00", id="value", restrict=r"[0-9.,]*"
                                )
                        yield ConditionList(id="condition-list")
                        yield Static("", id="timeframe-hint")
                        with Horizontal(classes="add-row"):
                            yield Button(
                                "+ Add condition", id="add_condition", classes="link"
                            )
                            yield Static("?", id="help", classes="help")
                with Grid(classes="section", id="settings"):
                    yield Label("Trigger", classes="label")
                    yield Select(
                        [(s, s) for s in TRIGGERS],
                        value="Once only",
                        allow_blank=False,
                        id="trigger",
                    )
                    yield Label("Expiration", classes="label")
                    yield Button(
                        self._expiration_text(), id="expiration", classes="row-link"
                    )
                    yield Label("Message", classes="label")
                    yield Button("", id="message", classes="row-link")
                    yield Label("Notifications", classes="label")
                    yield Button("", id="notifications", classes="row-link")
            with Horizontal(id="footer"):
                yield Button("Cancel", id="cancel")
                yield Button("Create", id="create", variant="primary")
        self._symbol_autocomplete = SymbolAutoComplete(
            symbol_input,
            id="symbol-autocomplete",
            on_selected=self._on_symbol_selected,
        )
        yield self._symbol_autocomplete

    def on_mount(self) -> None:
        if self._symbol_autocomplete is not None:
            self._symbol_autocomplete.set_hits(
                [SearchHitView(symbol=s, name="") for s in self.symbols]
            )
        self._sync_notifications()
        self._render_mode()
        self._sync_timeframe_hint()
        self._sync_message()
        self.query_one("#value", PriceInput).focus()

    # ── condition mode ──────────────────────────────────────

    def _condition_list(self) -> ConditionList:
        return self.query_one("#condition-list", ConditionList)

    def _is_multi(self) -> bool:
        return len(self._condition_list().conditions) >= 2

    def _inline_condition(self) -> Condition:
        value_type = str(self.query_one("#value_type", Select).value)
        raw = self.query_one("#value", PriceInput).value.replace(",", "").strip()
        value: float | None = None
        if value_type != "Indicator" and raw:
            try:
                value = float(raw)
            except ValueError:
                value = None
        return Condition(
            source=str(self.query_one("#source", Select).value),
            operator=str(self.query_one("#operator", Select).value),
            value_type=value_type,
            value=value,
            timeframe=self._inline_timeframe,
            id=self._inline_id,
        )

    def _all_conditions(self) -> list[Condition]:
        conditions = list(self._condition_list().conditions)
        if len(conditions) >= 2:
            return conditions
        return [self._inline_condition()]

    def _hydrate_inline(self, condition: Condition) -> None:
        self._inline_id = condition.id
        self._inline_timeframe = condition.timeframe
        self.query_one("#source", Select).value = (
            condition.source if condition.source in SOURCES else "Price"
        )
        self.query_one("#operator", Select).value = (
            condition.operator if condition.operator in OPERATORS else "Crossing"
        )
        self.query_one("#value_type", Select).value = (
            condition.value_type if condition.value_type in VALUE_TYPES else "Value"
        )
        if condition.value is not None:
            self.query_one("#value", PriceInput).value = f"{condition.value:,.2f}"

    def _render_mode(self) -> None:
        multi = self._is_multi()
        self.query_one("#condition-inline").display = not multi
        self._condition_list().display = multi
        self._sync_add_button()

    def _sync_add_button(self) -> None:
        button = self.query_one("#add_condition", Button)
        count = len(self._all_conditions())
        button.disabled = count >= MAX_CONDITIONS
        if self._is_multi():
            button.label = f"+ Add condition ({count}/{MAX_CONDITIONS})"
        else:
            button.label = "+ Add condition"
        button.tooltip = "Max 5 conditions" if button.disabled else None

    def _sync_timeframe_hint(self) -> None:
        hint = self.query_one("#timeframe-hint", Static)
        timeframes = {c.timeframe for c in self._all_conditions()}
        if self._is_multi() and len(timeframes) > 1:
            smallest = min(timeframes, key=lambda tf: TF_SECONDS[tf])
            hint.update(f"Checks every {smallest} (smallest timeframe)")
            hint.display = True
        else:
            hint.display = False

    def _after_conditions_changed(self) -> None:
        conditions = list(self._condition_list().conditions)
        if conditions and len(conditions) <= 1:
            self._hydrate_inline(conditions[0])
        self._render_mode()
        self._sync_timeframe_hint()
        self._sync_message()

    # ── state sync ──────────────────────────────────────────

    def _expiration_text(self) -> str:
        return self._expires_at.strftime(EXPIRATION_FORMAT)

    def _sync_message(self) -> None:
        if self._message_dirty:
            return
        symbol = self.query_one("#symbol", Input).value.strip() or self.default_symbol
        previews = [c.preview_short() for c in self._all_conditions()]
        self._message = f"{symbol} " + " and ".join(previews) if previews else symbol
        self.query_one("#message", Button).label = f"{self._message} >"

    def _sync_notifications(self) -> None:
        joined = ", ".join(self._notifications)
        self.query_one("#notifications", Button).label = f"{joined} >"

    # ── events ──────────────────────────────────────────────

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id in ("operator", "source", "value_type"):
            self._sync_message()

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "value":
            self._sync_message()
        elif event.input.id == "symbol":
            self._sync_message()
            if self._symbol_timer is not None:
                self._symbol_timer.stop()
                self._symbol_timer = None
            term = event.value.strip()
            if term:
                self._symbol_timer = self.set_timer(
                    0.3, lambda: self.run_worker(self._search_symbols(term))
                )

    async def _search_symbols(self, term: str) -> None:
        self._symbol_timer = None
        if self._api is None or self._symbol_autocomplete is None or not self.is_mounted:
            return
        try:
            hits = await self._api.search_symbols(term)
        except ApiError:
            return
        except Exception as exc:  # transport errors must not surface as a crash
            self.log.warning(f"symbol search failed: {exc!r}")
            return
        if not self.is_mounted:
            return
        try:
            current = self.query_one("#symbol", Input).value.strip()
        except NoMatches:
            return
        if current != term:
            return
        local = [
            SearchHitView(symbol=s, name="")
            for s in self.symbols
            if term.lower() in s.lower()
        ]
        self._symbol_autocomplete.set_hits([*hits, *local])

    def _on_symbol_selected(self, symbol: str) -> None:
        if self._symbol_autocomplete is not None:
            self._symbol_autocomplete.set_hits([])
        self._sync_message()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id
        if button_id in ("close", "cancel"):
            self.action_cancel()
        elif button_id == "create":
            self.action_create()
        elif button_id == "add_condition":
            self.action_add_condition()
        elif button_id == "templates":
            self.notify("Templates are not available yet", severity="warning")
        elif button_id == "message":
            self.app.push_screen(MessageScreen(self._message), self._handle_message)
        elif button_id == "notifications":
            self.app.push_screen(
                NotificationsScreen(self._notifications), self._handle_notifications
            )
        elif button_id == "expiration":
            self.app.push_screen(
                ExpirationScreen(self._expires_at), self._handle_expiration
            )

    def on_condition_list_conditions_changed(
        self, event: ConditionList.ConditionsChanged
    ) -> None:
        self._after_conditions_changed()

    def on_condition_list_edit_requested(
        self, event: ConditionList.EditRequested
    ) -> None:
        condition = event.condition
        editor = ConditionEditorScreen(condition)
        self.app.push_screen(
            editor,
            lambda result, editor=editor, condition=condition: self._on_edit_result(
                editor, condition, result
            ),
        )

    def _handle_message(self, message: str | None) -> None:
        if message is None:
            return
        self._message = message
        self._message_dirty = True
        self.query_one("#message", Button).label = f"{message} >"

    def _handle_notifications(self, selected: list[str] | None) -> None:
        if selected is None:
            return
        self._notifications = selected
        self._sync_notifications()

    def _handle_expiration(self, expires_at: datetime | None) -> None:
        if expires_at is None:
            return
        self._expires_at = expires_at
        self.query_one("#expiration", Button).label = self._expiration_text()

    # ── conditions ──────────────────────────────────────────

    def action_add_condition(self) -> None:
        if len(self._all_conditions()) >= MAX_CONDITIONS:
            return
        editor = ConditionEditorScreen()
        self.app.push_screen(
            editor,
            lambda result, editor=editor: self._on_add_result(editor, result),
        )

    def _on_add_result(self, editor: ConditionEditorScreen, result: Condition | None) -> None:
        if editor.deleted or result is None:
            return
        condition_list = self._condition_list()
        if self._is_multi():
            condition_list.add(result)
        else:
            condition_list.conditions = [self._inline_condition(), result]
        self._after_conditions_changed()

    def _on_edit_result(
        self,
        editor: ConditionEditorScreen,
        condition: Condition,
        result: Condition | None,
    ) -> None:
        if editor.deleted:
            self._condition_list().remove(condition.id)
            self._after_conditions_changed()
            return
        if result is None:
            return
        self._condition_list().update(result)
        self._after_conditions_changed()
        self.call_after_refresh(self._focus_condition, result.id)

    def action_delete_condition(self) -> None:
        widget = self.focused
        while widget is not None:
            if isinstance(widget, ConditionRow):
                self._condition_list().remove(widget.condition.id)
                self._after_conditions_changed()
                return
            widget = widget.parent

    def _focus_condition(self, condition_id: str) -> None:
        for widget in self.query(f"#preview-{condition_id}"):
            widget.focus()
            return
        self.query_one("#value", PriceInput).focus()

    # ── actions ─────────────────────────────────────────────

    def action_cancel(self) -> None:
        self.dismiss(None)

    def action_create(self) -> None:
        try:
            spec = self._build_spec()
        except ValueError as exc:
            self.notify(str(exc), severity="error")
            return
        self.dismiss(spec)

    def _build_spec(self) -> AlertSpec:
        symbol = self.query_one("#symbol", Input).value.strip().upper()
        if not symbol:
            self.query_one("#symbol", Input).focus()
            raise ValueError("Symbol is required")

        conditions = self._all_conditions()
        if not 1 <= len(conditions) <= MAX_CONDITIONS:
            raise ValueError(f"Alerts need 1 to {MAX_CONDITIONS} conditions")

        for condition in conditions:
            if condition.value_type == "Indicator":
                continue
            if condition.value is None or condition.value <= 0:
                self._focus_condition(condition.id)
                raise ValueError("Value must be greater than 0")

        if self._expires_at <= datetime.now().astimezone():
            self.query_one("#expiration", Button).focus()
            raise ValueError("Expiration must be in the future")

        if not self._notifications:
            self.query_one("#notifications", Button).focus()
            raise ValueError("At least one notification required")

        return AlertSpec(
            symbol=symbol,
            conditions=conditions,
            trigger=str(self.query_one("#trigger", Select).value),
            expires_at=self._expires_at,
            message=self._message,
            notifications=list(self._notifications),
        )
