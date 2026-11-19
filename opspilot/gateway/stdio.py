"""MCP stdio transport with caller credentials supplied by the launching operator."""

import asyncio
import os

from mcp.server.stdio import stdio_server

from opspilot.gateway.mcp_server import create_mcp_app
from opspilot.gateway.security import GatewaySettings, authenticate


async def main():
    settings = GatewaySettings()
    credential = os.environ.get("OPSPILOT_MCP_TOKEN", "")
    if not authenticate(f"Bearer {credential}", settings.policies()):
        raise SystemExit("A valid local caller credential is required in the launcher environment")
    app = create_mcp_app(settings, local_credential=credential)
    server = app.state.mcp_server
    async with stdio_server() as (reader, writer):
        await server.run(reader, writer, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
