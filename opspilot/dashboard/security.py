import hashlib
import hmac
import json
import secrets
import threading
import time
from collections import defaultdict, deque
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, Request
from sqlalchemy.orm import Session

from opspilot.durable.contracts import HumanOperator
from opspilot.gateway.approvals import utc
from opspilot.models import DashboardSession

COOKIE = "opspilot_session"


def session_digest(principal, token):
    # Credential/account rotation changes the lookup digest without storing a
    # credential or token in the session row. Legacy plain-SHA sessions fail closed.
    binding = f"session-v2:{principal.subject}:{principal.os_user.casefold()}:{token}"
    return hmac.new(
        bytes.fromhex(principal.token_sha256), binding.encode(), hashlib.sha256
    ).hexdigest()


class Security:
    def __init__(self, settings, operator, engine):
        self.settings, self.operator, self.engine = settings, operator, engine
        self.attempts = defaultdict(deque)
        self.lock = threading.Lock()

    def limit(self, key, count=30):
        with self.lock:
            times = self.attempts[key]
            now = time.monotonic()
            while times and times[0] < now - 60:
                times.popleft()
            if len(times) >= count:
                raise HTTPException(429, "RATE_LIMITED")
            times.append(now)

    def boundary(self, request: Request):
        provided = request.headers.get("x-dashboard-key", "")
        if not hmac.compare_digest(provided, self.settings.service_key.get_secret_value()):
            raise HTTPException(401, "BFF_AUTHENTICATION_REQUIRED")
        if request.method not in {"GET", "HEAD"}:
            if request.headers.get("origin") != self.settings.origin:
                raise HTTPException(403, "ORIGIN_REJECTED")
            if request.headers.get("content-type", "").split(";")[0] != "application/json":
                raise HTTPException(415, "JSON_REQUIRED")

    def principal(self, request, required=True):
        token = request.cookies.get(COOKIE, "")
        if len(token) != 64:
            if required:
                raise HTTPException(401, "HUMAN_LOGIN_REQUIRED")
            return None
        with Session(self.engine) as session:
            for principal in self.principals():
                row = session.get(DashboardSession, session_digest(principal, token))
                if (
                    row
                    and row.subject == principal.subject
                    and not row.revoked_at
                    and utc(row.expires_at) > datetime.now(UTC)
                ):
                    return principal
        if required:
            raise HTTPException(401, "HUMAN_SESSION_EXPIRED")
        return None

    def principals(self):
        return [
            HumanOperator.model_validate(entry)
            for entry in json.loads(self.operator.operators.get_secret_value())
        ]

    def issue(self, principal, response):
        token = secrets.token_hex(32)
        with Session(self.engine) as session, session.begin():
            session.add(
                DashboardSession(
                    token_sha256=session_digest(principal, token),
                    subject=principal.subject,
                    expires_at=datetime.now(UTC) + timedelta(minutes=30),
                )
            )
        response.set_cookie(
            COOKIE,
            token,
            httponly=True,
            samesite="strict",
            max_age=1800,
            secure=self.settings.origin.startswith("https://"),
            path="/",
        )

    def revoke(self, request, response):
        token = request.cookies.get(COOKIE, "")
        with Session(self.engine) as session, session.begin():
            for principal in self.principals():
                row = session.get(DashboardSession, session_digest(principal, token))
                if row and row.subject == principal.subject:
                    row.revoked_at = datetime.now(UTC)
        response.delete_cookie(COOKIE, path="/")
