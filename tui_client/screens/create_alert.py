"""Create-alert modal — keyboard-first condition builder."""

from __future__ import annotations

from datetime import datetime, timezone

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Checkbox, Input, Label, Select

from tui_client.api import AlertApiClient, ApiError

OPERATORS = [
    ("Above", "above"),
    ("Below", "below"),
    ("Crossing", "crossing"),
]
TRIGGERS = [
    ("Once only", "ONCE"),
    ("Every time", "EVERY_TIME"),
]


class CreateAlertModal(ModalScreen[dict | None]):
    """Collects alert configuration; dismisses with a payload dict or None."""

    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    def __init__(self, api: AlertApiClient, default_symbol: str = "BTCUSDT") -> None:
        super().__init__()
        self.api = api
        self.default_symbol = default_symbol
        self._condition_rows: list[tuple[Select, Input, Button]] = []

    def compose(self) -> ComposeResult:
        with VerticalScroll(id="modal-body"):
            yield Label("Create alert", id="modal-title")
            yield Label("Symbol", classes="field-label")
            yield Input(placeholder="e.g. BTCUSDT", id="symbol", value=self.default_symbol)
            yield Label("Conditions", classes="field-label")
            yield Label("", id="error", classes="error")
            with VerticalScroll(id="conditions"):
                pass
            yield Button("+ Add condition", id="add-condition")
            yield Label("Trigger", classes="field-label")
            yield Select(TRIGGERS, value="ONCE", allow_blank=False, id="trigger")
            yield Label("Expiration (UTC, optional)", classes="field-label")
            yield Input(
                placeholder="YYYY-MM-DDTHH:MM:SSZ",
                id="expiry",
            )
            yield Label("Message (optional)", classes="field-label")
            yield Input(placeholder="Custom message", id="message")
            yield Label("Notifications", classes="field-label")
            yield Checkbox("in_app", value=True, id="ch-in_app")
            yield Checkbox("toast", id="ch-toast")
            yield Checkbox("sound", id="ch-sound")
            with Horizontal(id="modal-actions"):
                yield Button("Cancel", id="cancel", variant="default")
                yield Button("Create", id="create", variant="primary")

    def on_mount(self) -> None:
        self._add_condition_row()
        self.query_one("#symbol", Input).focus()

    def _add_condition_row(self) -> None:
        index = len(self._condition_rows)
        operator = Select(OPERATORS, value="crossing", allow_blank=False, id=f"op-{index}")
        value = Input(placeholder="Target value", id=f"val-{index}")
        remove = Button("Remove", id=f"rm-{index}", variant="error")
        remove.disabled = index == 0
        row = Horizontal(operator, value, remove, id=f"cond-row-{index}")
        self.query_one("#conditions", VerticalScroll).mount(row)
        self._condition_rows.append((operator, value, remove))
        value.focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id
        if button_id == "add-condition":
            self._add_condition_row()
        elif button_id == "cancel":
            self.action_cancel()
        elif button_id == "create":
            self.run_worker(self._create())
        elif button_id and button_id.startswith("rm-"):
            self._remove_condition_row(int(button_id[3:]))

    def _remove_condition_row(self, index: int) -> None:
        if len(self._condition_rows) <= 1:
            return
        _, _, remove_button = self._condition_rows[index]
        row = remove_button.parent
        if row is not None:
            row.remove()
        del self._condition_rows[index]

    def action_cancel(self) -> None:
        self.dismiss(None)

    async def _create(self) -> None:
        error = self.query_one("#error", Label)
        try:
            payload = self._build_payload()
        except ValueError as exc:
            error.update(str(exc))
            return
        error.update("")
        try:
            await self.api.create_alert(payload)
        except ApiError as exc:
            error.update(exc.message)
            return
        self.dismiss(payload)

    def _build_payload(self) -> dict:
        symbol = self.query_one("#symbol", Input).value.strip().upper()
        if not symbol:
            raise ValueError("Symbol is required")

        conditions = []
        for operator, value_input, _ in self._condition_rows:
            operator_value = operator.value
            raw = value_input.value.strip()
            try:
                value = float(raw)
            except ValueError:
                raise ValueError(f"Value '{raw}' must be a number") from None
            if value <= 0:
                raise ValueError("Value must be greater than 0")
            conditions.append({"metric": "price", "operator": operator_value, "value": value})
        if not conditions:
            raise ValueError("At least one condition required")

        trigger = self.query_one("#trigger", Select).value
        expires_at = self._parse_expiry(self.query_one("#expiry", Input).value.strip())

        message = self.query_one("#message", Input).value.strip() or None
        channel_by_id = {
            "ch-in_app": "in_app",
            "ch-toast": "toast",
            "ch-sound": "sound",
        }
        channels = [
            name
            for checkbox_id, name in channel_by_id.items()
            if self.query_one(f"#{checkbox_id}", Checkbox).value
        ]
        if not channels:
            raise ValueError("At least one notification channel required")

        return {
            "symbol": symbol,
            "conditions": conditions,
            "match_mode": "ALL",
            "trigger_mode": trigger,
            "expires_at": expires_at,
            "message": message,
            "notification_channels": channels,
        }

    @staticmethod
    def _parse_expiry(raw: str) -> str | None:
        if not raw:
            return None
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            raise ValueError("Invalid expiration format (use YYYY-MM-DDTHH:MM:SSZ)") from None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        if parsed <= datetime.now(timezone.utc):
            raise ValueError("Expiration must be in the future")
        return parsed.isoformat().replace("+00:00", "Z")