"""Run an investigation against the real read-only MCP endpoint."""

import argparse
import asyncio
import json
import os
from pathlib import Path
from uuid import UUID

from opspilot.agent.fixtures import FixtureDecisionModel
from opspilot.agent.mcp import connect
from opspilot.agent.providers import HTTPDecisionModel
from opspilot.agent.schemas import RunRequest
from opspilot.agent.workflow import Investigation
from opspilot.schemas import ServiceName


async def execute(args):
    model = (
        FixtureDecisionModel() if args.mode == "fixture" else (HTTPDecisionModel.from_environment())
    )
    request = RunRequest(
        incident_id=UUID(args.incident_id),
        service_name=args.service,
        goal=args.goal,
        max_tool_calls=args.max_tool_calls,
        max_seconds=args.max_seconds,
    )
    async with connect(args.mcp_url, os.environ.get("OPSPILOT_MCP_TOKEN", "")) as mcp:
        result = await Investigation(model, mcp, request).run()
    value = result.model_dump(mode="json")
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(value, indent=2), encoding="utf-8")
    print(json.dumps(value, indent=2))
    return 0 if result.run_status == "completed" else 2


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", required=True, choices=["real", "fixture"])
    parser.add_argument("--incident-id", required=True)
    parser.add_argument("--service", choices=list(ServiceName), default="checkout-service")
    parser.add_argument("--goal", default=RunRequest.model_fields["goal"].default)
    parser.add_argument("--mcp-url", default="http://127.0.0.1:8085/mcp")
    parser.add_argument("--max-tool-calls", type=int, default=8)
    parser.add_argument("--max-seconds", type=float, default=180)
    parser.add_argument("--output")
    args = parser.parse_args()
    # Disable optional LangSmith tracing regardless of ambient developer configuration.
    os.environ["LANGSMITH_TRACING"] = "false"
    os.environ["LANGCHAIN_TRACING_V2"] = "false"
    try:
        code = asyncio.run(execute(args))
    except Exception:
        print(
            json.dumps(
                {
                    "status": "failed",
                    "mode": args.mode,
                    "error": "Provider configuration or MCP connection failed. "
                    "No fixture substitution was made.",
                }
            )
        )
        code = 2
    raise SystemExit(code)


if __name__ == "__main__":
    main()
