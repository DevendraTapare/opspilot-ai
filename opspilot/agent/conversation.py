"""Bounded provider transcript rebuilt from validated state, never raw tool content."""

import json

from opspilot.agent.evidence import arguments_for
from opspilot.agent.schemas import ModelToolCall, Observation, ToolCall


def tool_messages(context, *, references_only=False):
    """Pair actual assistant function IDs with their exact projected MCP result.

    The bootstrap read has no model function call. Errors remain error results;
    they never acquire an evidence ID. No provider reasoning is retained.
    """
    observations = [Observation.model_validate(o) for o in context.get("observations", [])]
    history = [ToolCall.model_validate(t) for t in context.get("tool_history", [])]
    if len(history) > 12 or len(observations) > 12:
        raise ValueError("conversation budget exceeded")
    registry = {o.id: o for o in observations}
    if len(registry) != len(observations):
        raise ValueError("duplicate evidence identifiers")
    messages, seen = [], set()
    for record in history:
        if record.model_call is None:
            continue
        call = ModelToolCall.model_validate(record.model_call.model_dump())
        if call.id in seen:
            raise ValueError("duplicate model function identifier")
        seen.add(call.id)
        step = call.arguments
        actual_arguments = arguments_for(
            step, context["incident_id"], set(context["allowed_services"])
        )
        if step.tool_name != record.tool_name or actual_arguments != record.arguments:
            raise ValueError("model function and executed tool differ")
        if record.outcome == "OK":
            observation = registry.get(record.evidence_ref)
            if (
                observation is None
                or observation.tool_name != record.tool_name
                or observation.service_name != step.service_name
                or record.request_id != observation.request_id
            ):
                raise ValueError("model function result binding rejected")
            result = (
                {
                    "ok": True,
                    "evidence_ref": observation.id,
                    "request_id": observation.request_id,
                    "untrusted_data": True,
                }
                if references_only
                else {"ok": True, "observation": observation.model_dump(mode="json")}
            )
        else:
            if record.evidence_ref is not None:
                raise ValueError("failed call cannot create evidence")
            result = {"ok": False, "error_code": record.outcome, "untrusted_data": True}
        messages.extend(
            [
                {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": call.id,
                            "type": "function",
                            "function": {
                                "name": call.name,
                                "arguments": step.model_dump_json(),
                            },
                        }
                    ],
                },
                {
                    "role": "tool",
                    "tool_call_id": call.id,
                    "name": call.name,
                    "content": json.dumps(result, separators=(",", ":"), allow_nan=False),
                },
            ]
        )
    return messages


def bind_citation_schema(schema, references):
    """Constrain the wire schema to observed IDs; independent validation still runs."""
    if len(references) > 12 or len(set(references)) != len(references):
        raise ValueError("invalid evidence registry")

    def visit(node):
        if isinstance(node, dict):
            if node.get("pattern") == r"^e[0-9]{3}$" and references:
                node["enum"] = references.copy()
            for child in node.values():
                visit(child)
        elif isinstance(node, list):
            for child in node:
                visit(child)

    visit(schema)
    return schema
