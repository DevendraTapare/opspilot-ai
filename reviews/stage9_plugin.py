"""Stage 9 evidence writer; reuse review hooks without changing Stage 7's path guard."""

import json
import os
from datetime import UTC, datetime
from pathlib import Path

from reviews.stage7_plugin import pytest_configure, pytest_runtest_makereport  # noqa: F401


def pytest_sessionfinish(session, exitstatus):
    target = os.environ.get("OPSPILOT_STAGE9_EVIDENCE")
    if not target:
        return
    root = Path(__file__).resolve().parents[1] / "artifacts/stage9"
    path = Path(target).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError("review evidence must stay in the project Stage 9 artifact directory")
    value = {
        "recorded_at_utc": datetime.now(UTC).isoformat(),
        "exit_status": int(exitstatus),
        "tests": list(session.config.stage7_rows.values()),
    }
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2)
