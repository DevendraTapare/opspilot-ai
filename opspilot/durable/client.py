"""Credential-separated action client; never supplied to an LLM."""

import asyncio
import json
from contextlib import asynccontextmanager
from urllib.parse import urlsplit

import httpx2
from mcp import Client
from mcp.client.streamable_http import streamable_http_client

from opspilot.gateway.contracts import (
    ACTION_TOOLS,
    MAX_RESULT_BYTES,
    PROTOCOL_VERSION,
    SUPERVISION_TOOLS,
    TOOLS,
    ToolResponse,
    validate_arguments,
)
from opspilot.observability import attributes, carrier, observed


class ExecutionClient:
    def __init__(self, client, timeout=15):
        self.client, self.timeout = client, timeout

    @observed("execute_tool mcp-approved", operation="execute_tool")
    async def call(self, name, arguments):
        attributes(**{"gen_ai.tool.name": name, "opspilot.run_id": arguments.get("run_id")})
        if name not in ACTION_TOOLS and name not in SUPERVISION_TOOLS:
            raise ValueError("execution client only accepts approved action/supervision tools")
        typed = validate_arguments(name, arguments)
        result = await asyncio.wait_for(
            self.client.call_tool(name, typed.model_dump(mode="json"), meta=carrier()),
            timeout=self.timeout,
        )
        value = result.structured_content
        if not value or len(json.dumps(value).encode()) > MAX_RESULT_BYTES:
            raise ValueError("invalid structured action response")
        response = ToolResponse[TOOLS[name][1]].model_validate(value)
        if result.is_error == response.ok:
            raise ValueError("inconsistent action error state")
        if response.ok:
            data = response.data.model_dump(mode="json")
            if name in ACTION_TOOLS:
                if (
                    data["execution_id"] != arguments["request_id"]
                    or data["approval_id"] != arguments["approval_id"]
                    or data["service_name"] != arguments["service_name"]
                    or data["action"] != name
                ):
                    raise ValueError("action response binding mismatch")
            elif (
                data["run_id"] != arguments["run_id"]
                or data["request_id"] != arguments["request_id"]
            ):
                raise ValueError("supervision response binding mismatch")
        return response.model_dump(mode="json")


@asynccontextmanager
async def connect_executor(url, token):
    target = urlsplit(url)
    if (
        target.scheme != "http"
        or target.hostname not in {"127.0.0.1", "localhost", "mcp"}
        or target.path != "/mcp"
        or target.username
        or target.password
        or target.query
        or target.fragment
        or not 32 <= len(token) <= 256
    ):
        raise ValueError("local MCP endpoint and separate executor credential required")
    async with (
        httpx2.AsyncClient(
            headers={"Authorization": f"Bearer {token}"}, trust_env=False, timeout=15
        ) as http,
        Client(
            streamable_http_client(url, http_client=http),
            mode=PROTOCOL_VERSION,
            read_timeout_seconds=15,
        ) as client,
    ):
        await client.session.discover()
        definitions = {t.name for t in (await client.list_tools()).tools}
        if not (set(ACTION_TOOLS) | set(SUPERVISION_TOOLS)) <= definitions:
            raise ValueError("executor credential lacks required scoped tools")
        yield ExecutionClient(client)
