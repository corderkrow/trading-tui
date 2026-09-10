"""Settings modal — watchlists + notification preferences."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Checkbox, Input, Label, RadioSet, RadioButton

from tui_client.settings import UserSettings, save_settings

SOURCES = [("Watchlist", "watchlist"), ("Portfolio", "portfolio"), ("Watchlist & Portfolio", "both")]
DELIVERIES = [
    ("Push Notification", "push"),
    ("In-app", "in_app"),
    ("Push Notification & Email", "push_email"),
    ("None", "none"),
]
THRESHOLD_CHOICES = [("≥ 2%", 2.0), ("≥ 5%", 5.0), ("≥ 20%", 20.0)]


def _radio_set(options: list[tuple[str, str]], value: str, set_id: str) -> RadioSet:
    buttons = [
        RadioButton(label, name=opt_value, value=opt_value == value)
        for label, opt_value in options
    ]
    return RadioSet(*buttons, id=set_id)


class SettingsModal(ModalScreen[UserSettings | None]):
    """Edit user settings; dismisses with updated settings or None on cancel."""

    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    def __init__(self, settings: UserSettings) -> None:
        super().__init__()
        self.settings = settings

    def compose(self) -> ComposeResult:
        wl = self.settings.watchlist
        n = self.settings.notifications
        with VerticalScroll(id="modal-body"):
            yield Label("Settings", id="modal-title")

            yield Label("Watchlist mode", classes="field-label")
            yield _radio_set([("Single Watchlist", "single"), ("Multiple Watchlists", "multiple")], wl.mode, "wl-mode")
            yield Label("Watchlists (comma-separated symbols per list; name:symbols)", classes="field-label")
            yield Input(
                placeholder="default: BTC-USD,ETH-USD | crypto: BTC-USD,SOL-USD",
                id="watchlists",
                value=" | ".join(
                    f"{name}: {', '.join(symbols)}" for name, symbols in wl.watchlists.items()
                ),
            )
            yield Label("Active watchlist", classes="field-label")
            yield Input(id="active", value=wl.active)

            yield Label("Price change sources", classes="field-label")
            yield _radio_set(SOURCES, n.price_change_sources, "sources")
            yield Label("Percentage change thresholds", classes="field-label")
            with Vertical(id="thresholds"):
                for label, value in THRESHOLD_CHOICES:
                    yield Checkbox(label, value=value in n.price_change_thresholds, name=str(value))
                custom_on = n.custom_threshold is not None
                yield Checkbox("custom", value=custom_on, id="th-custom")
                yield Input(
                    placeholder="%", id="th-custom-value",
                    value="" if n.custom_threshold is None else str(n.custom_threshold),
                    disabled=not custom_on,
                )

            yield Label("Price alert delivery", classes="field-label")
            yield _radio_set(DELIVERIES, n.price_alert_delivery, "delivery")

            yield Label("", id="error", classes="error")
            with Horizontal(id="modal-actions"):
                yield Button("Cancel", id="cancel", variant="default")
                yield Button("Save", id="save", variant="primary")

    def on_checkbox_changed(self, event: Checkbox.Changed) -> None:
        if event.checkbox.id == "th-custom":
            self.query_one("#th-custom-value", Input).disabled = not event.value

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel":
            self.action_cancel()
        elif event.button.id == "save":
            self._save()

    def action_cancel(self) -> None:
        self.dismiss(None)

    def _radio_value(self, set_id: str) -> str | None:
        radio_set = self.query_one(f"#{set_id}", RadioSet)
        pressed = radio_set.pressed_button
        return pressed.name if pressed else None

    def _save(self) -> None:
        error = self.query_one("#error", Label)
        try:
            updated = self._build_settings()
        except ValueError as exc:
            error.update(str(exc))
            return
        error.update("")
        save_settings(updated)
        self.dismiss(updated)

    def _build_settings(self) -> UserSettings:
        mode = self._radio_value("wl-mode")
        if mode is None:
            raise ValueError("Watchlist mode required")

        watchlists: dict[str, list[str]] = {}
        raw_lists = self.query_one("#watchlists", Input).value
        for chunk in raw_list_chunks(raw_lists):
            if ":" not in chunk:
                raise ValueError(f"Watchlist entry '{chunk}' must be name: sym1, sym2")
            name, symbols_raw = chunk.split(":", 1)
            name = name.strip()
            symbols = [s.strip().upper() for s in symbols_raw.split(",") if s.strip()]
            if not name or not symbols:
                raise ValueError(f"Watchlist entry '{chunk}' needs a name and symbols")
            if name in watchlists:
                raise ValueError(f"Duplicate watchlist name '{name}'")
            watchlists[name] = symbols
        if not watchlists:
            raise ValueError("At least one watchlist required")

        active = self.query_one("#active", Input).value.strip()
        if active not in watchlists:
            raise ValueError(f"Active watchlist '{active}' not in list")

        sources = self._radio_value("sources")
        if sources is None:
            raise ValueError("Price change source required")

        thresholds = [
            float(cb.name)
            for cb in self.query("#thresholds Checkbox").results(Checkbox)
            if cb.name and cb.value and cb.name != "custom"
        ]
        custom_checkbox = self.query_one("#th-custom", Checkbox)
        custom_threshold: float | None = None
        if custom_checkbox.value:
            raw = self.query_one("#th-custom-value", Input).value.strip()
            try:
                custom_threshold = float(raw)
            except ValueError:
                raise ValueError(f"Custom threshold '{raw}' must be a number") from None
        if not thresholds and custom_threshold is None:
            raise ValueError("At least one percentage threshold required")

        delivery = self._radio_value("delivery")
        if delivery is None:
            raise ValueError("Price alert delivery required")

        notifications = {
            "price_change_sources": sources,
            "price_change_thresholds": thresholds,
            "custom_threshold": custom_threshold,
            "price_alert_delivery": delivery,
        }
        return UserSettings.model_validate(
            {
                "watchlist": {"mode": mode, "watchlists": watchlists, "active": active},
                "notifications": notifications,
            }
        )


def raw_list_chunks(value: str) -> list[str]:
    """Split 'a: x, y | b: z' into ['a: x, y', 'b: z']."""
    return [chunk for chunk in value.split("|") if chunk.strip()]
