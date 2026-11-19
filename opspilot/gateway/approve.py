"""Local human operator CLI. No --yes, approval booleans, or noninteractive path."""

import argparse
from uuid import UUID

from opspilot.config import Settings
from opspilot.db import make_engine, session_factory
from opspilot.gateway.approvals import ACTION_SCENARIOS, approve_interactively
from opspilot.gateway.security import AuthorizerSettings
from opspilot.schemas import ServiceName


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--caller", required=True)
    parser.add_argument("--action", choices=sorted(ACTION_SCENARIOS), required=True)
    parser.add_argument("--service", choices=list(ServiceName), required=True)
    parser.add_argument("--fault-id", type=UUID, required=True)
    parser.add_argument("--ttl", type=int, default=120)
    args = parser.parse_args()
    settings = AuthorizerSettings(_env_file=".env")
    # Issuance uses the trusted local operator's DB credential, never the backend role.
    engine = make_engine(Settings().database_url.get_secret_value())
    try:
        with session_factory(engine).begin() as session:
            approval_id = approve_interactively(
                session,
                settings,
                args.caller,
                args.action,
                args.service,
                str(args.fault_id),
                args.ttl,
            )
        print(f"Approved one execution. Approval ID: {approval_id}")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
