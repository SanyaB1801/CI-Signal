"""A2A client/orchestrator that delegates a triage run to specialist agents."""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any

import httpx
from a2a.client import A2ACardResolver, ClientConfig, create_client
from a2a.helpers import new_text_message
from a2a.types import Role, SendMessageRequest
from google.protobuf.json_format import MessageToDict
from google.protobuf.message import Message as ProtobufMessage


DEFAULT_AGENT_URLS = {
    "failure": "http://127.0.0.1:10001",
    "stability": "http://127.0.0.1:10002",
}


def _to_plain(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _to_plain(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_to_plain(item) for item in value]
    root = getattr(value, "root", None)
    if root is not None:
        return _to_plain(root)
    proto_value = getattr(value, "_pb", None)
    if proto_value is not None:
        return _to_plain(MessageToDict(proto_value, preserving_proto_field_name=False))
    if isinstance(value, ProtobufMessage):
        return _to_plain(MessageToDict(value, preserving_proto_field_name=False))
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        return _to_plain(model_dump(mode="json", by_alias=True, exclude_none=True))
    return value


def _find_task(value: Any) -> dict[str, Any] | None:
    plain = _to_plain(value)
    if isinstance(plain, dict):
        if "status" in plain and "id" in plain:
            return plain
        for key in ("result", "task", "response"):
            nested = _find_task(plain.get(key))
            if nested is not None:
                return nested
    return None


def _artifact_result(task: dict[str, Any]) -> dict[str, Any]:
    for artifact in task.get("artifacts", []):
        for part in artifact.get("parts", []):
            text = part.get("text") if isinstance(part, dict) else None
            if not text:
                continue
            try:
                decoded = json.loads(text)
            except json.JSONDecodeError:
                continue
            if isinstance(decoded, dict):
                return decoded
    raise ValueError("The A2A task completed without a JSON finding artifact.")


async def _invoke_agent(
    agent_key: str,
    base_url: str,
    payload: dict[str, Any],
    trace: list[dict[str, Any]],
) -> dict[str, Any]:
    started = time.perf_counter()
    agent_name = {"failure": "Failure Evidence Agent", "stability": "Stability Agent"}.get(agent_key, agent_key)
    try:
        async with httpx.AsyncClient(timeout=15.0) as http_client:
            resolver = A2ACardResolver(httpx_client=http_client, base_url=base_url)
            card = await resolver.get_agent_card()
            agent_name = card.name
            skills = [skill.name for skill in card.skills]
            trace.append({
                "type": "discovery",
                "agent": card.name,
                "agent_key": agent_key,
                "skills": skills,
                "protocol": card.supported_interfaces[0].protocol_binding if card.supported_interfaces else "unknown",
                "protocol_version": card.supported_interfaces[0].protocol_version if card.supported_interfaces else "unknown",
                "status": "discovered",
            })

            client = await create_client(
                agent=card,
                client_config=ClientConfig(streaming=False),
            )
            try:
                message = new_text_message(
                    json.dumps(payload, ensure_ascii=False),
                    role=Role.ROLE_USER,
                )
                request = SendMessageRequest(message=message)
                last_response: Any = None
                async for response in client.send_message(request):
                    last_response = response
            finally:
                await client.close()

        task = _find_task(last_response)
        if task is None:
            raise ValueError(f"{agent_name} returned no A2A task.")
        status = task.get("status", {})
        state = status.get("state", "unknown") if isinstance(status, dict) else "unknown"
        status_message = None
        if isinstance(status, dict):
            message_parts = (status.get("message") or {}).get("parts", [])
            if message_parts and isinstance(message_parts[0], dict):
                status_message = message_parts[0].get("text")
        trace.append({
            "type": "task",
            "agent": agent_name,
            "agent_key": agent_key,
            "task_id": task.get("id"),
            "state": state,
            "duration_ms": round((time.perf_counter() - started) * 1000),
            "status_message": status_message,
        })
        if state not in {"TASK_STATE_COMPLETED", "completed"}:
            raise RuntimeError(f"{agent_name} task ended in state {state}.")
        return _artifact_result(task)
    except Exception as exc:
        trace.append({
            "type": "agent_error",
            "agent": agent_name,
            "agent_key": agent_key,
            "state": "unavailable",
            "duration_ms": round((time.perf_counter() - started) * 1000),
            "error": str(exc),
        })
        raise


def _diagnosis(stability: dict[str, Any], failure: dict[str, Any]) -> dict[str, Any]:
    classification = stability.get("classification", "inconclusive")
    labels = {
        "regression": "Likely regression",
        "flaky": "Likely flaky test",
        "environment": "Environment or setup issue",
        "inconclusive": "Insufficient evidence",
    }
    recommendations = {
        "regression": "Inspect the change that introduced this assertion and keep the failure visible until it is fixed.",
        "flaky": "Inspect timing, shared state, or external-service dependence; avoid treating a passing retry as proof the test is healthy.",
        "environment": "Check dependency installation and CI runner setup before changing application code.",
        "inconclusive": "Capture the full traceback and collect more repeat-run observations before assigning a root cause.",
    }
    return {
        "classification": classification,
        "title": labels.get(classification, "Insufficient evidence"),
        "confidence": stability.get("confidence", 0.0),
        "reason": stability.get("reason", "The agent did not return a reason."),
        "recommendation": recommendations.get(classification, recommendations["inconclusive"]),
        "test_name": failure.get("test_name"),
        "failure_type": failure.get("failure_type", "unknown"),
        "evidence": failure.get("evidence", []),
        "attempt_evidence": stability.get("attempt_evidence", []),
        "attempts_observed": stability.get("attempts_observed", 0),
    }


async def investigate(
    *,
    log: str,
    attempts: list[dict[str, Any]],
    agent_urls: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Discover, delegate, and combine two independent A2A agent tasks."""
    urls = agent_urls or DEFAULT_AGENT_URLS
    trace: list[dict[str, Any]] = []
    try:
        failure = await _invoke_agent("failure", urls["failure"], {"log": log}, trace)
    except Exception as exc:
        return {
            "diagnosis": _diagnosis({"classification": "inconclusive", "confidence": 0.1, "reason": f"Failure analysis did not complete: {exc}"}, {}),
            "trace": trace,
        }
    try:
        stability = await _invoke_agent(
            "stability",
            urls["stability"],
            {"failure": failure, "attempts": attempts},
            trace,
        )
    except Exception as exc:
        stability = {
            "classification": "inconclusive",
            "confidence": 0.2,
            "reason": f"The failure evidence was collected, but stability analysis did not complete: {exc}",
            "attempts_observed": 0,
            "attempt_evidence": [],
        }
    return {
        "diagnosis": _diagnosis(stability, failure),
        "trace": trace,
    }
