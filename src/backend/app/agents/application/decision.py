"""Choosing among deterministic options, explaining the choice, and drafting messages (provider-independent).

A decider receives a de-identified context (pseudonymous supplier labels, no names or identifiers) and returns a
`Decision`: one offered option id, a rationale, optional escalation advice and information requests, and message
drafts. A model's answer passes three checks before anything is used:
1. `parse_answer`: exactly one JSON object matching `DecisionAnswer` (strict types, no extra fields, bounded lengths);
2. the option id must be one that was offered, otherwise the deterministic choice is used;
3. `validated`: a rationale, draft or information request is withheld when it cites a number not in the evidence or
   makes an unsupported claim (`claim_findings`: regulatory, commercial, state, contact channel, unknown party, or
   text echoed from untrusted incident notes). Drafts are only ever stored, never sent.
The deterministic decider is always available and is used whenever the model is disabled, fails or is rejected.
"""
import json
import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Annotated, Protocol

from pydantic import BaseModel, ConfigDict, Field, ValidationError

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
    call: dict | None = None  # model call record: provider, model, latency, usage, cost, outcome (never reasoning)


class Decider(Protocol):
    mode: str
    external: bool  # True when deciding calls an external service (decided outside database transactions)

    def decide(self, context: dict) -> Decision: ...


# --- Strict answer schema ----------------------------------------------------------------------------------------

class SupplierDraft(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    supplier_label: str = Field(min_length=1, max_length=10)
    message: str = Field(max_length=MAX_DRAFT)


class DecisionAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    option_id: str = Field(min_length=1, max_length=10)
    rationale: str = Field(max_length=MAX_RATIONALE)
    recommend_escalation: bool
    information_requests: list[Annotated[str, Field(max_length=300)]] = Field(max_length=5)
    supplier_drafts: list[SupplierDraft] = Field(max_length=10)
    buyer_draft: str = Field(max_length=MAX_DRAFT)


# Sent to providers that accept a JSON schema, and repeated in every prompt. Length limits are enforced locally.
DECISION_SCHEMA = {
    "type": "object",
    "properties": {
        "option_id": {"type": "string"},
        "rationale": {"type": "string"},
        "recommend_escalation": {"type": "boolean"},
        "information_requests": {"type": "array", "items": {"type": "string"}},
        "supplier_drafts": {"type": "array", "items": {
            "type": "object",
            "properties": {"supplier_label": {"type": "string"}, "message": {"type": "string"}},
            "required": ["supplier_label", "message"], "additionalProperties": False}},
        "buyer_draft": {"type": "string"},
    },
    "required": ["option_id", "rationale", "recommend_escalation", "information_requests", "supplier_drafts", "buyer_draft"],
    "additionalProperties": False,
}

_FENCE = re.compile(r"^```(?:json)?\s*(.*?)\s*```$", re.DOTALL | re.IGNORECASE)


class AnswerFormatError(ValueError):
    pass


def parse_answer(text: str) -> DecisionAnswer:
    """Exactly one JSON object and nothing else (a single code fence around it is tolerated)."""
    body = (text or "").strip()
    fenced = _FENCE.match(body)
    if fenced:
        body = fenced.group(1).strip()
    try:
        data = json.loads(body)
    except json.JSONDecodeError as exc:
        raise AnswerFormatError("the answer is not a single JSON object") from exc
    if not isinstance(data, dict):
        raise AnswerFormatError("the answer is not a JSON object")
    try:
        return DecisionAnswer.model_validate(data)
    except ValidationError as exc:
        fields = sorted({".".join(str(p) for p in error["loc"]) or "answer" for error in exc.errors()})
        raise AnswerFormatError(f"the answer does not match the decision schema ({', '.join(fields)[:200]})") from exc


def to_decision(answer: DecisionAnswer, model: str | None) -> Decision:
    return Decision(option_id=answer.option_id, rationale=answer.rationale, recommend_escalation=answer.recommend_escalation,
                    information_requests=list(answer.information_requests),
                    supplier_drafts={d.supplier_label: d.message for d in answer.supplier_drafts},
                    buyer_draft=answer.buyer_draft or None, mode="model", model=model)


# --- Deterministic choice --------------------------------------------------------------------------------------

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
    external = False

    def __init__(self, configuration_error: str | None = None):
        # Set when a model provider was configured but cannot be used; recorded on every decision.
        self.configuration_error = configuration_error

    def decide(self, context: dict) -> Decision:
        option = deterministic_choice(context["options"])
        parts = [f"Option {option['id']} ({option['title']}) covers the most of the {context['basis']['net_need_kg']} kg need"]
        if Decimal(option["standby_activated_kg"]) > 0:
            parts.append(f"activating {option['standby_activated_kg']} kg of standby the suppliers already authorized")
        if Decimal(option["requested_kg"]) > 0:
            parts.append(f"asking new suppliers for {option['requested_kg']} kg (a request, not a commitment)")
        if Decimal(option["escalation_kg"]) > 0:
            parts.append(f"leaving {option['escalation_kg']} kg for a coordinator")
        decision = Decision(option_id=option["id"], rationale="; ".join(parts) + ".",
                            recommend_escalation=Decimal(option["escalation_kg"]) > 0)
        if self.configuration_error:
            decision.fallback_reason = f"model provider configured but unusable: {self.configuration_error}"
        return decision


# --- Numbers -----------------------------------------------------------------------------------------------------

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
    return format(value.normalize(), "f")


def foreign_numbers(text: str, allowed: set[str]) -> list[str]:
    return [match for match in NUMBER.findall(text or "") if _norm(match) not in allowed]


# --- Claims that are not numbers ----------------------------------------------------------------------------------

_RULES: list[tuple[str, re.Pattern]] = [
    # The model never sees authoritative trade rules, so any regulatory or certification statement is unsupported.
    ("regulatory", re.compile(r"\b(phyto\w*|certif\w*|complian\w*|compliant|compl(?:y|ies)\s+with|regulat\w*|organic|"
                              r"globalg\.?a\.?p|g\.a\.p\b|residues?|mrls?\b|customs|quarantine|import\s+(?:rules?|requirements?|permits?|licen[cs]es?)|"
                              r"export\s+(?:rules?|requirements?|permits?|licen[cs]es?)|meets?\s+(?:the\s+)?\w+\s+(?:rules|requirements|standards)|"
                              r"food[\s-]safety|inspection\s+(?:passed|cleared)|approved\s+for\s+(?:import|export))", re.IGNORECASE)),
    ("commercial", re.compile(r"\b(guarantee\w*|promis\w*|discount\w*|premiums?|penalt\w*|refund\w*|compensat\w*|"
                              r"pay(?:s|ing|ment|ments)?|paid|bonus\w*|incentive\w*|rebate\w*|contract\s+price|price\s+(?:of|per|at))\b", re.IGNORECASE)),
    ("state", re.compile(r"\b(confirmed|(?:has|have|was|were|been|already)\s+(?:shipped|dispatched|delivered|agreed|committed|secured)|"
                         r"shipped|dispatched|on\s+(?:its|the)\s+way|in\s+transit|locked\s+in|secured)\b", re.IGNORECASE)),
    ("contact_channel", re.compile(r"\b(whats\s?app|sms|text\s+message|e-?mail(?:ed|s)?|phoned|telephoned|"
                                   r"(?:we|i)\s+(?:have|'ve|has)\s+(?:contacted|messaged|notified|called|informed)|"
                                   r"sent\s+(?:a|an|the)\s+(?:message|notification|text))\b", re.IGNORECASE)),
]
_LABEL = re.compile(r"\bS\d{1,3}\b")
_URL = re.compile(r"https?://|www\.", re.IGNORECASE)
_WORD = re.compile(r"[a-z0-9']+")
ECHO_WORDS = 6  # a run of this many consecutive words copied from an incident note counts as echoing it


def _shingles(text: str) -> set[tuple[str, ...]]:
    words = _WORD.findall(text.lower())
    return {tuple(words[i:i + ECHO_WORDS]) for i in range(len(words) - ECHO_WORDS + 1)}


def claim_findings(text: str, context: dict) -> list[tuple[str, str]]:
    """Unsupported claims in model-written text: (category, matched text). Deterministic and auditable."""
    if not text:
        return []
    found = [(category, match.group(0)) for category, pattern in _RULES for match in [pattern.search(text)] if match]
    labels = {a["supplier_label"] for option in context.get("options", []) for a in option.get("actions", [])}
    unknown = sorted({label for label in _LABEL.findall(text) if label not in labels})
    if unknown:
        found.append(("unknown_party", ", ".join(unknown)))
    if _URL.search(text):
        found.append(("echoed_note", "link"))
    notes = [i.get("note") or "" for i in context.get("incidents", [])]
    own = _shingles(text)
    for note in notes:
        overlap = own & _shingles(note)
        if overlap:
            found.append(("echoed_note", " ".join(sorted(overlap)[0])))
            break
    return found


def _problems(text: str, context: dict, allowed: set[str]) -> list[str]:
    problems = [f"{category} ({match[:60]})" for category, match in claim_findings(text, context)]
    invented = foreign_numbers(text, allowed)
    if invented:
        problems.append(f"figures not in the evidence ({', '.join(invented[:5])})")
    return problems


def validated(raw: Decision, context: dict, fallback: Decision) -> Decision:
    """Apply the safety checks to a model's decision; fall back field by field where it fails."""
    offered = {option["id"] for option in context["options"]}
    if raw.option_id not in offered:
        fallback.violations.append(f"model chose option {raw.option_id!r}, which was not offered")
        fallback.fallback_reason = "invalid option"
        fallback.call = raw.call
        return fallback
    allowed = allowed_numbers(context)
    result = Decision(option_id=raw.option_id, rationale=fallback.rationale, mode=raw.mode, model=raw.model,
                      recommend_escalation=bool(raw.recommend_escalation), call=raw.call)
    rationale = (raw.rationale or "").strip()[:MAX_RATIONALE]
    problems = _problems(rationale, context, allowed)
    if not rationale:
        result.violations.append("model gave no rationale; deterministic summary used")
    elif problems:
        result.violations.append(f"model rationale withheld: {'; '.join(problems)}")
        if raw.option_id != fallback.option_id:
            result.rationale = f"Model selected option {raw.option_id}. Its explanation was withheld: {'; '.join(problems)}."
    else:
        result.rationale = rationale
    for item in raw.information_requests[:5]:
        issues = _problems(item, context, allowed)
        if issues:
            result.violations.append(f"information request withheld: {'; '.join(issues)}")
        else:
            result.information_requests.append(item[:300])
    labels = {action["supplier_label"] for option in context["options"] for action in option["actions"]}
    for label, text in (raw.supplier_drafts or {}).items():
        text = (text or "").strip()
        issues = _problems(text, context, allowed) if text else ["empty"]
        if label not in labels:
            result.violations.append(f"draft for unknown supplier {label!r} discarded")
        elif len(text) > MAX_DRAFT or issues:
            result.violations.append(f"draft for {label} discarded: {'; '.join(issues) or 'too long'}")
        else:
            result.supplier_drafts[label] = text
    if raw.buyer_draft:
        text = raw.buyer_draft.strip()
        issues = _problems(text, context, allowed)
        if len(text) > MAX_DRAFT or issues:
            result.violations.append(f"buyer draft discarded: {'; '.join(issues) or 'too long'}")
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
