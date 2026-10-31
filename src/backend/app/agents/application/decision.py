"""Choosing among deterministic options, explaining the choice, and drafting messages.

A decider receives a de-identified context (pseudonymous supplier labels, no names or identifiers) and returns a
`Decision`: one offered option id, a rationale, optional escalation advice and information requests, and message
drafts. `validated` checks every model answer before it is used:
* the option id must be one that was offered, otherwise the deterministic choice is used;
* a rationale or draft citing a number that is not in the evidence is withheld (models may not invent quantities);
* drafts are capped in length and are only ever stored, never sent.
The deterministic decider is always available and is used whenever the model is disabled, fails or is rejected.
"""
import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Protocol

MAX_DRAFT = 800
MAX_RATIONALE = 2000
NUMBER = re.compile(r"(?<![A-Za-z])\d+(?:[.,]\d+)*")


@dataclass
class Decision:
    option_id: str
    rationale: str
    recommend_escalation: bool = False
    information_requests: list[str] = field(default_factory=list)
    supplier_drafts: dict[str, str] = field(default_factory=dict)  # supplier label -> request text
    buyer_draft: str | None = None
    mode: str = "deterministic"
    model: str | None = None
    violations: list[str] = field(default_factory=list)
    fallback_reason: str | None = None


class Decider(Protocol):
    mode: str

    def decide(self, context: dict) -> Decision: ...


def _covered(option: dict) -> Decimal:
    return Decimal(option["standby_activated_kg"]) + Decimal(option["requested_kg"])


def _cost_key(option: dict):
    increase = option["cost"].get("increase_jmd")
    return (not option["cost"]["known"], Decimal(increase) if increase is not None else Decimal("0"))


def deterministic_choice(options: list[dict]) -> dict:
    """Cover the most; then prefer authorized standby (consent already given); then the lowest cost increase."""
    return sorted(options, key=lambda o: (-_covered(o), -Decimal(o["standby_activated_kg"]), _cost_key(o), o["id"]))[0]


def template_supplier_draft(action: dict, crop: str, window: str) -> str:
    return (f"KoroFarm request: could you supply {action['quantity_kg']} kg of {crop} (Grade A) for delivery {window}? "
            f"Please accept or decline in the farmer portal within {action['respond_within_hours']} hours. "
            "No answer is not treated as acceptance.")


def template_buyer_draft(context: dict, option: dict) -> str:
    escalation = Decimal(option["escalation_kg"])
    text = (f"Update on your {context['order']['crop']} order: we have a supply exception of {context['basis']['net_need_kg']} kg "
            f"and a recovery plan is awaiting internal approval.")
    if escalation > 0:
        text += f" {option['escalation_kg']} kg is not yet covered and a coordinator is working on it."
    return text


class DeterministicDecider:
    mode = "deterministic"

    def decide(self, context: dict) -> Decision:
        option = deterministic_choice(context["options"])
        parts = [f"Option {option['id']} ({option['title']}) covers the most of the {context['basis']['net_need_kg']} kg need"]
        if Decimal(option["standby_activated_kg"]) > 0:
            parts.append(f"activating {option['standby_activated_kg']} kg of standby the suppliers already authorized")
        if Decimal(option["requested_kg"]) > 0:
            parts.append(f"asking new suppliers for {option['requested_kg']} kg (a request, not a commitment)")
        if Decimal(option["escalation_kg"]) > 0:
            parts.append(f"leaving {option['escalation_kg']} kg for a coordinator")
        return Decision(option_id=option["id"], rationale="; ".join(parts) + ".", recommend_escalation=Decimal(option["escalation_kg"]) > 0)


def allowed_numbers(context: dict) -> set[str]:
    """Every number that appears anywhere in the evidence given to the model, in normalized form."""
    found: set[str] = set()

    def walk(value):
        if isinstance(value, dict):
            for item in value.values():
                walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)
        elif isinstance(value, (int, float, Decimal)) and not isinstance(value, bool):
            found.add(_norm(str(value)))
        elif isinstance(value, str):
            for match in NUMBER.findall(value):
                found.add(_norm(match))
    walk({k: v for k, v in context.items() if k != "incidents"})
    for incident in context.get("incidents", []):  # incident quantities are evidence; their free text is not
        walk({k: v for k, v in incident.items() if k != "note"})
    return found


def _norm(text: str) -> str:
    try:
        value = Decimal(text.replace(",", ""))
    except InvalidOperation:
        return text
    normalized = format(value.normalize(), "f")
    return normalized


def foreign_numbers(text: str, allowed: set[str]) -> list[str]:
    return [match for match in NUMBER.findall(text or "") if _norm(match) not in allowed]


def validated(raw: Decision, context: dict, fallback: Decision) -> Decision:
    """Apply the safety checks to a model's decision; fall back field by field where it fails."""
    offered = {option["id"] for option in context["options"]}
    if raw.option_id not in offered:
        fallback.violations.append(f"model chose option {raw.option_id!r}, which was not offered")
        fallback.fallback_reason = "invalid option"
        return fallback
    allowed = allowed_numbers(context)
    result = Decision(option_id=raw.option_id, rationale=fallback.rationale, mode=raw.mode, model=raw.model,
                      recommend_escalation=bool(raw.recommend_escalation),
                      information_requests=[item[:300] for item in raw.information_requests[:5]])
    rationale = (raw.rationale or "").strip()[:MAX_RATIONALE]
    invented = foreign_numbers(rationale, allowed)
    if not rationale:
        result.violations.append("model gave no rationale; deterministic summary used")
    elif invented:
        result.violations.append(f"model rationale cited figures not in the evidence ({', '.join(invented[:5])}); withheld")
        if raw.option_id != fallback.option_id:
            result.rationale = f"Model selected option {raw.option_id}. Its explanation was withheld because it cited figures not in the evidence."
    else:
        result.rationale = rationale
    labels = {action["supplier_label"] for option in context["options"] for action in option["actions"]}
    for label, text in (raw.supplier_drafts or {}).items():
        text = (text or "").strip()
        if label not in labels:
            result.violations.append(f"draft for unknown supplier {label!r} discarded")
        elif not text or len(text) > MAX_DRAFT or foreign_numbers(text, allowed):
            result.violations.append(f"draft for {label} discarded (empty, too long or citing figures not in the evidence)")
        else:
            result.supplier_drafts[label] = text
    if raw.buyer_draft:
        text = raw.buyer_draft.strip()
        if len(text) > MAX_DRAFT or foreign_numbers(text, allowed):
            result.violations.append("buyer draft discarded (too long or citing figures not in the evidence)")
        else:
            result.buyer_draft = text
    return result


def model_context(evidence, options: list[dict], incidents: list[dict]) -> dict:
    """What a model may see: quantities, costs, dates, parishes and pseudonymous supplier labels. No names, ids,
    contact details or free-text identifiers of real people. Incident notes are passed as untrusted data."""
    requirement = evidence.requirement
    redacted = []
    for option in options:
        actions = [{"type": a["type"], "supplier_label": a["supplier_label"], "parish": a["parish"],
                    "quantity_kg": a["quantity_kg"],
                    **({"respond_within_hours": a["respond_within_hours"]} if "respond_within_hours" in a else {}),
                    **({"authorization_valid_until": a["authorization_valid_until"]} if "authorization_valid_until" in a else {})}
                   for a in option["actions"]]
        cost = {k: option["cost"].get(k) for k in ("known", "replacement_kg", "total_landed_cost_jmd", "baseline_cost_per_kg_jmd",
                                                     "increase_jmd", "increase_pct")}
        redacted.append({"id": option["id"], "title": option["title"], "actions": actions,
                         "standby_activated_kg": option["standby_activated_kg"], "requested_kg": option["requested_kg"],
                         "escalation_kg": option["escalation_kg"], "cost": cost})
    return {
        "order": {"crop": str(requirement.crop).replace("_", " ").lower(), "grade": requirement.grade.value,
                  "required_kg": evidence.basis.as_dict()["required_kg"],
                  "delivery_window": f"{requirement.delivery_window_start.isoformat()} to {requirement.delivery_window_end.isoformat()}"},
        "basis": evidence.basis.as_dict(),
        "incidents": [{"kind": i["kind"], "quantity_kg": i["quantity_kg"], "note": i.get("note")} for i in incidents],
        "options": redacted,
    }
