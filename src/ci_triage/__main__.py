"""CLI entry point for the CI Signal learning demo."""

from __future__ import annotations

import argparse
import os
import sys

from .runtime import start_agents


def main() -> None:
    parser = argparse.ArgumentParser(prog="ci-triage", description="Local A2A-powered CI failure triage demo")
    parser.add_argument("command", choices=("web", "eval"), help="Start the dashboard or run the A2A eval suite")
    args = parser.parse_args()

    if args.command == "eval":
        from .evals import run_evals

        sys.exit(run_evals())

    host = os.environ.get("HOST", "127.0.0.1")
    try:
        port = int(os.environ.get("PORT", "8000"))
    except ValueError as exc:
        raise SystemExit("PORT must be an integer between 1 and 65535.") from exc
    if not 1 <= port <= 65535:
        raise SystemExit("PORT must be an integer between 1 and 65535.")

    runtime = start_agents()
    try:
        from .web import serve_dashboard

        serve_dashboard(runtime.urls, host=host, port=port)
    except KeyboardInterrupt:
        pass
    finally:
        runtime.stop()


if __name__ == "__main__":
    main()
