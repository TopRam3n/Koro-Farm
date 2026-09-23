from src.backend.scripts.evaluate_agents import run


def test_complete_agent_evaluation_suite_has_zero_safety_failures() -> None:
    report = run()
    assert report["test_count"] >= 18
    assert report["failed"] == 0
    assert report["constraint_violations"] == 0
    assert report["unsafe_actions"] == 0
    assert report["unauthorized_actions"] == 0
    assert report["unsupported_claims"] == 0


def test_agent_evaluation_filters_by_capability_and_case() -> None:
    capability = run(capability="compliance_resolver")
    assert capability["test_count"] == 1
    assert capability["results"][0]["actual"]["status"] == "NO_VERIFIED_RULE_ON_FILE"
    case = run(test_id="orchestrator-002")
    assert case["test_count"] == 1
    assert case["passed"] == 1
