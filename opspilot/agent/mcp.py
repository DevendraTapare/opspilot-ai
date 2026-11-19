"""Actual SDK read-only MCP transport. No database or simulator control credentials."""

from contextlib import asynccontextmanager
from urllib.parse import urlsplit

import httpx2
from mcp import Client
from mcp.client.streamable_http import streamable_http_client

from opspilot.gateway.contracts import MAX_RESULT_BYTES, PROTOCOL_VERSION, READ_TOOLS
from opspilot.observability import attributes, carrier, observed


class ReadOnlyMCP:
    def __init__(self, client):
        self.client = client

    @observed("execute_tool mcp-read", operation="execute_tool")
    async def call(self, name: str, arguments: dict) -> dict:
        attributes(**{"gen_ai.tool.name": name})
        if name not in READ_TOOLS:
            raise ValueError("read-only tool allowlist rejected call")
        result = await self.client.call_tool(name, arguments, meta=carrier())
        value = result.structured_content
        if value is None:
            raise ValueError("MCP response has no structured content")
        import json

        if len(json.dumps(value, allow_nan=False).encode()) > MAX_RESULT_BYTES:
            raise ValueError("MCP response exceeds budget")
        if result.is_error == bool(value.get("ok")):
            raise ValueError("inconsistent MCP error state")
        return value


@asynccontextmanager
async def connect(url: str, token: str):
    target = urlsplit(url)
    if (
        target.scheme != "http"
        or target.hostname not in {"127.0.0.1", "localhost", "mcp"}
        or target.path != "/mcp"
        or target.username
        or target.password
        or target.query
        or target.fragment
        or len(token) < 32
    ):
        raise ValueError("use a configured local MCP URL and read-only credential")
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
        discovery = await client.list_tools()
        available = {t.name for t in discovery.tools}
        if available == set(READ_TOOLS):
            yield ReadOnlyMCP(client)
    if available != set(READ_TOOLS):
        # Raise after closing SDK task groups so callers receive a plain bounded error.
        raise ValueError("agent credential must discover exactly the seven read tools")
