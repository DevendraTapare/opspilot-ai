"""Explicit MCP discovery/call example. Reads only its own pre-provisioned client token."""

import argparse
import asyncio
import json
import os
import subprocess
import sys
from urllib.parse import urlsplit

import httpx2
from mcp import Client, StdioServerParameters
from mcp.client.streamable_http import streamable_http_client

from opspilot.gateway.contracts import ACTION_TOOLS, PROTOCOL_VERSION, SUPERVISION_TOOLS, TOOLS
from opspilot.schemas import ServiceName


async def run(args):
    token = os.environ.get("OPSPILOT_MCP_TOKEN", "")
    if len(token) < 32:
        raise SystemExit("Set OPSPILOT_MCP_TOKEN to the intended caller's local credential")
    url = urlsplit(args.url)
    if (
        url.scheme != "http"
        or url.hostname not in {"127.0.0.1", "localhost", "mcp"}
        or url.path != "/mcp"
        or url.username
        or url.query
        or url.fragment
    ):
        raise SystemExit("Example client targets only the explicitly selected local MCP endpoint")
    transport = (
        StdioServerParameters(
            command=sys.executable,
            args=[
                "-m",
                "opspilot.gateway.stdio",
            ],
            env={
                "OPSPILOT_MCP_TOKEN": token,
                "PYTHONDONTWRITEBYTECODE": "1",
                "PYTHONUNBUFFERED": "1",
                **{
                    key: os.environ[key]
                    for key in (
                        "OPSPILOT_GATEWAY_CALLERS",
                        "OPSPILOT_GATEWAY_DELEGATION_KEY",
                        "OPSPILOT_GATEWAY_BACKEND_URL",
                    )
                    if key in os.environ
                },
            },
        )
        if args.transport == "stdio"
        else None
    )
    async with (
        httpx2.AsyncClient(
            headers={"Authorization": f"Bearer {token}"}, trust_env=False, timeout=15
        ) as http,
        Client(
            transport or streamable_http_client(args.url, http_client=http),
            mode=PROTOCOL_VERSION,
            read_timeout_seconds=30 if args.transport == "stdio" else 15,
        ) as client,
    ):
        await client.session.discover()
        definitions = await client.list_tools()
        print(
            json.dumps(
                {
                    "protocol_version": client.protocol_version,
                    "tools": [tool.name for tool in definitions.tools],
                },
                indent=2,
            )
        )
        name = args.tool
        arguments = {"service_name": args.service or "checkout-service"}
        model = TOOLS[name][0]
        for field in (
            "limit",
            "query",
            "incident_id",
            "approval_id",
            "request_id",
            "run_id",
            "action_fingerprint",
        ):
            value = getattr(args, field, None)
            if field in model.model_fields and value is not None:
                arguments[field] = value
        result = await client.call_tool(name, arguments)
        print(json.dumps(result.structured_content, indent=2))
        if result.is_error:
            raise SystemExit(2)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8085/mcp")
    parser.add_argument("--transport", choices=["http", "stdio"], default="http")
    parser.add_argument("--tool", choices=sorted(TOOLS), default="get_service_health")
    parser.add_argument("--service", choices=list(ServiceName))
    parser.add_argument("--limit", type=int)
    parser.add_argument("--query")
    parser.add_argument("--incident-id")
    parser.add_argument("--approval-id")
    parser.add_argument("--request-id")
    parser.add_argument("--run-id")
    parser.add_argument("--action-fingerprint")
    args = parser.parse_args()
    if args.tool in SUPERVISION_TOOLS and not all(
        (args.service, args.approval_id, args.request_id, args.run_id, args.action_fingerprint)
    ):
        parser.error("supervision calls require exact service/approval/request/run/fingerprint")
    if args.tool in ACTION_TOOLS and (
        not args.service or not args.approval_id or not args.request_id
    ):
        parser.error("action examples require --service, --approval-id, and --request-id")
    if args.transport == "stdio" and "OPSPILOT_GATEWAY_CALLERS" not in os.environ:
        # Run both SDK peers inside Linux. Docker stdout carries the CLI result,
        # avoiding Windows Docker-exec pipe behavior as the MCP transport.
        result = subprocess.run(
            [
                "docker",
                "compose",
                "exec",
                "-T",
                "-e",
                "OPSPILOT_MCP_TOKEN",
                "mcp",
                "python",
                "-m",
                "opspilot.gateway.client",
                *sys.argv[1:],
            ],
            check=False,
            stderr=subprocess.STDOUT,
        )
        raise SystemExit(result.returncode)
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
