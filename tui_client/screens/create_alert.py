"""Create-alert modal — TradingView-style multi-condition builder.

Recreates the TradingView "Create alert" dialog
(https://www.tradingview.com/support/solutions/43000761492-multi-condition-alerts/)
as a Textual ``ModalScreen``. The modal only collects + validates intent and
dismisses with an :class:`AlertSpec`; persistence stays in ``AlertListScreen``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from textual import events
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Grid, Horizontal, Vertical, VerticalScroll
from textual.css.query import NoMatches
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, Select, SelectionList, Static, TextArea

from tui_client.api import AlertApiClient, ApiError, SearchHitView
from tui_client.widgets import SymbolAutoComplete

# ── Option lists ─────────────────────────────────────────────

SOURCES = ["Price", "Volume", "Indicator"]
VALUE_TYPES = ["Value", "Indicator"]
TRIGGERS = ["Once only", "Once per bar", "Once per bar close", "Once per minute"]
NOTIFICATIONS = ["App", "Toasts", "Sound", "Email", "Webhook"]
DEFAULT_NOTIFICATIONS = ["App", "Toasts", "Sound"]

OPERATORS = [
    "Crossing",
    "Crossing up",
    "Crossing down",
    "Greater than",
    "Less than",
    "Moving up %",
    "Moving down %",
]

# UI operator -> glyph shown in the condition block.
OPERATOR_ICONS = {
    "Crossing": "⤫",
    "Crossing up": "↗",
    "Crossing down": "↘",
    "Greater than": ">",
    "Less than": "<",
    "Moving up %": "↗",
    "Moving down %": "↘",
}

# The backend implements a narrower operator set; map UI intent onto it.
# (multi-condition UI ships ahead of the evaluator, hence the approximation)
OPERATOR_BACKEND: dict[str, tuple[str, str]] = {
    "Crossing": ("crossing", "price"),
    "Crossing up": ("crossing_up", "price"),
    "Crossing down": ("crossing_down", "price"),
    "Greater than": ("above", "price"),
    "Less than": ("below", "price"),
    "Moving up %": ("rises_by", "change_pct"),
    "Moving down %": ("falls_by", "change_pct"),
}
TRIGGER_BACKEND = {
    "Once only": "ONCE",
    "Once per bar": "EVERY_TIME",
    "Once per bar close": "EVERY_TIME",
    "Once per minute": "EVERY_TIME",
}
NOTIFICATION_BACKEND = {
    "App": "in_app",
    "Toasts": "toast",
    "Sound": "sound",
    "Email": "email",
    "Webhook": "webhook",
}

MAX_CONDITIONS = 3
EXPIRATION_FORMAT = "%B %d, %Y at %H:%M"

# Preset offsets for the expiration picker.
EXPIRATION_PRESETS = [
    ("1 hour", timedelta(hours=1)),
    ("1 day", timedelta(days=1)),
    ("7 days", timedelta(days=7)),
    ("30 days", timedelta(days=30)),
    ("90 days", timedelta(days=90)),
    ("1 year", timedelta(days=365)),
]


# ── Dismiss payload ──────────────────────────────────────────


@dataclass
class Condition:
    """One alert condition as entered in the dialog."""

    source: str
    operator: str
    value_type: str
    value: float

    def to_payload(self) -> dict:
        operator, metric = OPERATOR_BACKEND.get(self.operator, ("crossing", "price"))
        return {"metric": metric, "operator": operator, "value": self.value}


@dataclass
class AlertSpec:
    """Validated alert configuration returned by the modal."""

    symbol: str
    conditions: list[Condition]
    trigger: str
    expires_at: datetime
    message: str
    notifications: list[str] = field(default_factory=list)

    def to_payload(self) -> dict:
        """Translate the spec into the backend ``CreateAlertRequest`` shape."""
        return {
            "symbol": self.symbol.strip().upper(),
            "conditions": [c.to_payload() for c in self.conditions],
            "match_mode": "ALL",
            "trigger_mode": TRIGGER_BACKEND.get(self.trigger, "ONCE"),
            "expires_at": self.expires_at.isoformat(),
            "message": self.message or None,
            "notification_channels": [
                NOTIFICATION_BACKEND[name]
                for name in self.notifications
                if name in NOTIFICATION_BACKEND
            ],
        }


# ── Inputs ───────────────────────────────────────────────────


class PriceInput(Input):
    """Numeric input with up/down tick stepping (emulates the ⇅ spinner)."""

    BINDINGS = [
        Binding("up", "step(1)", "Step up", show=False),
        Binding("down", "step(-1)", "Step down", show=False),
        Binding("shift+up", "step(100)", "Step ×100 up", show=False),
        Binding("shift+down", "step(-100)", "Step ×100 down", show=False),
    ]

    tick = 0.01
    # Cleared on first focus so the user can type instead of deleting "0.00".
    _clear_on_focus = True

    def on_focus(self, event: events.Focus) -> None:
        if self._clear_on_focus:
            self._clear_on_focus = False
            self.value = ""

    def action_step(self, factor: int) -> None:
        try:
            current = float(self.value.replace(",", "")) if self.value else 0.0
        except ValueError:
            current = 0.0
        self.value = f"{current + self.tick * factor:,.2f}"

    def on_input_blurred(self, event: Input.Blurred) -> None:
        event.stop()
        raw = self.value.replace(",", "").strip()
        if not raw:
            return
        try:
            self.value = f"{float(raw):,.2f}"
        except ValueError:
            return


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
        self._selected = list(selected) if selected is not None else list(DEFAULT_NOTIFICATIONS)

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


# ── Modal ────────────────────────────────────────────────────


@dataclass
class _ConditionRow:
    source: Select
    operator: Select
    value_type: Select
    value: PriceInput


class CreateAlertModal(ModalScreen[AlertSpec | None]):
    """Collects alert configuration; dismisses with an ``AlertSpec`` or None."""

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("ctrl+s", "create", "Create"),
        Binding("ctrl+n", "add_condition", "Add condition", show=False),
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
        self._rows: list[_ConditionRow] = []
        self._message = ""
        self._message_dirty = False
        self._notifications = list(DEFAULT_NOTIFICATIONS)
        self._expires_at = datetime.now().astimezone() + timedelta(days=30)

    def compose(self) -> ComposeResult:
        symbol_input = Input(
            self.default_symbol, id="symbol", restrict=r"[A-Za-z0-9.\-_^=/]*"
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
                        with Vertical(id="condition-rows"):
                            with Vertical(classes="condition-row", id="condition-0"):
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
                        with Horizontal(classes="add-row"):
                            yield Button("+ Add condition", id="add_condition", classes="link")
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
                    yield Button(self._expiration_text(), id="expiration", classes="row-link")
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
        row = _ConditionRow(
            source=self.query_one("#source", Select),
            operator=self.query_one("#operator", Select),
            value_type=self.query_one("#value_type", Select),
            value=self.query_one("#value", PriceInput),
        )
        self._rows = [row]
        if self._symbol_autocomplete is not None:
            self._symbol_autocomplete.set_hits(
                [SearchHitView(symbol=s, name="") for s in self.symbols]
            )
        self._sync_message()
        self._sync_notifications()
        self.query_one("#symbol", Input).focus()

    # ── state sync ──────────────────────────────────────────

    def _expiration_text(self) -> str:
        return self._expires_at.strftime(EXPIRATION_FORMAT)

    def _sync_message(self) -> None:
        if self._message_dirty:
            return
        row = self._rows[0]
        symbol = self.query_one("#symbol", Input).value.strip() or self.default_symbol
        value = row.value.value.strip() or "0"
        self._message = f"{symbol} {row.operator.value} {value}"
        self.query_one("#message", Button).label = f"{self._message} >"

    def _sync_notifications(self) -> None:
        joined = ", ".join(self._notifications)
        self.query_one("#notifications", Button).label = f"{joined} >"

    # ── events ──────────────────────────────────────────────

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id == "operator":
            self._sync_message()

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input is self._rows[0].value:
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
        """Fetch symbol suggestions for the header input from the search endpoint."""
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
        if len(self._rows) >= MAX_CONDITIONS:
            self.notify(f"At most {MAX_CONDITIONS} conditions", severity="warning")
            return
        index = len(self._rows)
        source = Select(
            [(s, s) for s in SOURCES], value="Price", allow_blank=False, id=f"source-{index}"
        )
        operator = Select(
            [(s, s) for s in OPERATORS],
            value="Crossing",
            allow_blank=False,
            id=f"operator-{index}",
        )
        value_type = Select(
            [(s, s) for s in VALUE_TYPES],
            value="Value",
            allow_blank=False,
            id=f"value_type-{index}",
        )
        value = PriceInput("0.00", id=f"value-{index}", restrict=r"[0-9.,]*")
        row = Vertical(
            source, operator, Horizontal(value_type, value, classes="value-row"),
            classes="condition-row",
            id=f"condition-{index}",
        )
        self.query_one("#condition-rows", Vertical).mount(row)
        self._rows.append(
            _ConditionRow(source=source, operator=operator, value_type=value_type, value=value)
        )
        value.focus()

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

        conditions: list[Condition] = []
        for row in self._rows:
            raw = row.value.value.replace(",", "").strip()
            try:
                value = float(raw)
            except ValueError:
                row.value.focus()
                raise ValueError(f"Value '{row.value.value}' must be a number") from None
            if value <= 0:
                row.value.focus()
                raise ValueError("Value must be greater than 0")
            conditions.append(
                Condition(
                    source=row.source.value,
                    operator=row.operator.value,
                    value_type=row.value_type.value,
                    value=value,
                )
            )

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
