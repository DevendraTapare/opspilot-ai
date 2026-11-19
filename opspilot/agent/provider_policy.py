"""Groq wire boundaries and header-driven admission; never retry a provider request."""

import math
import re
import time


def strict_objects(schema):
    """Validate strict object closure without stripping any schema constraints."""

    def visit(node):
        if not isinstance(node, dict):
            raise ValueError("schema node must be an object")
        if node.get("type") == "object":
            properties = node.get("properties", {})
            if node.get("additionalProperties") is not False or set(
                node.get("required", [])
            ) != set(properties):
                raise ValueError("strict object requirements not satisfied")
        if "$ref" in node:
            ref = node["$ref"]
            if not isinstance(ref, str) or not ref.startswith("#/$defs/"):
                raise ValueError("only local definition references are permitted")
            name = ref.removeprefix("#/$defs/")
            if name not in schema.get("$defs", {}):
                raise ValueError("unresolved schema reference")
        for key in ("properties", "$defs"):
            for child in node.get(key, {}).values():
                visit(child)
        if "items" in node:
            visit(node["items"])
        for child in node.get("anyOf", []):
            visit(child)

    visit(schema)


def validate_groq_request(body):
    if body.get("stream") is not False:
        raise ValueError("model streaming is disabled")
    if body.get("tools"):
        if "response_format" in body or body.get("parallel_tool_calls") is not False:
            raise ValueError("incompatible tool request")
        if len(body["tools"]) != 1:
            raise ValueError("one diagnostic selector is required")
        function = body["tools"][0]["function"]
        if function.get("name") != "select_diagnostic_tool":
            raise ValueError("only the diagnostic selector is permitted")
        strict_objects(function["parameters"])
    else:
        if any(key in body for key in ("tools", "tool_choice", "parallel_tool_calls")):
            raise ValueError("structured phase must have no tool controls")
        if any(
            m.get("role") not in {"system", "user"}
            or any(key in m for key in ("tool_calls", "tool_call_id", "function_call"))
            for m in body["messages"]
        ):
            raise ValueError("structured phase must contain no tool protocol")
        output = body.get("response_format", {})
        contract = output.get("json_schema", {})
        if output.get("type") != "json_schema" or contract.get("strict") is not True:
            raise ValueError("strict structured output required")
        strict_objects(contract["schema"])


def reset_seconds(value):
    """Accept bounded provider duration values, not arbitrary header text."""
    if not isinstance(value, str) or len(value) > 40:
        return None
    match = re.fullmatch(r"(?:(\d+)h)?(?:(\d+)m)?(?:(\d+(?:\.\d+)?)s)?", value)
    if not match or not any(match.groups()):
        return None
    h, m, s = match.groups()
    total = int(h or 0) * 3600 + int(m or 0) * 60 + float(s or 0)
    return total if math.isfinite(total) and 0 <= total <= 86400 else None


def quota_scope(value, status):
    """Derive fixed labels in memory; never retain provider message text."""
    if status in {401, 403}:
        return "access_denied"
    if status != 429:
        return None
    error = value.get("error") if isinstance(value, dict) else None
    message = error.get("message") if isinstance(error, dict) else None
    if isinstance(message, str):
        units = {
            "(RPM)": "requests_per_minute",
            "(RPD)": "requests_per_day",
            "(TPM)": "tokens_per_minute",
            "(TPD)": "tokens_per_day",
        }
        found = [label for unit, label in units.items() if unit in message]
        if len(found) == 1:
            return found[0]
    kind = error.get("type") if isinstance(error, dict) else None
    return {"tokens": "tokens_unspecified", "requests": "requests_unspecified"}.get(
        kind, "unclassified"
    )


class GroqCapacity:
    """Per adapter instance, not an organization-wide quota coordinator.

    Wait for the reported token reset after each response instead of guessing
    next-prompt tokenization. Existing workflow deadlines bound this wait.
    """

    def __init__(self):
        self.not_before = 0.0
        self.stopped = None

    def observe(self, headers, status, *, now=None):
        now = time.monotonic() if now is None else now
        reset = reset_seconds(headers.get("x-ratelimit-reset-tokens"))
        if reset is not None:
            self.not_before = max(self.not_before, now + reset + 1)
        remaining = headers.get("x-ratelimit-remaining-requests")
        if isinstance(remaining, str) and re.fullmatch(r"0+", remaining):
            self.stopped = "MODEL_DAILY_LIMIT"
        if status == 429:
            self.stopped = "MODEL_RATE_LIMITED"
        if status in {401, 403}:
            self.stopped = "MODEL_ACCESS_DENIED"

    def delay(self, *, now=None):
        now = time.monotonic() if now is None else now
        return max(0.0, self.not_before - now)
