"""Capture one calibration ambiguity using real TCP MCP, with rules only."""

import asyncio
import json
import os
from pathlib import Path

from evaluations.runners.dataset import load
from evaluations.runners.environment import Environment
from evaluations.runners.subjects import baseline, read
from opspilot.agent.mcp import connect
from scripts.review_stage9 import environment

ROOT = Path(__file__).resolve().parents[1]


async def probe():
    case = next(c for c in load("calibration") if c.family == "failed_remediation")
    with Environment(os.environ["OPSPILOT_TEST_DATABASE_URL"]).start() as controller:
        public = controller.prepare(case)
        async with connect(controller.url, controller.token) as mcp:
            observations = [
                await read(mcp, name, public)
                for name in [
                    "get_incident",
                    "get_service_metrics",
                    "search_service_logs",
                    "get_dependency_status",
                    "list_recent_deployments",
                ]
            ]
            prediction = await baseline(public, mcp)
    return {
        "mode": "rules",
        "real_model": False,
        "case_id": case.id,
        "public_input": public.model_dump(mode="json"),
        "observations": observations,
        "prediction": prediction.model_dump(mode="json"),
    }


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    output = Path(parser.parse_args().output).resolve()
    if not output.is_relative_to(ROOT / "artifacts/stage9") or output.exists():
        parser.error("Choose a new output inside artifacts/stage9")
    os.environ.update(environment())
    output.write_text(json.dumps(asyncio.run(probe()), indent=2), encoding="utf-8")
    print(
        "Saved projected operational evidence, no model inference: " + str(output.relative_to(ROOT))
    )
