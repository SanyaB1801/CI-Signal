"""A2A server implementations for the two CI triage specialists."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from typing import Any

from a2a.helpers import get_message_text, new_task_from_user_message, new_text_message, new_text_part
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.tasks import TaskUpdater
from a2a.types import Role, TaskState


def _evidence_lines(log: str, needles: tuple[str, ...]) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []
    for line_number, line in enumerate(log.splitlines(), start=1):
        if any(needle.lower() in line.lower() for needle in needles):
            evidence.append({"line": line_number, "text": line.strip()})
    return evidence[:5]


def inspect_failure(payload: dict[str, Any]) -> dict[str, Any]:
    """Extract a small, traceable failure signature from a CI log."""
    log = str(payload.get("log", ""))
    if not log.strip():
        return {
            "failure_type": "unknown",
            "test_name": None,
            "signature": "no-log-content",
            "evidence": [],
        }

    test_match = re.search(r"(?m)^\s*(tests?/[^\s:]+::[^\s]+).*?(?:FAILED|ERROR)", log)
    test_name = test_match.group(1) if test_match else None

    patterns = (
        ("environment", ("ModuleNotFoundError", "ImportError", "No module named", "command not found")),
        ("timeout", ("ReadTimeout", "TimeoutError", "timed out", "deadline exceeded")),
        ("network", ("ConnectionError", "ConnectionRefusedError", "Temporary failure in name resolution")),
        ("assertion", ("AssertionError", "assert ", "E       assert")),
    )
    for failure_type, needles in patterns:
        evidence = _evidence_lines(log, needles)
        if evidence:
            signature = failure_type
            if failure_type == "environment":
                signature = "missing-dependency"
            return {
                "failure_type": failure_type,
                "test_name": test_name,
                "signature": signature,
                "evidence": evidence,
            }

    failure_line = _evidence_lines(log, ("FAILED", "ERROR", "Traceback", "exit status"))
    return {
        "failure_type": "unknown",
        "test_name": test_name,
        "signature": "unclassified-failure",
        "evidence": failure_line,
    }


def assess_stability(payload: dict[str, Any]) -> dict[str, Any]:
    """Classify a failure using the original signature and repeat-run evidence."""
    failure = payload.get("failure", {})
    failure_type = str(failure.get("failure_type", "unknown"))
    attempts = payload.get("attempts", [])
    valid_attempts = [
        attempt for attempt in attempts
        if isinstance(attempt, dict) and attempt.get("status") in {"passed", "failed"}
    ]
    statuses = [str(attempt["status"]) for attempt in valid_attempts]

    if failure_type in {"environment", "network"}:
        classification = "environment"
        confidence = 0.94
        reason = "The log contains a dependency or execution-environment failure signature."
    elif len(statuses) >= 2 and len(set(statuses)) > 1:
        classification = "flaky"
        confidence = 0.92
        reason = "Repeated attempts disagree: the test both passed and failed."
    elif len(statuses) >= 2 and all(status == "failed" for status in statuses) and failure_type == "assertion":
        classification = "regression"
        confidence = 0.90
        reason = "The assertion failure reproduced on every supplied attempt."
    elif len(statuses) >= 2 and all(status == "failed" for status in statuses) and failure_type == "environment":
        classification = "environment"
        confidence = 0.94
        reason = "The same dependency/setup failure appears on every supplied attempt."
    else:
        classification = "inconclusive"
        confidence = 0.25
        reason = "The available log and repeat-run observations are not enough to distinguish a regression from a transient failure."

    attempt_evidence = [
        {"attempt": index, "status": attempt["status"], "detail": str(attempt.get("detail", ""))}
        for index, attempt in enumerate(valid_attempts, start=1)
    ]
    return {
        "classification": classification,
        "confidence": confidence,
        "reason": reason,
        "attempts_observed": len(valid_attempts),
        "attempt_evidence": attempt_evidence,
    }


class SpecialistExecutor(AgentExecutor):
    """Wrap a deterministic specialist function in A2A task lifecycle events."""

    def __init__(self, handler: Callable[[dict[str, Any]], dict[str, Any]], working_message: str):
        self.handler = handler
        self.working_message = working_message

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        task = context.current_task
        if task is None:
            task = new_task_from_user_message(context.message)
            await event_queue.enqueue_event(task)

        updater = TaskUpdater(event_queue, task.id, context_id=task.context_id)
        await updater.update_status(
            state=TaskState.TASK_STATE_WORKING,
            message=new_text_message(self.working_message, role=Role.ROLE_AGENT),
        )

        try:
            request_text = get_message_text(context.message)
            request_payload = json.loads(request_text)
            if not isinstance(request_payload, dict):
                raise ValueError("Agent input must be a JSON object.")
            result = self.handler(request_payload)
            artifact = json.dumps(result, ensure_ascii=False)
            await updater.add_artifact(
                parts=[new_text_part(text=artifact, media_type="application/json")],
            )
            await updater.update_status(
                state=TaskState.TASK_STATE_COMPLETED,
                message=new_text_message("Finding ready.", role=Role.ROLE_AGENT),
            )
        except Exception as exc:  # A2A task gets a failure state instead of a hung request.
            await updater.update_status(
                state=TaskState.TASK_STATE_FAILED,
                message=new_text_message(f"The agent could not process this task: {exc}", role=Role.ROLE_AGENT),
            )

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        raise NotImplementedError("Cancellation is not supported by this short-running demo agent.")
