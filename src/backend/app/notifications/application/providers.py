"""Notification providers (R1 WP5, M3). No real messaging provider is connected.

* `none` (default everywhere): nothing is sent; each queued message is marked NOT_SENT_PROVIDER_DISABLED, so it is
  visible that it would have gone out.
* `synthetic`: never touches the network. It records what would have been sent in memory (for tests and staging
  rehearsals) and reports SENT, or FAILED for an address ending in "-fail", to exercise the failure path.
  Refused in production (core/config.py).
A real provider (SMS, WhatsApp or email) is added later behind the same `send` signature, after the channel,
provider, consent wording and a data processing review are approved (docs/integrations/MESSAGING.md).
"""
from dataclasses import dataclass, field
from typing import Protocol

from src.backend.app.core.config import notification_provider_name


@dataclass(frozen=True)
class OutboundMessage:
    notification_id: str
    channel: str
    address: str
    body: str


@dataclass(frozen=True)
class ProviderResult:
    accepted: bool
    provider_message_id: str | None = None
    error: str | None = None
    permanent: bool = False  # a permanent refusal is not retried


class NotificationProvider(Protocol):
    name: str
    sends: bool  # False: the provider is a stand-in and nothing can leave the system

    def send(self, message: OutboundMessage) -> ProviderResult: ...


class DisabledProvider:
    name = "none"
    sends = False

    def send(self, message: OutboundMessage) -> ProviderResult:
        return ProviderResult(accepted=False, error="notification provider disabled", permanent=True)


@dataclass
class SyntheticProvider:
    name: str = "synthetic"
    sends: bool = False
    outbox: list[OutboundMessage] = field(default_factory=list)

    def send(self, message: OutboundMessage) -> ProviderResult:
        if message.address.endswith("-fail"):
            return ProviderResult(accepted=False, error="synthetic failure for a test address")
        self.outbox.append(message)
        return ProviderResult(accepted=True, provider_message_id=f"synthetic-{message.notification_id}")


_synthetic = SyntheticProvider()


def configured_provider() -> NotificationProvider:
    return _synthetic if notification_provider_name() == "synthetic" else DisabledProvider()
