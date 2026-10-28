# CI Signal

**Evidence-first CI failure triage, built as a small multi-agent A2A demo.**

CI Signal takes a Python CI log and optional retry outcomes, delegates analysis to two independently served agents, and combines their findings into a diagnosis with traceable evidence. You can paste your own inputs or load a bundled example. A browser dashboard lets you inspect the result and A2A task trace.

> **Project status:** This is a working portfolio/learning prototype, not a production CI integration. It accepts pasted logs and retry outcomes, with bundled scenarios for demos. It does not connect to GitHub Actions, inspect a repository, execute repository code, or change source files.

## Why agents?

The work is split into two focused capabilities rather than one chatbot prompt:

1. The **Failure Evidence Agent** discovers from its A2A Agent Card and extracts a failure signature and matching log lines.
2. The **Stability Agent** discovers separately and compares that signature with pass/fail retry observations.
3. The **coordinator** calls both agents over A2A, combines their artifacts, and returns a diagnosis. If an agent is unavailable, the trace shows the failure and the result becomes inconclusive instead of silently guessing.

The agents run as separate HTTP services with their own Agent Cards and in-memory task stores. They currently share one Python process for easy local development and container deployment; they are separate A2A endpoints, not separately scaled production services.

```text
Browser → CI Signal dashboard / coordinator (A2A client)
                         ├─ Agent Card discovery → Failure Evidence Agent
                         └─ Agent Card discovery → Stability Agent
```

## What you can try

Paste a CI log and, if available, enter the result of each attempt (`passed` or `failed`, one per line). Include the original run and any reruns. If you do not have retry data, leave it blank; the result should then be inconclusive when stability cannot be established. You can instead load one of the bundled examples, which fills both the log and matching attempt outcomes:

| Scenario | Expected result |
| --- | --- |
| Reproducible assertion failure | Likely regression |
| Pass/fail disagreement across retries | Likely flaky test |
| Missing Python dependency | Environment or setup issue |
| Incomplete or unclassified log | Insufficient evidence |

The dashboard shows the diagnosis, confidence, evidence lines, retry observations, discovered agent skills, task states, and timing.

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

Open <http://127.0.0.1:8000>. The A2A Agent Cards are available locally at:

- <http://127.0.0.1:10001/.well-known/agent-card.json> — Failure Evidence Agent
- <http://127.0.0.1:10002/.well-known/agent-card.json> — Stability Agent
- <http://127.0.0.1:8000/api/health> — dashboard health check

Press `Ctrl+C` to stop the dashboard and both agents.

To change the dashboard bind address or port, set `HOST` and `PORT` before starting it. For example, on PowerShell: `$env:HOST="0.0.0.0"; $env:PORT="8080"; python -m ci_triage web`.

## Run the evaluations

In a second terminal with the virtual environment activated, run the input tests and the end-to-end A2A evals:

```bash
python -m unittest discover -s tests -v
python -m ci_triage eval
```

The evaluation runner starts the actual A2A servers, discovers both Agent Cards, sends tasks through the A2A client/server path, and checks expected classifications, evidence, task completion, and graceful behavior when an agent is unavailable. It exits non-zero if a scenario fails. The bundled suite currently contains five scenarios, including an unavailable-agent case. Input validation has separate unit tests. Both run automatically on GitHub pushes and pull requests.

## Deploy with Docker

The included Dockerfile builds a single-container demo. The dashboard listens on `0.0.0.0` and honors the platform-provided `PORT`; the two agent endpoints remain bound to the container's loopback interface for coordinator-to-agent traffic.

Build and run locally:

```bash
docker build -t ci-signal .
docker run --rm -p 8000:8080 -e HOST=0.0.0.0 -e PORT=8080 ci-signal
```

Then open <http://127.0.0.1:8000>.

For a cloud host that supports Docker deployments, push this repository to GitHub, create a web service from that repository, select the Docker runtime, and use the repository root as the build context. The image starts the app with `python -m ci_triage web`; configure the service to provide `HOST=0.0.0.0` and its assigned `PORT` if it does not set those automatically. Confirm the platform health check at `/api/health`.

Before sharing a public instance, remember that the demo endpoint is unauthenticated and is intended for sample or non-sensitive logs. Submitted logs are not intentionally persisted by this application, but avoid secrets and private logs. Add access control, rate limiting, and appropriate log-retention/privacy controls before accepting real company CI data.

## Project layout

```text
src/ci_triage/
├── agents.py       # Specialist logic and A2A task lifecycle
├── coordinator.py  # Agent discovery, delegation, trace, and synthesis
├── server.py       # Agent Cards and A2A JSON-RPC endpoints
├── runtime.py      # Local agent server lifecycle
├── web.py          # Dashboard and small JSON API
├── evals.py        # End-to-end A2A evaluation suite
├── data/           # Curated, reproducible scenarios
└── static/         # Browser dashboard
tests/              # Input validation unit tests
```

## Next steps

- Add a read-only GitHub Actions adapter to fetch real workflow logs.
- Expand the eval set with real-world, ambiguous, and adversarial log cases.
- Add configurable authentication and request limits before handling private logs.
- Explore an optional model-backed explanation agent while keeping evidence extraction and evaluations deterministic.

## License

No license has been added yet. Add a `LICENSE` file before treating the project as open source or inviting reuse; without one, normal copyright applies.
