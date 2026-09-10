"""Notification channel abstraction + MVP channels.

Channels are Strategy/Adapter implementations: adding Email, Webhook, Discord,
Telegram etc. means registering a new class here — AlertService is untouched.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Protocol

from app.services.alerts.domain import Alert, AlertEvent


class NotificationChannel(Protocol):
    name: str

    async def notify(self, alert: Alert, event: AlertEvent) -> None: ...


@dataclass
class InAppChannel:
    """Records events into an in-memory notification log (visible in TUI)."""

    name: str = "in_app"
    events: list[AlertEvent] = field(default_factory=list)

    async def notify(self, alert: Alert, event: AlertEvent) -> None:
        self.events.append(event)


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
            await channel.notify(alert, event)


def default_channels() -> dict[str, NotificationChannel]:
    in_app = InAppChannel()
    return {
        "in_app": in_app,
        "toast": NoopChannel("toast"),
        "sound": NoopChannel("sound"),
        "push": NoopChannel("push"),
        "email": NoopChannel("email"),
    }