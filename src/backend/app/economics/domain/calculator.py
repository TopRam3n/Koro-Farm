from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

from src.backend.app.economics.domain.models import LotCostInput

MONEY_QUANTUM = Decimal("0.01")


def money(value: Decimal) -> Decimal:
    return value.quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class CostBreakdown:
    produce_cost_jmd: Decimal = Decimal("0")
    pickup_cost_jmd: Decimal = Decimal("0")
    handling_cost_jmd: Decimal = Decimal("0")
    packaging_cost_jmd: Decimal = Decimal("0")
    transport_cost_jmd: Decimal = Decimal("0")
    expected_rejection_cost_jmd: Decimal = Decimal("0")

    @property
    def total_landed_cost_jmd(self) -> Decimal:
        return money(
            self.produce_cost_jmd + self.pickup_cost_jmd + self.handling_cost_jmd + self.packaging_cost_jmd
            + self.transport_cost_jmd + self.expected_rejection_cost_jmd
        )

    def plus(self, other: "CostBreakdown") -> "CostBreakdown":
        return CostBreakdown(*(
            getattr(self, name) + getattr(other, name) for name in self.__dataclass_fields__
        ))


def allocation_cost(quantity_kg: Decimal, inputs: LotCostInput) -> CostBreakdown:
    produce = quantity_kg * inputs.farmgate_price_per_kg_jmd
    return CostBreakdown(
        produce_cost_jmd=money(produce),
        pickup_cost_jmd=money(inputs.pickup_cost_jmd),
        handling_cost_jmd=money(quantity_kg * inputs.handling_grading_cost_per_kg_jmd),
        packaging_cost_jmd=money(quantity_kg * inputs.packaging_cost_per_kg_jmd),
        transport_cost_jmd=money(inputs.transport_cost_jmd),
        expected_rejection_cost_jmd=money(produce * inputs.expected_rejection_pct),
    )
