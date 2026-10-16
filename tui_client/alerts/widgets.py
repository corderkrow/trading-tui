"""Reusable widgets for the multi-condition alert dialog."""

from __future__ import annotations

from textual import events
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.reactive import reactive
from textual.widgets import Button, Input, Static

from tui_client.alerts.models import MAX_CONDITIONS, Condition


class PriceInput(Input):
    """Numeric input with up/down tick stepping (the ⇅ spinner analogue)."""

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


class ConditionRow(Horizontal):
    """One condition: a full-width preview button plus a ``✕`` remove button."""

    def __init__(self, condition: Condition, **kwargs) -> None:
        super().__init__(**kwargs)
        self.condition = condition

    def compose(self):
        remove = Button(
            "✕",
            id=f"remove-{self.condition.id}",
            classes="remove",
        )
        # Keep Tab order as rows top→bottom; removal is a click/`delete` action.
        remove.can_focus = False
        yield Button(
            self.condition.preview(),
            id=f"preview-{self.condition.id}",
            classes="preview",
        )
        yield remove

    class PreviewRequested(Message):
        def __init__(self, condition: Condition) -> None:
            super().__init__()
            self.condition = condition

    class RemoveRequested(Message):
        def __init__(self, condition_id: str) -> None:
            super().__init__()
            self.condition_id = condition_id

    def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id or ""
        if button_id.startswith("preview-"):
            event.stop()
            self.post_message(self.PreviewRequested(self.condition))
        elif button_id.startswith("remove-"):
            event.stop()
            self.post_message(self.RemoveRequested(self.condition.id))


class ConditionList(Vertical):
    """Owns the ordered condition list and rebuilds rows whenever it changes.

    Only used in "Mode B" (2+ conditions). Mutating through :meth:`add`,
    :meth:`update` and :meth:`remove` reassigns :attr:`conditions`, which
    recomposes the rows and posts :class:`ConditionsChanged` so the dialog can
    re-render the message, add-button state and timeframe hint.
    """

    conditions: reactive[list[Condition]] = reactive(list, recompose=True)

    class ConditionsChanged(Message):
        def __init__(self, count: int) -> None:
            super().__init__()
            self.count = count

    class EditRequested(Message):
        def __init__(self, condition: Condition) -> None:
            super().__init__()
            self.condition = condition

    def compose(self):
        for index, condition in enumerate(self.conditions):
            yield ConditionRow(condition, id=f"condition-{condition.id}")
            if index < len(self.conditions) - 1:
                yield Static("AND", classes="and-sep")

    def add(self, condition: Condition) -> None:
        if len(self.conditions) >= MAX_CONDITIONS:
            return
        self.conditions = [*self.conditions, condition]

    def update(self, condition: Condition) -> None:
        self.conditions = [
            condition if existing.id == condition.id else existing
            for existing in self.conditions
        ]

    def remove(self, condition_id: str) -> None:
        if len(self.conditions) <= 1:
            return
        self.conditions = [c for c in self.conditions if c.id != condition_id]

    def watch_conditions(self, conditions: list[Condition]) -> None:
        self.post_message(self.ConditionsChanged(len(conditions)))

    def on_condition_row_preview_requested(
        self, event: ConditionRow.PreviewRequested
    ) -> None:
        event.stop()
        self.post_message(self.EditRequested(event.condition))

    def on_condition_row_remove_requested(
        self, event: ConditionRow.RemoveRequested
    ) -> None:
        event.stop()
        self.remove(event.condition_id)
