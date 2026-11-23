from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from enum import StrEnum


def _decimal(value: Decimal | int | str, field: str) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{field} must be a decimal value") from exc


@dataclass(frozen=True)
class QuantityKg:
    value: Decimal

    def __post_init__(self) -> None:
        value = _decimal(self.value, "quantity")
        if value < 0:
            raise ValueError("quantity cannot be negative")
        object.__setattr__(self, "value", value)


@dataclass(frozen=True)
class MoneyJmd:
    value: Decimal

    def __post_init__(self) -> None:
        value = _decimal(self.value, "money")
        if value < 0:
            raise ValueError("money cannot be negative")
        object.__setattr__(self, "value", value.quantize(Decimal("0.01")))


@dataclass(frozen=True)
class DateWindow:
    start: date
    end: date

    def __post_init__(self) -> None:
        if self.end < self.start:
            raise ValueError("date window end must be on or after its start")


class Crop(StrEnum):
    """Codes seeded into the shared crop catalogue. The catalogue (crops table) is authoritative."""
    BANANA = "BANANA"
    BREADFRUIT = "BREADFRUIT"
    CALLALOO = "CALLALOO"
    CASSAVA = "CASSAVA"
    GINGER = "GINGER"
    MANGO = "MANGO"
    PLANTAIN = "PLANTAIN"
    SCOTCH_BONNET = "SCOTCH_BONNET"
    SWEET_POTATO = "SWEET_POTATO"
    YAM = "YAM"


class Grade(StrEnum):
    A = "A"
    B = "B"


class AvailabilityConfidence(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


CROP_CODE_PATTERN = r"^[A-Z][A-Z0-9_]{1,63}$"


class CropCode(str):
    """A crop catalogue code (``crops.code``), e.g. ``GINGER`` or ``SCOTCH_BONNET``.

    Crops are configurable records, not a fixed enum. ``.value`` is kept so existing callers written
    against the old ``Crop`` enum keep working.
    """

    @property
    def value(self) -> str:
        return str(self)
