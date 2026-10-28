# CI Signal

**A2A-powered, evidence-first CI failure triage demo.**

[Try the live demo](https://ci-signal.onrender.com/) · [Health check](https://ci-signal.onrender.com/api/health) · Python 3.10+

CI Signal investigates a failed Python CI run. Paste a job log and optional retry outcomes; two specialist agents analyze the evidence over the [Agent2Agent (A2A) protocol](https://a2a-protocol.org/), and a coordinator presents a diagnosis with the evidence and agent task trace.

> **Scope:** This is a portfolio/learning prototype, not a production CI integration. It does not connect to GitHub Actions, inspect a codebase, run repository code, or edit files. It uses deterministic analysis and bundled examples; no model API key is required.

<!--
Add screenshots under docs/screenshots/ and uncomment these when the images are ready:
![CI Signal input form](docs/screenshots/dashboard.png)
![Example diagnosis and A2A trace](docs/screenshots/report.png)
-->

## Try it online

1. Open the [live demo](https://ci-signal.onrender.com/).
2. Choose an example, or paste a failed job's log (up to 100 KB).
3. Optionally enter attempt results—one `passed` or `failed` per line. Include the original run and any retries.
4. Select **Run investigation** and review the diagnosis, log evidence, retry observations, and A2A trace.

Example retry outcomes:

```text
failed
passed
failed
```

If there is no retry history, leave the field blank. The result may be inconclusive if the evidence is insufficient. The free Render instance can take about a minute to wake after 15 minutes without traffic. **Use sample or non-sensitive logs only:** the public demo is unauthenticated.

## What it diagnoses

| Example | Expected result |
| --- | --- |
| Same assertion failure on repeated attempts | Likely regression |
| Test passes and fails across attempts | Likely flaky test |
| Missing dependency or setup error | Environment issue |
| Incomplete or unclassified evidence | Inconclusive |

## How the agents work

The dashboard sends a request to the coordinator, which discovers each specialist through its A2A Agent Card and sends each a task:

```text
Browser → Dashboard / Coordinator (A2A client)
                    ├─ Failure Evidence Agent: find failure signature and log evidence
                    └─ Stability Agent: compare signature with attempt outcomes
```

The agents return findings as task artifacts. The coordinator combines them into a report and exposes the discovery and task states in the UI. If a specialist is unavailable, the trace makes that visible and the diagnosis falls back to inconclusive rather than silently treating a partial result as certain.

The agents are separate A2A HTTP endpoints with their own Agent Cards and in-memory task stores, but this demo runs them in the same Python process/container for simplicity. They are not separately deployed or scaled services.

## Run locally

Requires Python 3.10 or newer. No API key, database, or paid service is needed.

### Windows PowerShell

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e .
python -m ci_triage web
```

### macOS / Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .
python -m ci_triage web
```

Open <http://127.0.0.1:8000>. Press `Ctrl+C` to stop the dashboard and both agents. For local inspection, the Agent Cards are at:

- <http://127.0.0.1:10001/.well-known/agent-card.json> — Failure Evidence Agent
- <http://127.0.0.1:10002/.well-known/agent-card.json> — Stability Agent
- <http://127.0.0.1:8000/api/health> — dashboard API status and configured agents

## Run tests and evaluations

In a second terminal with the virtual environment activated:

```bash
python -m unittest discover -s tests -v
python -m ci_triage eval
```

- **Unit tests** validate manual input handling and reject malformed attempt outcomes.
- **A2A evaluations** start the real local agents, discover their Agent Cards, send tasks through the A2A client/server path, and check diagnoses, evidence, task completion, and behavior when an agent is unavailable.

The current suite covers five scenarios and 23 checks. The same tests run on GitHub pushes and pull requests via the workflow in `.github/workflows/evals.yml`.

## Deploy with Docker

The project includes a single-container Docker setup. The dashboard honors `HOST` and the platform-provided `PORT`; the agents bind to loopback for coordinator-to-agent requests.

```bash
docker build -t ci-signal .
docker run --rm -p 8000:8080 -e HOST=0.0.0.0 -e PORT=8080 ci-signal
```

Then visit <http://127.0.0.1:8000>. To deploy on a Docker-capable host, use the repository root as the build context and set the service health-check path to `/api/health`. The live demo is hosted on Render; its free instance sleeps when idle, so its first request after sleeping can be slow.

## Project structure

```text
src/ci_triage/
├── agents.py       # Specialist logic and A2A task lifecycle
├── coordinator.py  # Agent discovery, delegation, trace, and synthesis
├── server.py       # Agent Cards and A2A JSON-RPC endpoints
├── runtime.py      # Local agent server lifecycle
├── web.py          # Dashboard and JSON API
├── evals.py        # End-to-end A2A evaluation suite
├── data/           # Reproducible example scenarios
└── static/         # Browser dashboard
tests/              # Input validation unit tests
```

## Limitations and next steps

- No GitHub connection yet: users paste logs manually. A repository URL alone would not grant access to private workflows.
- Analysis is deterministic and rule-based; it is not an LLM root-cause analysis system.
- The public demo has no authentication. Do not submit secrets or private company logs.
- Future work: a read-only GitHub Actions adapter, broader eval cases, and authentication/rate limiting before handling private logs.

## License

No license has been added. Until one is chosen, normal copyright applies; add a `LICENSE` file before inviting reuse as open source.
