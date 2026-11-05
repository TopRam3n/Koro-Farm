"""Message templates, versioned in code so every sent text is reviewable in git (R1 WP5, M3).

A template names its purpose (the consent purpose the recipient must have granted) and the only fields it may use.
Rendering refuses unknown fields and truncates to MAX_LENGTH, so a template can never pull in data it was not
reviewed for. Changing wording means adding a new version, never editing one in place: each notification records the
key and version it was rendered from.

Wording is a draft for product-owner review (consent wording and channel are decisions still open, WP5 §4).
"""
from dataclasses import dataclass
from string import Formatter

from src.backend.app.notifications.domain.models import NotificationPurpose

MAX_LENGTH = 480  # three SMS segments; long enough for every template below


@dataclass(frozen=True)
class Template:
    key: str
    version: int
    purpose: NotificationPurpose
    text: str

    def fields(self) -> set[str]:
        return {name for _, name, _, _ in Formatter().parse(self.text) if name}

    def render(self, values: dict[str, str]) -> str:
        missing = self.fields() - set(values)
        if missing:
            raise ValueError(f"template {self.key} v{self.version} needs {sorted(missing)}")
        text = self.text.format(**{name: str(values[name]) for name in self.fields()})
        return text if len(text) <= MAX_LENGTH else text[: MAX_LENGTH - 1] + "…"


TEMPLATES: dict[str, Template] = {t.key: t for t in (
    Template("SUPPLIER_REQUEST", 1, NotificationPurpose.SUPPLY_REQUESTS,
             "{organization}: can you supply {quantity_kg} kg of {crop}? Please reply by {due}. "
             "Answer in your KoroFarm portal or tell your coordinator. Nothing is agreed until you accept."),
    Template("SUPPLIER_REMINDER", 1, NotificationPurpose.SUPPLY_REQUESTS,
             "{organization}: reminder, we are waiting for your answer about {quantity_kg} kg of {crop} by {due}. "
             "No answer is not taken as yes or no."),
    Template("SUPPLIER_DEADLINE_CHANGED", 1, NotificationPurpose.SUPPLY_REQUESTS,
             "{organization}: the reply date for {quantity_kg} kg of {crop} is now {due}."),
    Template("RELEASE_AGREEMENT_RECORDED", 1, NotificationPurpose.RELEASE_AGREEMENTS,
             "{organization}: we recorded that you agreed to release {quantity_kg} kg of {crop} from an order. "
             "If this is wrong, contact your coordinator."),
    Template("BUYER_DELIVERY_RECORDED", 1, NotificationPurpose.DELIVERY_UPDATES,
             "{organization}: a delivery of {quantity_kg} kg of {crop} (shipment {reference}) was recorded. "
             "Please confirm what you received in your KoroFarm account."),
)}
