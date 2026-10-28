"""Build official A2A 1.0-compatible servers for local specialist agents."""

from __future__ import annotations

from starlette.applications import Starlette

from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.routes import create_agent_card_routes, create_jsonrpc_routes
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import AgentCapabilities, AgentCard, AgentInterface, AgentSkill

from .agents import SpecialistExecutor, assess_stability, inspect_failure


AGENTS = {
    "failure": {
        "name": "Failure Evidence Agent",
        "description": "Finds a failing test, classifies the visible error pattern, and returns exact log evidence.",
        "skill_id": "inspect_ci_failure",
        "skill_name": "Inspect CI failure logs",
        "skill_description": "Extract a test name, failure signature, and line-numbered evidence from a Python CI log.",
        "port": 10001,
        "executor": lambda: SpecialistExecutor(inspect_failure, "Inspecting CI log evidence."),
    },
    "stability": {
        "name": "Stability Agent",
        "description": "Uses repeat-run observations to distinguish reproducible failures from flaky or environmental failures.",
        "skill_id": "assess_failure_stability",
        "skill_name": "Assess repeat-run stability",
        "skill_description": "Compare failure signatures and pass/fail observations to classify stability with evidence.",
        "port": 10002,
        "executor": lambda: SpecialistExecutor(assess_stability, "Comparing repeat-run observations."),
    },
}


def build_agent_app(agent_key: str, host: str = "127.0.0.1", port: int | None = None) -> Starlette:
    """Create a Starlette A2A server with a public Agent Card and JSON-RPC route."""
    config = AGENTS[agent_key]
    resolved_port = port or int(config["port"])
    base_url = f"http://{host}:{resolved_port}/"

    skill = AgentSkill(
        id=str(config["skill_id"]),
        name=str(config["skill_name"]),
        description=str(config["skill_description"]),
        tags=["ci", "testing", "triage"],
        examples=["Analyze this pytest failure and return evidence."],
        input_modes=["text/plain"],
        output_modes=["application/json"],
    )
    card = AgentCard(
        name=str(config["name"]),
        description=str(config["description"]),
        version="0.1.0",
        default_input_modes=["text/plain"],
        default_output_modes=["application/json"],
        capabilities=AgentCapabilities(streaming=False, push_notifications=False),
        supported_interfaces=[
            AgentInterface(
                protocol_binding="JSONRPC",
                url=base_url,
                protocol_version="1.0",
            )
        ],
        skills=[skill],
    )
    handler = DefaultRequestHandler(
        agent_card=card,
        agent_executor=config["executor"](),
        task_store=InMemoryTaskStore(),
    )
    routes = create_agent_card_routes(card)
    routes.extend(create_jsonrpc_routes(handler, "/"))
    return Starlette(routes=routes)
