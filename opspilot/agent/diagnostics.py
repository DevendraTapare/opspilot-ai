"""Content-free diagnostics. Never retain provider messages, failed output or reasoning."""

import json
import re
import time
from dataclasses import asdict, dataclass, field

from pydantic import ValidationError

from opspilot.agent.provider_policy import quota_scope, reset_seconds


def _identifier(value):
    # Correlation IDs only, never arbitrary header/body text.
    if (
        isinstance(value, str)
        and re.fullmatch(
            r"(?:req_[A-Za-z0-9-]{8,80}|chatcmpl-[A-Za-z0-9-]{8,80}|"
            r"[a-fA-F0-9]{8}(?:-[a-fA-F0-9]{4}){3}-[a-fA-F0-9]{12})",
            value,
        )
        and not any(marker in value.lower() for marker in ("gsk", "secret", "bearer"))
    ):
        return value
    return None


@dataclass
class ModelDiagnostic:
    category: str = "request_construction"
    outcome: str = "pending"
    http_status: int | None = None
    request_id: str | None = None
    completion_id: str | None = None
    finish_reason: str | None = None
    provider_error_code: str | None = None
    quota_scope: str | None = None
    quota_remaining_requests_per_day: int | None = None
    quota_remaining_tokens_per_minute: int | None = None
    quota_reset_tokens_seconds: float | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    reasoning_tokens: int | None = None
    response_bytes: int = 0
    content_chars: int | None = None
    validation_errors: list[dict] = field(default_factory=list)
    failed_generation: dict | None = None
    timings_ms: dict = field(default_factory=dict)
    _started: float = field(default_factory=time.monotonic, repr=False)

    def metadata(self, value, status, headers):
        self.http_status = status
        self.request_id = _identifier(headers.get("x-request-id"))
        self.quota_scope = quota_scope(value, status)
        self.quota_reset_tokens_seconds = reset_seconds(headers.get("x-ratelimit-reset-tokens"))
        for header, target in (
            ("x-ratelimit-remaining-requests", "quota_remaining_requests_per_day"),
            ("x-ratelimit-remaining-tokens", "quota_remaining_tokens_per_minute"),
        ):
            count = headers.get(header)
            if isinstance(count, str) and re.fullmatch(r"[0-9]{1,10}", count):
                setattr(self, target, int(count))
        if not isinstance(value, dict):
            return
        self.completion_id = _identifier(value.get("id"))
        if not self.request_id and isinstance(value.get("x_groq"), dict):
            self.request_id = _identifier(value["x_groq"].get("id"))
        usage = value.get("usage")
        if isinstance(usage, dict):
            for source, target in (
                ("prompt_tokens", "input_tokens"),
                ("completion_tokens", "output_tokens"),
            ):
                count = usage.get(source)
                if type(count) is int and 0 <= count <= 1_000_000:
                    setattr(self, target, count)
            details = usage.get("completion_tokens_details")
            count = details.get("reasoning_tokens") if isinstance(details, dict) else None
            if type(count) is int and 0 <= count <= 1_000_000:
                self.reasoning_tokens = count
        choices = value.get("choices")
        if isinstance(choices, list) and choices and isinstance(choices[0], dict):
            reason = choices[0].get("finish_reason")
            self.finish_reason = (
                reason
                if reason in {"stop", "tool_calls", "length", "content_filter"}
                else "unknown"
            )
        error = value.get("error")
        if isinstance(error, dict):
            code = error.get("code")
            self.provider_error_code = (
                code
                if code
                in {
                    "json_validate_failed",
                    "tool_use_failed",
                    "invalid_api_key",
                    "rate_limit_exceeded",
                    "context_length_exceeded",
                    "invalid_json_schema",
                }
                else "other"
            )

    def invalid(self, exc, schema):
        """Do not retain Pydantic input/ctx/msg or unknown property names."""
        fields = set()

        def visit(node):
            if isinstance(node, dict):
                fields.update(node.get("properties", {}))
                for child in node.values():
                    visit(child)
            elif isinstance(node, list):
                for child in node:
                    visit(child)

        visit(schema.model_json_schema())
        errors = exc.errors(include_url=False, include_context=False, include_input=False)
        self.validation_errors = [
            {
                "type": e["type"],
                "path": [p if isinstance(p, int) or p in fields else "<unknown>" for p in e["loc"]],
            }
            for e in errors[:16]
        ]
        self.category = (
            "response_parsing"
            if any(e["type"] == "json_invalid" for e in errors)
            else "schema_validation"
        )

    def inspect_failed_generation(self, value, schema):
        # A provider may return the failed generation on HTTP 400. Validate only
        # in memory; never save any text, private reasoning or exception message.
        error = value.get("error") if isinstance(value, dict) else None
        text = error.get("failed_generation") if isinstance(error, dict) else None
        if not isinstance(text, str) or len(text) > 65536:
            return
        if not text:
            # Empty provider diagnostics do not prove a malformed model generation.
            self.failed_generation = {
                "chars": 0,
                "category": "empty_provider_diagnostic",
                "validation_errors": [],
            }
            return
        result = ModelDiagnostic()
        try:
            from opspilot.agent.providers import parse_model_output

            parse_model_output(text, schema)
            result.category = "schema_valid"
        except ValidationError as exc:
            result.invalid(exc, schema)
        self.failed_generation = {
            "chars": len(text),
            "category": result.category,
            "validation_errors": result.validation_errors,
        }

    def finish(self):
        self.timings_ms["total"] = round((time.monotonic() - self._started) * 1000, 3)
        value = asdict(self)
        value.pop("_started")
        # Reject accidental non-JSON diagnostics during development.
        json.dumps(value, allow_nan=False)
        return value
