"""Tiny standard-library dashboard/API for the local demo."""

from __future__ import annotations

import asyncio
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .coordinator import investigate
from .scenarios import load_scenarios


def parse_triage_input(body: Any) -> tuple[str, list[dict[str, str]]]:
    """Validate manual input and translate attempt outcomes for the stability agent."""
    if not isinstance(body, dict):
        raise ValueError("The request body must be a JSON object.")

    log = body.get("log")
    if not isinstance(log, str) or not log.strip():
        raise ValueError("Paste a CI log before running the investigation.")
    if len(log) > 100_000:
        raise ValueError("Log must be no larger than 100 KB.")

    outcomes = body.get("attempts", [])
    if not isinstance(outcomes, list):
        raise ValueError("Attempt outcomes must be a list of passed/failed values.")
    if len(outcomes) > 20:
        raise ValueError("Enter no more than 20 attempt outcomes.")

    attempts: list[dict[str, str]] = []
    for index, outcome in enumerate(outcomes, start=1):
        if not isinstance(outcome, str) or outcome.strip().lower() not in {"passed", "failed"}:
            raise ValueError(f"Attempt {index} must be either passed or failed.")
        attempts.append({"status": outcome.strip().lower(), "detail": f"Manual attempt {index}."})

    return log, attempts


class DashboardHandler(BaseHTTPRequestHandler):
    server_version = "CISignal/0.1"
    agent_urls: dict[str, str] = {}

    def log_message(self, format: str, *args: Any) -> None:
        # Keep the demo console readable; app errors still return JSON to the browser.
        return

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status: int, payload: Any) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self._send(status, body, "application/json; charset=utf-8")

    def do_GET(self) -> None:  # noqa: N802 - stdlib handler API
        path = urlparse(self.path).path
        if path == "/":
            html_path = Path(__file__).parent / "static" / "index.html"
            self._send(200, html_path.read_bytes(), "text/html; charset=utf-8")
            return
        if path == "/api/scenarios":
            public = [
                {key: scenario[key] for key in ("id", "name", "description", "log", "attempts")}
                for scenario in load_scenarios()
            ]
            self._json(200, public)
            return
        if path == "/api/health":
            self._json(200, {"status": "ok", "agents": list(self.agent_urls)})
            return
        self._json(404, {"error": "Not found"})

    def do_POST(self) -> None:  # noqa: N802 - stdlib handler API
        if urlparse(self.path).path != "/api/triage":
            self._json(404, {"error": "Not found"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > 1_000_000:
                raise ValueError("Request body must be between 1 byte and 1 MB.")
            body = json.loads(self.rfile.read(length))
            log, attempts = parse_triage_input(body)
            result = asyncio.run(
                investigate(
                    log=log,
                    attempts=attempts,
                    agent_urls=self.agent_urls,
                )
            )
            self._json(200, result)
        except (ValueError, json.JSONDecodeError) as exc:
            self._json(400, {"error": str(exc)})
        except Exception as exc:
            self._json(502, {"error": f"Triage could not complete: {exc}"})


def serve_dashboard(agent_urls: dict[str, str], host: str = "127.0.0.1", port: int = 8000) -> None:
    handler = type("ConfiguredDashboardHandler", (DashboardHandler,), {"agent_urls": agent_urls})
    server = ThreadingHTTPServer((host, port), handler)
    print(f"CI Signal dashboard: http://{host}:{port}")
    print("Press Ctrl+C to stop the dashboard and local A2A agents.")
    try:
        server.serve_forever()
    finally:
        server.server_close()
