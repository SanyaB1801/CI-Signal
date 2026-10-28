"""End-to-end evaluations over the actual local A2A agents."""

from __future__ import annotations

import asyncio
import json
import sys
from typing import Any

from .coordinator import investigate
from .runtime import start_agents
from .scenarios import load_scenarios


CASES = {
    "regression": {"expected": "regression", "required_evidence": ("AssertionError",)},
    "flaky": {"expected": "flaky", "required_evidence": ("ReadTimeout",)},
    "environment": {"expected": "environment", "required_evidence": ("ModuleNotFoundError",)},
    "unknown": {"expected": "inconclusive", "required_evidence": ()},
}


async def _evaluate(agents: dict[str, str]) -> list[dict[str, Any]]:
    scenarios = {scenario["id"]: scenario for scenario in load_scenarios()}
    results: list[dict[str, Any]] = []
    for scenario_id, expectations in CASES.items():
        scenario = scenarios[scenario_id]
        result = await investigate(
            log=scenario["log"],
            attempts=scenario["attempts"],
            agent_urls=agents,
        )
        diagnosis = result["diagnosis"]
        trace = result["trace"]
        evidence_text = "\n".join(item.get("text", "") for item in diagnosis["evidence"])
        task_events = [event for event in trace if event["type"] == "task"]
        discovery_events = [event for event in trace if event["type"] == "discovery"]

        checks = {
            "classification": diagnosis["classification"] == expectations["expected"],
            "evidence": all(token.lower() in evidence_text.lower() for token in expectations["required_evidence"]),
            "two_agents_discovered": len(discovery_events) == 2,
            "two_tasks_completed": len(task_events) == 2 and all(
                event["state"] in {"TASK_STATE_COMPLETED", "completed"} for event in task_events
            ),
            "test_name_grounded": diagnosis["test_name"] is None or diagnosis["test_name"].startswith("tests/"),
        }
        results.append({
            "scenario": scenario_id,
            "expected": expectations["expected"],
            "actual": diagnosis["classification"],
            "confidence": diagnosis["confidence"],
            "reason": diagnosis["reason"],
            "trace": trace,
            "checks": checks,
            "passed": all(checks.values()),
        })

    unavailable_urls = {
        "failure": agents["failure"],
        "stability": "http://127.0.0.1:1",
    }
    regression = scenarios["regression"]
    partial = await investigate(
        log=regression["log"],
        attempts=regression["attempts"],
        agent_urls=unavailable_urls,
    )
    partial_trace = partial["trace"]
    failure_event = next((event for event in partial_trace if event.get("type") == "agent_error"), {})
    partial_checks = {
        "partial_result_is_inconclusive": partial["diagnosis"]["classification"] == "inconclusive",
        "failure_evidence_preserved": any(item.get("text", "").find("AssertionError") >= 0 for item in partial["diagnosis"]["evidence"]),
        "unavailable_agent_visible_in_trace": failure_event.get("agent_key") == "stability" and failure_event.get("state") == "unavailable",
    }
    results.append({
        "scenario": "stability_agent_unavailable",
        "expected": "inconclusive",
        "actual": partial["diagnosis"]["classification"],
        "confidence": partial["diagnosis"]["confidence"],
        "reason": partial["diagnosis"]["reason"],
        "trace": partial_trace,
        "checks": partial_checks,
        "passed": all(partial_checks.values()),
    })
    return results


def run_evals() -> int:
    runtime = start_agents(port_offset=100)
    try:
        results = asyncio.run(_evaluate(runtime.urls))
    finally:
        runtime.stop()

    passed = sum(bool(result["passed"]) for result in results)
    total_checks = sum(len(result["checks"]) for result in results)
    passed_checks = sum(sum(bool(value) for value in result["checks"].values()) for result in results)
    print("CI Signal - A2A evaluation report")
    print("=" * 35)
    for result in results:
        status = "PASS" if result["passed"] else "FAIL"
        print(f"{status:4} {result['scenario']:<14} expected={result['expected']:<13} actual={result['actual']:<13} confidence={result['confidence']:.2f}")
        for name, check in result["checks"].items():
            print(f"       {'PASS' if check else 'FAIL'} {name}")
        if not result["passed"]:
            print(f"       reason: {result['reason']}")
            print(f"       trace: {json.dumps(result['trace'], ensure_ascii=True)}")
    print(f"\nScenarios: {passed}/{len(results)} passed; checks: {passed_checks}/{total_checks} passed.")
    return 0 if passed == len(results) else 1


def main() -> None:
    sys.exit(run_evals())
