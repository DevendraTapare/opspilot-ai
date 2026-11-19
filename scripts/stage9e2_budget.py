"""Experiment-local monotonic reservation ledger. No provider-invoice guarantee."""

import json
import threading
import time

import httpx2

from opspilot.agent.budgets import estimate_input_tokens
from opspilot.agent.diagnostics import ModelDiagnostic
from opspilot.agent.provider_policy import validate_groq_request
from opspilot.agent.providers import ModelFailure

BASE = "https://api.groq.com/openai/v1"
MODEL = "openai/gpt-oss-20b"
# Integer nanodollars: checked list prices $0.075/M input, $0.30/M output.
INPUT_PRICE, OUTPUT_PRICE = 75, 300
LOCAL_CEILING = 20_000_000  # $0.02; not the provider's billing system.


class ReservationGuard:
    def __init__(self, folder, *, ceiling=LOCAL_CEILING):
        if type(ceiling) is not int or not 0 < ceiling <= LOCAL_CEILING:
            raise ValueError("ceiling must be a positive integer no greater than $0.02")
        self.path = folder / "requests.json"
        self.ceiling = ceiling
        self.charged = self.estimated_tokens = 0
        self.rows = []
        self.stopped = None
        self.inflight = False
        self.started = time.monotonic()
        self.lock = threading.Lock()
        # An existing ledger cannot silently start over after a restart.
        with self.path.open("x", encoding="utf-8") as stream:
            json.dump(self.snapshot(), stream)

    def snapshot(self):
        return {
            "version": "9e2-reservations-1",
            "ceiling_nanodollars": self.ceiling,
            "accounted_nanodollars": self.charged,
            "accounted_usd": self.charged / 1_000_000_000,
            "estimated_tokens_reserved": self.estimated_tokens,
            "stopped": self.stopped,
            "requests": self.rows,
        }

    def persist(self):
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(self.snapshot(), indent=2), encoding="utf-8")
        temporary.replace(self.path)

    def stop(self, code):
        with self.lock:
            self.stopped = self.stopped or code
            self.persist()

    def reserve(self, body, stage):
        with self.lock:
            if self.stopped:
                raise ModelFailure(self.stopped)
            if self.inflight:
                raise ModelFailure("CONCURRENT_PROVIDER_REQUEST_REJECTED")
            allowed = {
                "model",
                "messages",
                "stream",
                "max_tokens",
                "tools",
                "tool_choice",
                "parallel_tool_calls",
                "response_format",
                "reasoning_effort",
                "temperature",
                "include_reasoning",
            }
            if (
                set(body) - allowed
                or type(body.get("max_tokens")) is not int
                or body.get("model") != MODEL
                or body.get("max_tokens") != 1600
                or "max_completion_tokens" in body
                or body.get("reasoning_effort") != "medium"
                or body.get("include_reasoning") is not False
                or body.get("temperature") != 0.2
            ):
                raise ModelFailure("EXPERIMENT_PROFILE_REJECTED")
            validate_groq_request(body)
            estimate = estimate_input_tokens(body)
            reserved = estimate * INPUT_PRICE + 1600 * OUTPUT_PRICE
            failure = (
                "EXPERIMENT_DEADLINE"
                if time.monotonic() - self.started >= 600
                else "REQUEST_BUDGET_EXHAUSTED"
                if len(self.rows) >= 11
                else "PROMPT_ESTIMATE_EXHAUSTED"
                if estimate > 20000
                else "TOKEN_ESTIMATE_EXHAUSTED"
                if self.estimated_tokens + estimate + 1600 > 160000
                else "COST_BUDGET_EXHAUSTED"
                if self.charged + reserved > self.ceiling
                else None
            )
            if failure:
                self.stopped = failure
                self.persist()
                raise ModelFailure(failure)
            row = {
                "number": len(self.rows) + 1,
                "stage": stage,
                "estimated_input_units": estimate,
                "maximum_output_tokens": 1600,
                "reserved_nanodollars": reserved,
                "cost_complete": False,
                "http_status": None,
            }
            self.charged += reserved
            self.estimated_tokens += estimate + 1600
            self.rows.append(row)
            self.inflight = True
            try:
                self.persist()  # Must succeed before any network dispatch.
            except OSError:
                self.stopped = "LEDGER_PERSISTENCE_FAILED"
                self.inflight = False
                raise ModelFailure(self.stopped) from None
            return row

    def finish(self, row, *, status=None, value=None, headers=None, error=None, latency=0):
        with self.lock:
            diagnostic = ModelDiagnostic()
            diagnostic.metadata(value or {}, status, headers or {})
            diagnostic.category = "provider_response" if status == 200 else "provider_rejected"
            diagnostic.outcome = "received" if status == 200 else "rejected"
            row.update(http_status=status, latency_ms=latency, diagnostic=diagnostic.finish())
            if error:
                row["failure"] = error
            if diagnostic.input_tokens is not None and diagnostic.output_tokens is not None:
                actual = (
                    diagnostic.input_tokens * INPUT_PRICE + diagnostic.output_tokens * OUTPUT_PRICE
                )
                row.update(reported_list_price_nanodollars=actual, cost_complete=True)
                # Never release reservations, including after low reported usage.
                if actual > row["reserved_nanodollars"]:
                    self.charged += actual - row["reserved_nanodollars"]
                    self.stopped = "USAGE_EXCEEDED_RESERVATION"
                if (
                    diagnostic.input_tokens > row["estimated_input_units"]
                    or diagnostic.output_tokens > 1600
                ):
                    self.stopped = "USAGE_EXCEEDED_RESERVATION"
            if error or status != 200:
                self.stopped = self.stopped or "PROVIDER_FAILURE_STOP"
            self.inflight = False
            self.persist()


class GuardedTransport(httpx2.AsyncBaseTransport):
    def __init__(self, guard, stage, actual=None):
        self.guard, self.stage = guard, stage
        self.actual = actual or httpx2.AsyncHTTPTransport(retries=0)

    async def handle_async_request(self, request):
        if request.method != "POST" or str(request.url) != BASE + "/chat/completions":
            raise ModelFailure("PROVIDER_ENDPOINT_REJECTED")
        body = json.loads(request.content)
        row = self.guard.reserve(body, self.stage)
        started = time.monotonic()
        response, value = None, None
        failure = "TRANSPORT_OR_RESPONSE_FAILURE"
        try:
            response = await self.actual.handle_async_request(request)
            raw = bytearray()
            async for chunk in response.aiter_bytes():
                raw.extend(chunk)
                if len(raw) > 131072:
                    raise ModelFailure("MODEL_RESPONSE_TOO_LARGE")
            value = json.loads(raw)
            failure = None
            headers = {
                k: v
                for k, v in response.headers.items()
                if k.lower() not in {"content-encoding", "content-length", "transfer-encoding"}
            }
            return httpx2.Response(response.status_code, content=bytes(raw), headers=headers)
        finally:
            try:
                if response is not None:
                    await response.aclose()
            finally:
                self.guard.finish(
                    row,
                    status=response.status_code if response is not None else None,
                    value=value,
                    headers=response.headers if response is not None else None,
                    error=failure,
                    latency=round((time.monotonic() - started) * 1000, 3),
                )

    async def aclose(self):
        await self.actual.aclose()
