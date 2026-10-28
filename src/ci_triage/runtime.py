"""Run the two local A2A agents as independent HTTP services."""

from __future__ import annotations

import time
import urllib.request
from dataclasses import dataclass
from threading import Thread
from typing import Any

import uvicorn

from .server import AGENTS, build_agent_app


@dataclass
class AgentRuntime:
    servers: list[uvicorn.Server]
    threads: list[Thread]
    urls: dict[str, str]

    def stop(self) -> None:
        for server in self.servers:
            server.should_exit = True
        for thread in self.threads:
            thread.join(timeout=4)


def start_agents(port_offset: int = 0, timeout: float = 10.0) -> AgentRuntime:
    """Start each A2A server on localhost and wait until its public card is served."""
    servers: list[uvicorn.Server] = []
    threads: list[Thread] = []
    urls: dict[str, str] = {}

    for key, config in AGENTS.items():
        port = int(config["port"]) + port_offset
        app = build_agent_app(key, port=port)
        server = uvicorn.Server(
            uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error", access_log=False)
        )
        thread = Thread(target=server.run, name=f"a2a-{key}-agent", daemon=True)
        servers.append(server)
        threads.append(thread)
        urls[key] = f"http://127.0.0.1:{port}"
        thread.start()

    deadline = time.monotonic() + timeout
    pending = set(urls)
    while pending and time.monotonic() < deadline:
        for key in list(pending):
            try:
                with urllib.request.urlopen(f"{urls[key]}/.well-known/agent-card.json", timeout=0.4) as response:
                    if response.status == 200:
                        pending.remove(key)
            except Exception:
                pass
        if pending:
            time.sleep(0.1)

    if pending:
        for server in servers:
            server.should_exit = True
        raise RuntimeError(f"A2A agent server(s) did not start: {', '.join(sorted(pending))}")

    return AgentRuntime(servers=servers, threads=threads, urls=urls)
