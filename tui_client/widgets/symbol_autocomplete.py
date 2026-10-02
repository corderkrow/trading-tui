"""Symbol autocomplete dropdown for the create-alert symbol field."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Protocol

from textual.widgets import Input
from textual_autocomplete import AutoComplete, DropdownItem, TargetState

MAX_SUGGESTIONS = 12


class _SearchHit(Protocol):
    symbol: str
    name: str | None


class SymbolAutoComplete(AutoComplete):
    """Suggest symbols fetched asynchronously from the market search endpoint.

    Candidates are pushed in with :meth:`set_hits` after the owning screen
    queries the search endpoint, so the base class ``candidates`` callback is
    not used.
    """

    def __init__(
        self,
        target: Input | str,
        *,
        on_selected: Callable[[str], None] | None = None,
        **kwargs,
    ) -> None:
        super().__init__(target, candidates=None, **kwargs)
        self._hits: list[tuple[str, str]] = []
        self._on_selected = on_selected

    def set_hits(self, hits: Sequence[_SearchHit]) -> None:
        """Replace the suggestion list (deduped, capped) and rebuild the dropdown."""
        seen: set[str] = set()
        self._hits = []
        for hit in hits:
            symbol = hit.symbol.strip().upper()
            if not symbol or symbol in seen:
                continue
            seen.add(symbol)
            self._hits.append((symbol, (hit.name or "").strip()))
            if len(self._hits) >= MAX_SUGGESTIONS:
                break
        if self.is_mounted:
            self._handle_target_update()

    def get_candidates(self, target_state: TargetState) -> list[DropdownItem]:
        items: list[DropdownItem] = []
        for symbol, name in self._hits:
            items.append(DropdownItem(main=symbol, prefix=name) if name else DropdownItem(symbol))
        return items

    def should_show_dropdown(self, search_string: str) -> bool:
        if not self._hits or not self.target.has_focus:
            return False
        if not search_string:
            # Show the full suggestion list as soon as the field is focused.
            return True
        return super().should_show_dropdown(search_string)

    def _handle_focus_change(self, has_focus: bool) -> None:
        super()._handle_focus_change(has_focus)
        if has_focus and self.is_mounted:
            self._handle_target_update()

    def post_completion(self) -> None:
        super().post_completion()
        if self._on_selected is not None:
            self._on_selected(self.target.value)
