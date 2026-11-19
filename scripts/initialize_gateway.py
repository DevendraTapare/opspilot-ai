"""Add independent local Stage 2 credentials without exposing or rotating Stage 1 secrets."""

import hashlib
import json
import secrets
from pathlib import Path

from dotenv import dotenv_values

from opspilot.gateway.contracts import READ_TOOLS, TOOLS
from opspilot.schemas import ServiceName


def main():
    path = Path(__file__).resolve().parents[1] / ".env"
    values = dotenv_values(path)
    if not values.get("OPSPILOT_DATABASE_URL"):
        raise SystemExit("Initialize Stage 1's local .env first")
    if values.get("OPSPILOT_GATEWAY_CALLERS"):
        print("Existing Stage 2 credentials preserved.")
        return
    tokens = {name: secrets.token_hex(32) for name in ("READER", "CHECKOUT", "OPERATOR")}
    policies = []
    for subject, token_name, services, tools in (
        ("incident-reader", "READER", list(ServiceName), sorted(READ_TOOLS)),
        ("checkout-observer", "CHECKOUT", [ServiceName.CHECKOUT], sorted(READ_TOOLS)),
        ("sandbox-operator", "OPERATOR", list(ServiceName), sorted(TOOLS)),
    ):
        policies.append(
            {
                "subject": subject,
                "token_sha256": hashlib.sha256(tokens[token_name].encode()).hexdigest(),
                "services": services,
                "tools": tools,
            }
        )
    additions = {
        "OPSPILOT_GATEWAY_CALLERS": json.dumps(policies, separators=(",", ":")),
        "OPSPILOT_GATEWAY_DELEGATION_KEY": secrets.token_hex(32),
        "OPSPILOT_GATEWAY_APPROVAL_KEY": secrets.token_hex(32),
        "OPSPILOT_GATEWAY_DATABASE_URL": values["OPSPILOT_DATABASE_URL"],
        "OPSPILOT_GATEWAY_ACTIONS_ENABLED": "false",
        **{f"OPSPILOT_MCP_{name}_TOKEN": token for name, token in tokens.items()},
    }
    with path.open("a", encoding="utf-8") as target:
        target.write("\n# Stage 2 local gateway credentials; never mount this file into MCP.\n")
        for key, value in additions.items():
            target.write(f"{key}={value}\n")
    print("Added independent Stage 2 credentials; actions disabled. No secret values printed.")


if __name__ == "__main__":
    main()
