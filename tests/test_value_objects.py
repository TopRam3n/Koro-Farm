from datetime import date
from decimal import Decimal

import pytest

from app.domain.common import DateWindow, MoneyJmd, QuantityKg


def test_negative_quantity_rejected() -> None:
    with pytest.raises(ValueError, match="cannot be negative"):
        QuantityKg(Decimal("-0.001"))


def test_negative_money_rejected() -> None:
    with pytest.raises(ValueError, match="cannot be negative"):
        MoneyJmd("-1")


def test_invalid_date_window_rejected() -> None:
    with pytest.raises(ValueError, match="end must be"):
        DateWindow(date(2026, 8, 20), date(2026, 8, 19))
