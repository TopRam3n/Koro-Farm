from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol
from uuid import uuid4


@dataclass(frozen=True)
class MessageResult:
    provider: str
    provider_reference: str
    delivery_state: str
    sent_at: datetime


class MessagingProvider(Protocol):
    def send(self, destination: str, body: str) -> MessageResult: ...


class ConsoleMessagingProvider:
    """Development-only provider. It makes no external delivery claim."""

    def send(self, destination: str, body: str) -> MessageResult:
        print(f"[KoroFarm console message] destination={destination} body={body}")
        return MessageResult(
            provider="CONSOLE_DEVELOPMENT", provider_reference=f"console-{uuid4()}",
            delivery_state="LOGGED_NOT_DELIVERED", sent_at=datetime.now(timezone.utc),
        )
