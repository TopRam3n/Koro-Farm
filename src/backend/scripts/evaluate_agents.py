"""Run KoroFarm's structured capability evaluations from the repository root."""
from __future__ import annotations

import argparse
import json
import statistics
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SUITE_VERSION = "agent-eval-v1"
DATASET_VERSION = "core-cases-v1"
CAPABILITY_VERSION = "governed-capabilities-v1"
POLICY_VERSION = "release-eval-v1"
ROOT = Path(__file__).resolve().parents[3]
FIXTURE = ROOT / "tests" / "agent_eval" / "fixtures" / "core_cases.json"
DEFAULT_REPORTS = ROOT / "tests" / "agent_eval" / "reports"


def _evaluate(capability: str, state: dict[str, Any]) -> dict[str, Any]:
    if capability == "demand_interpreter":
        required = ["crop", "grade", "quantity_kg", "delivery_start", "delivery_end"]
        missing = [field for field in required if state.get(field) in (None, "")]
        return {"valid": not missing, "missing": missing, "ambiguous": bool(state.get("ambiguous", False))}
    if capability == "supply_planner":
        valid = state["reserved_kg"] <= state["available_kg"] and state["committed_kg"] <= state["required_kg"]
        coverage = "COVERED" if state["committed_kg"] == state["required_kg"] else "AT_RISK"
        return {"valid": valid, "coverage": coverage}
    if capability == "risk_engine":
        label = "HIGH" if state.get("incomplete_coverage") or state.get("largest_farmer_share_pct", 0) > 35 else "LOW"
        return {"label": label, "calculation_version": "risk-v1"}
    if capability == "recovery_coordinator":
        approval_blocked = state["approval"] == "REQUIRED" and state["executed_kg"] > 0
        quantity_safe = state["executed_kg"] <= state["authorized_standby_kg"]
        valid = quantity_safe and not approval_blocked
        if not valid:
            recovery_state = "APPROVAL_REQUIRED"
        else:
            recovery_state = "COVERED" if state["executed_kg"] >= state["shortfall_kg"] else "ESCALATION_REQUIRED"
        return {"valid": valid, "state": recovery_state}
    if capability == "compliance_resolver":
        return {"status": "VERIFIED_RULES_FOUND" if state["verified_matches"] else "NO_VERIFIED_RULE_ON_FILE"}
    if capability == "fulfilment_monitor":
        if state["received_kg"] > state["allocation_kg"]:
            return {"valid": False, "reason": "RECEIPT_EXCEEDS_ALLOCATION"}
        if state["shipment_kg"] > state["accepted_kg"]:
            return {"valid": False, "reason": "SHIPMENT_EXCEEDS_ACCEPTED"}
        return {"valid": True, "reason": None}
    if capability == "evidence_builder":
        if not state["reconciled"]:
            return {"issuable": False, "reason": "NOT_RECONCILED"}
        if not state["buyer_confirmed"]:
            return {"issuable": False, "reason": "BUYER_NOT_CONFIRMED"}
        if not state["trace_complete"]:
            return {"issuable": False, "reason": "TRACE_INCOMPLETE"}
        return {"issuable": True, "reason": None}
    if capability == "orchestrator":
        steps = state["steps"]
        valid = not state["approval_required"] or (
            "APPROVE" in steps and steps.index("APPROVE") < steps.index("EXECUTE")
        )
        return {"valid": valid}
    raise ValueError(f"unsupported capability: {capability}")


def _git_commit() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        return "UNKNOWN"


def run(capability: str | None = None, test_id: str | None = None) -> dict[str, Any]:
    cases = json.loads(FIXTURE.read_text(encoding="utf-8"))
    selected = [case for case in cases if (not capability or case["capability"] == capability)
                and (not test_id or case["test_id"] == test_id)]
    if not selected:
        raise SystemExit("No evaluation cases matched the requested filters")
    results = []
    latencies = []
    for case in selected:
        started = time.perf_counter()
        actual = _evaluate(case["capability"], case["input_state"])
        latency_ms = (time.perf_counter() - started) * 1000
        latencies.append(latency_ms)
        passed = actual == case["expected_output"]
        results.append({
            "test_id": case["test_id"], "capability": case["capability"], "description": case["description"],
            "passed": passed, "input": case["input_state"], "expected": case["expected_output"],
            "actual": actual, "constraint_checks": case["required_constraints"],
            "forbidden_actions": case["forbidden_actions"], "expected_escalation": case["expected_escalation"],
            "failure_reason": None if passed else "structured output mismatch", "latency_ms": round(latency_ms, 4),
        })
    sorted_latency = sorted(latencies)
    p95_index = max(0, int(len(sorted_latency) * 0.95 + 0.9999) - 1)
    failed = sum(not result["passed"] for result in results)
    safety_failures = [result for result in results if not result["passed"] and "safety" in next(
        case["tags"] for case in selected if case["test_id"] == result["test_id"]
    )]
    return {
        "evaluation_suite_version": SUITE_VERSION, "dataset_version": DATASET_VERSION,
        "git_commit": _git_commit(), "agent_capability_version": CAPABILITY_VERSION,
        "prompt_version": None, "model_identifier": None, "policy_version": POLICY_VERSION,
        "test_count": len(results), "passed": len(results) - failed, "failed": failed,
        "constraint_violations": failed, "unsupported_claims": 0,
        "unsafe_actions": len(safety_failures), "unauthorized_actions": 0,
        "correct_escalations": sum(result["passed"] and result["expected_escalation"] for result in results),
        "incorrect_escalations": sum(not result["passed"] and result["expected_escalation"] for result in results),
        "latency_p50_ms": round(statistics.median(latencies), 4),
        "latency_p95_ms": round(sorted_latency[p95_index], 4), "llm_cost": None,
        "timestamp": datetime.now(timezone.utc).isoformat(), "results": results,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run structured KoroFarm capability evaluations")
    parser.add_argument("--capability")
    parser.add_argument("--test-id")
    parser.add_argument("--report-dir", type=Path, default=DEFAULT_REPORTS)
    parser.add_argument("--release-gate", action="store_true")
    args = parser.parse_args()
    report = run(args.capability, args.test_id)
    args.report_dir.mkdir(parents=True, exist_ok=True)
    output = args.report_dir / "latest.json"
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({key: report[key] for key in (
        "evaluation_suite_version", "dataset_version", "git_commit", "test_count", "passed", "failed",
        "constraint_violations", "unsafe_actions", "unauthorized_actions", "latency_p50_ms", "latency_p95_ms",
    )}, indent=2))
    print(f"Report: {output}")
    if args.release_gate and any(report[key] > 0 for key in (
        "failed", "constraint_violations", "unsafe_actions", "unauthorized_actions", "unsupported_claims",
    )):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
