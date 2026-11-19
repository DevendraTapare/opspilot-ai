"""Read-only live MCP verification, including identity and default-disabled action checks."""

import argparse
import asyncio
import json
from pathlib import Path
from uuid import uuid4

import httpx2
from dotenv import dotenv_values
from jsonschema import Draft202012Validator
from mcp import Client
from mcp.client.streamable_http import streamable_http_client

from opspilot.gateway.contracts import ACTION_TOOLS, PROTOCOL_VERSION, READ_TOOLS

ROOT = Path(__file__).resolve().parents[1]


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expect-backend-unavailable", action="store_true")
    args = parser.parse_args()
    env = dotenv_values(ROOT / ".env")
    evidence = {"protocol_version": None, "checks": []}

    async def inspect_caller(token_name, expected_names):
        http = httpx2.AsyncClient(
            headers={"Authorization": f"Bearer {env[token_name]}"},
            trust_env=False,
            timeout=15,
        )
        async with (
            http,
            Client(
                streamable_http_client("http://127.0.0.1:8085/mcp", http_client=http),
                mode=PROTOCOL_VERSION,
                read_timeout_seconds=15,
            ) as client,
        ):
            assert client.protocol_version == PROTOCOL_VERSION
            await client.session.discover()
            evidence["protocol_version"] = client.protocol_version
            definitions = {tool.name: tool for tool in (await client.list_tools()).tools}
            assert set(definitions) == set(expected_names)
            evidence["checks"].append(
                {"check": token_name + "_discovery", "tools": sorted(definitions)}
            )

            async def call(name, arguments, error=None):
                result = await client.call_tool(name, arguments)
                value = result.structured_content
                assert value and value["untrusted_data"] is True
                assert result.is_error == (not value["ok"])
                if name in definitions:
                    Draft202012Validator(definitions[name].output_schema).validate(value)
                if error:
                    allowed = {error} if isinstance(error, str) else set(error)
                    assert value["error"]["code"] in allowed, value
                else:
                    assert value["ok"], value
                evidence["checks"].append(
                    {
                        "tool": name,
                        "ok": value["ok"],
                        "error": value["error"]["code"] if value["error"] else None,
                    }
                )
                return value

            if args.expect_backend_unavailable:
                await call(
                    "get_service_health",
                    {"service_name": "checkout-service"},
                    ["DOWNSTREAM_UNAVAILABLE", "TIMEOUT"],
                )
            elif token_name == "OPSPILOT_MCP_READER_TOKEN":
                incidents = await call(
                    "list_incidents", {"service_name": "checkout-service", "limit": 3}
                )
                for name in READ_TOOLS:
                    if name == "list_incidents":
                        continue
                    arguments = {"service_name": "checkout-service"}
                    if name == "get_incident":
                        assert incidents["data"]["items"], (
                            "Need an existing checkout incident for the live check"
                        )
                        arguments["incident_id"] = incidents["data"]["items"][0]["id"]
                    if "limit" in definitions[name].input_schema.get("properties", {}):
                        arguments["limit"] = 3
                    await call(name, arguments)
                await call(
                    "restart_simulated_worker",
                    {"service_name": "checkout-service", "request_id": str(uuid4())},
                    "FORBIDDEN",
                )
            elif token_name == "OPSPILOT_MCP_CHECKOUT_TOKEN":
                await call("get_service_health", {"service_name": "payment-service"}, "FORBIDDEN")
                await call(
                    "get_dependency_status", {"service_name": "checkout-service"}, "FORBIDDEN"
                )
            else:
                await call(
                    "restart_simulated_worker",
                    {"service_name": "payment-service", "request_id": str(uuid4())},
                    "ACTIONS_DISABLED",
                )

    await inspect_caller("OPSPILOT_MCP_READER_TOKEN", READ_TOOLS)
    if not args.expect_backend_unavailable:
        await inspect_caller("OPSPILOT_MCP_CHECKOUT_TOKEN", READ_TOOLS)
        await inspect_caller("OPSPILOT_MCP_OPERATOR_TOKEN", READ_TOOLS | ACTION_TOOLS)
    name = (
        "stage2-live-unavailable.json"
        if args.expect_backend_unavailable
        else "stage2-live-mcp.json"
    )
    (ROOT / "artifacts" / name).write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    print(json.dumps(evidence, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
