"""Load bundled reproducible demo/evaluation scenarios."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_scenarios() -> list[dict[str, Any]]:
    path = Path(__file__).parent / "data" / "scenarios.json"
    return json.loads(path.read_text(encoding="utf-8"))
