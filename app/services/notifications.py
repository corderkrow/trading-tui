"""Notification channel abstraction + MVP channels.

Channels are Strategy/Adapter implementations: adding Email, Webhook, Discord,
Telegram etc. means registering a new class here — AlertService is untouched.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Callable
from typing import Protocol

from app.services.alerts.domain import Alert, AlertEvent

MAX_IN_APP_EVENTS = 1000


class NotificationChannel(Protocol):
    name: str

    async def notify(self, alert: Alert, event: AlertEvent) -> None: ...


class InAppChannel:
    """Records events into a bounded in-memory ring buffer (visible in TUI/API).

    Oldest events fall off the end once `maxlen` is reached; `recent()` reads
    them back newest-first.
    """

    def __init__(self, name: str = "in_app", maxlen: int = MAX_IN_APP_EVENTS) -> None:
        self.name = name
        self._events: deque[AlertEvent] = deque(maxlen=maxlen)

    @property
    def events(self) -> list[AlertEvent]:
        return list(self._events)

    def recent(self, limit: int = 50) -> list[AlertEvent]:
        """Last `limit` events, newest first."""
        items = list(self._events)
        return items[-limit:][::-1]

    async def notify(self, alert: Alert, event: AlertEvent) -> None:
        self._events.append(event)


class NoopChannel:
    """Toast/Sound placeholders — no external integration in the MVP."""

    def __init__(self, name: str):
        self.name = name

    async def notify(self, alert: Alert, event: AlertEvent) -> None:
        return None


class NotificationService:
    """Fans an AlertEvent out to the channels configured on the alert.

    An optional `delivery_filter` (re-read per dispatch) restricts which
    channels may fire — used to apply the user's global delivery preference.
    """

    def __init__(
        self,
        channels: dict[str, NotificationChannel] | None = None,
        delivery_filter: Callable[[], set[str] | None] | None = None,
    ) -> None:
        self.channels: dict[str, NotificationChannel] = channels or default_channels()
        self._delivery_filter = delivery_filter

    @property
    def channel_names(self) -> set[str]:
        return set(self.channels)

    async def dispatch(self, alert: Alert, event: AlertEvent) -> None:
        allowed = self._delivery_filter() if self._delivery_filter else None
        for name in alert.notification_channels:
            if allowed is not None and name not in allowed:
                continue
            channel = self.channels.get(name)
            if channel is None:
                continue
            try:
                await channel.notify(alert, event)
            except Exception:
                # One broken channel must not stop the others (or the caller).
                # MVP channels are local; log to stderr for diagnosis.
                import sys

                print(
                    f"notification channel '{name}' failed: {sys.exc_info()[1]}",
                    file=sys.stderr,
                )


def default_channels() -> dict[str, NotificationChannel]:
    in_app = InAppChannel()
    return {
        "in_app": in_app,
        "toast": NoopChannel("toast"),
        "sound": NoopChannel("sound"),
        "push": NoopChannel("push"),
        "email": NoopChannel("email"),
        "webhook": NoopChannel("webhook"),
    }