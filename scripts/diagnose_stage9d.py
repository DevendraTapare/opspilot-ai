"""Stage 9D isolation probes. Default command prints a plan and makes no network calls.

--execute-approved-plan is for an operator AFTER separate budget approval. It is
not a remediation approval and provides no state-changing MCP capability.
"""

import argparse
import asyncio
import json
import time
from datetime import UTC, datetime
from typing import Literal
from uuid import uuid4

import httpx2
from pydantic import Field, ValidationError

from opspilot.agent.conversation import bind_citation_schema
from opspilot.agent.diagnostics import ModelDiagnostic
from opspilot.agent.providers import SYSTEM, ModelFailure, parse_model_output, strict_schema
from opspilot.agent.schemas import (
    Assessment,
    Contract,
    Remediation,
    RootCause,
    RunRequest,
    Triage,
)
from opspilot.agent.workflow import Investigation
from scripts.compare_groq_models import (
    MODELS,
    ROOT,
    Budget,
    ComparisonModel,
    StrictDiagnosis,
    collect_packet,
    digest,
    load_key,
    probe,
    save,
    settings,
    validate_diagnosis,
)

MODEL = MODELS[1]
PLAN = {
    "version": "9d-1",
    "model": MODEL,
    "provider": "groq",
    "maximum_provider_requests": 19,
    "maximum_output_tokens_per_call": 1600,
    "maximum_request_bytes_with_reserve": 65000,
    "maximum_reserved_usd": 0.15,
    "worst_case_list_price_estimate_usd": 0.101745,
    "price_per_million_input_output_usd": [0.075, 0.30],
    "phase_requests": {"A": 1, "B": 1, "C": 1, "D": 2, "E": 14},
    "automatic_retries": 0,
    "request_interval_seconds": 12,
    "call_timeout_seconds": 15,
    "E_seconds": 180,
    "E_max_read_tools": 8,
    "reasoning_effort": "medium",
    "temperature": 0.2,
    "include_reasoning": False,
    "calibration_case": "op5-001",
    "held_out": False,
    "early_stops": "401/403/429, reservation cap; E only if A-D all pass",
    "actions": "disabled; no action grants, approvals or remediation calls",
    "billing_caveat": (
        "Application reservation ceiling, not a provider billing guarantee. "
        "Use account-side paid billing disabled/spend limit for a hard account cap. "
        "Missing usage retains full reservation; no model-list requests."
    ),
}


class BasicJSON(Contract):
    status: Literal["ready"]


class MinimalDiagnosis(Contract):
    # Isolation contract only. Never accepted as a production recommendation.
    root_cause: RootCause | None
    uncertainty: list[str] = Field(min_length=1, max_length=5)


SCHEMAS = {
    s.__name__: s
    for s in (
        BasicJSON,
        MinimalDiagnosis,
        StrictDiagnosis,
        Triage,
        Assessment,
        RootCause,
        Remediation,
    )
}


class DiagnosticBudget(Budget):
    async def exchange(self, request, body, phase, actual):
        diagnostic = ModelDiagnostic()
        count = len(self.requests)
        try:
            diagnostic.category = "provider_transport"
            response = await super().exchange(request, body, phase, actual)
            diagnostic.category = "response_extraction"
            value = response.json()
            diagnostic.response_bytes = len(response.content)
            diagnostic.metadata(value, response.status_code, response.headers)
            if response.status_code != 200:
                diagnostic.category = (
                    "provider_schema_enforcement"
                    if diagnostic.provider_error_code == "json_validate_failed"
                    else "provider_request_rejected"
                )
                if response.status_code == 429:
                    diagnostic.category = "provider_rate_limit"
                schema_name = (
                    (body or {}).get("response_format", {}).get("json_schema", {}).get("name")
                )
                if schema_name in SCHEMAS:
                    diagnostic.inspect_failed_generation(value, SCHEMAS[schema_name])
                diagnostic.outcome = "rejected"
            else:
                diagnostic.category, diagnostic.outcome = "response_extraction", "received"
                if diagnostic.finish_reason == "length":
                    diagnostic.category = "output_token_exhaustion"
                    diagnostic.outcome = "rejected"
            return response
        except httpx2.TimeoutException:
            diagnostic.category, diagnostic.outcome = "transport_timeout", "rejected"
            raise
        except (httpx2.HTTPError, OSError):
            diagnostic.category, diagnostic.outcome = "transport_error", "rejected"
            raise
        except ValueError:
            diagnostic.category, diagnostic.outcome = "response_extraction", "rejected"
            raise
        except ModelFailure as exc:
            diagnostic.category = (
                "response_size" if exc.code == "MODEL_RESPONSE_TOO_LARGE" else "request_policy"
            )
            diagnostic.outcome = "rejected"
            raise
        finally:
            if len(self.requests) > count:
                self.requests[-1]["diagnostic"] = diagnostic.finish()
                save(self.folder / "requests.json", self.requests)


def full_messages(state):
    """Reproduce the 9C D prompt/contract exactly, using newly observed evidence."""
    schema = bind_citation_schema(strict_schema(StrictDiagnosis), state.evidence_references)
    evidence = {
        "incident_id": str(state.incident_id),
        "service_name": state.request.service_name.value,
        "observations": [o.model_dump(mode="json") for o in state.observations],
    }
    return [
        {"role": "system", "content": SYSTEM},
        {
            "role": "user",
            "content": json.dumps(
                {
                    "goal": "Assess evidence, compare alternatives, and return a supported "
                    "final diagnosis/remediation or abstain when inconclusive.",
                    "required_output_contract": schema,
                    "untrusted_evidence": evidence,
                },
                separators=(",", ":"),
            ),
        },
    ]


async def structured(budget, phase, schema, messages, state):
    row = {
        "probe": phase,
        "passed": False,
        "schema_valid": False,
        "grounding": "not_assessed",
        "failure_stage": "request_construction",
    }
    started = time.monotonic()
    diagnostic = ModelDiagnostic()
    previous_requests = len(budget.requests)
    try:
        output_schema = bind_citation_schema(strict_schema(schema), state.evidence_references)
        body = {
            "model": MODEL,
            **settings(MODEL),
            "messages": messages,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": schema.__name__,
                    "strict": True,
                    "schema": output_schema,
                },
            },
        }
        row["messages_sha256"] = digest(messages)
        row["schema_sha256"] = digest(body["response_format"])
        row["failure_stage"] = "provider_response"
        message = await budget.call(body, "probe:" + phase)
        row["failure_stage"] = "response_extraction"
        content = message.get("content")
        if not isinstance(content, str) or not content:
            row["failure_stage"] = "empty_response"
            raise ValueError("empty response")
        try:
            result = parse_model_output(content, schema)
        except ValidationError as exc:
            diagnostic.invalid(exc, schema)
            row["failure_stage"] = diagnostic.category
            row["validation_errors"] = diagnostic.validation_errors
            raise
        row["schema_valid"] = True
        if schema is StrictDiagnosis:
            row["failure_stage"] = "evidence_validation"
            validate_diagnosis(result, state)
            row["grounding"] = "passed_existing_citation_and_corroboration_gates"
            row["status"] = result.recommendation.status
        else:
            row["grounding"] = "not_a_full_diagnosis"
        row.update(passed=True, failure_stage=None)
    except Exception as exc:
        if isinstance(exc, ModelFailure):
            row["error_code"] = exc.code
            if len(budget.requests) > previous_requests:
                trace = budget.requests[-1].get("diagnostic", {})
                row["failure_stage"] = trace.get("category", "provider_response")
            else:
                row["failure_stage"] = "request_policy"
        # Never persist exception strings or response contents.
    row["latency_ms"] = round((time.monotonic() - started) * 1000, 3)
    return row


async def isolated_probes(budget, mcp, state):
    rows = []
    rows.append(
        await structured(
            budget,
            "A",
            BasicJSON,
            [
                {"role": "user", "content": 'Return the JSON object {"status":"ready"}.'},
            ],
            state,
        )
    )
    rows.append(
        await structured(
            budget,
            "B",
            MinimalDiagnosis,
            [
                {"role": "system", "content": SYSTEM},
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "goal": "Propose a supported cause or return null when insufficient. "
                            "This is a schema isolation probe, not a final recommendation.",
                            "observations": [o.model_dump(mode="json") for o in state.observations],
                        },
                        separators=(",", ":"),
                    ),
                },
            ],
            state,
        )
    )
    rows.append(await structured(budget, "C", StrictDiagnosis, full_messages(state), state))

    # Actual model-generated call ID, actual MCP output; never synthetic tool output.
    class ToolPhase:
        async def call(self, body, _phase):
            return await budget.call(body, "probe:D-tool")

    selection = await probe(ToolPhase(), MODEL, "B", mcp, state)
    row = {
        "probe": "D",
        "passed": False,
        "failure_stage": "tool_generation_or_execution",
        "tool_selection_passed": selection["passed"],
    }
    if selection["passed"]:
        messages = [
            *selection["messages"],
            {"role": "assistant", "tool_calls": [selection["tool_call"]], "content": None},
            {
                "role": "tool",
                "tool_call_id": selection["tool_call"]["id"],
                "name": "get_service_health",
                "content": json.dumps(selection["tool_result"]),
            },
            full_messages(state)[-1],
        ]
        # Assign the fresh result its own registry ID before the model sees it;
        # e001 in C already belongs to the incident, not this health observation.
        observation = selection["tool_result"]["observation"]
        observation["id"] = f"e{len(state.observations) + 1:03d}"
        from opspilot.agent.schemas import Observation, ToolCall

        state = state.model_copy(deep=True)
        state.observations.append(Observation.model_validate(observation))
        state.evidence_references.append(observation["id"])
        state.tool_call_history.append(
            ToolCall(
                tool_name="get_service_health",
                arguments={"service_name": "checkout-service"},
                outcome="OK",
                evidence_ref=observation["id"],
                latency_ms=0,
                request_id=observation["request_id"],
            )
        )
        messages[-2]["content"] = json.dumps(selection["tool_result"])
        messages[-1] = full_messages(state)[-1]
        row = await structured(budget, "D", StrictDiagnosis, messages, state)
        row["bound_tool_call_id"] = selection["tool_call"]["id"]
    else:
        row["error_code"] = selection.get("error_code")
        if selection.get("error_origin") == "application":
            row["failure_stage"] = "tool_argument_or_result_validation"
        elif budget.requests:
            row["failure_stage"] = (
                budget.requests[-1].get("diagnostic", {}).get("category", row["failure_stage"])
            )
    rows.append(row)
    return rows


class DiagnosticModel(ComparisonModel):
    async def generate(self, stage, context, schema):
        try:
            reply = await super().generate(stage, context, schema)
            self.decisions[-1].clear()
            self.decisions[-1].update(stage=stage, diagnostic=reply.diagnostic)
            return reply
        except Exception as exc:
            self.decisions[-1].clear()
            self.decisions[-1].update(stage=stage, diagnostic=getattr(exc, "diagnostic", None))
            raise


async def live(folder):
    # These imports/controller are reached only after explicit operator invocation.
    from evaluations.runners.dataset import load
    from evaluations.runners.environment import Environment
    from opspilot.agent.mcp import connect
    from scripts.review_stage9 import environment
    from scripts.run_stage9c import fixture_hash

    budget = DiagnosticBudget(folder, load_key(), request_limit=19, cost_limit=0.15)
    report = {"plan": PLAN, "mode": "real", "probes": [], "investigation": None}
    save(folder / "plan.json", PLAN)
    case = next(c for c in load("calibration") if c.id == "op5-001")
    try:
        with Environment(environment()["OPSPILOT_TEST_DATABASE_URL"]).start() as controller:
            public = controller.prepare(case)
            before = fixture_hash(controller.engine)
            async with connect(controller.url, controller.token) as mcp:
                state = await collect_packet(mcp, public)
                report["evidence_sha256"] = digest(
                    [o.model_dump(mode="json") for o in state.observations]
                )
                report["probes"] = await isolated_probes(budget, mcp, state)
                if all(row["passed"] for row in report["probes"]) and not budget.stopped:
                    model = DiagnosticModel(MODEL, budget)
                    result = await Investigation(
                        model, mcp, RunRequest.model_validate(public.model_dump())
                    ).run()
                    report["investigation"] = result.model_dump(mode="json")
                    report["model_diagnostics"] = model.decisions
                report["fixture_unchanged"] = fixture_hash(controller.engine) == before
                from sqlalchemy import func, select
                from sqlalchemy.orm import Session

                from opspilot.models import ActionExecution

                with Session(controller.engine) as session:
                    report["action_execution_records"] = session.scalar(
                        select(func.count()).select_from(ActionExecution)
                    )
    finally:
        report["provider_requests"] = len(budget.requests)
        report["accounted_usd"] = budget.accounted_usd
        report["cost_complete"] = all(r["cost_complete"] for r in budget.requests)
        save(folder / "report.json", report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute-approved-plan", action="store_true")
    args = parser.parse_args()
    if not args.execute_approved_plan:
        print(json.dumps(PLAN, indent=2))
        return 0
    folder = (
        ROOT
        / "evaluations/reports/stage9d"
        / (datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:6])
    )
    folder.mkdir(parents=True, exist_ok=False)
    report = asyncio.run(live(folder))
    print(str(folder.relative_to(ROOT)))
    result = report.get("investigation") or {}
    return (
        0
        if result.get("run_status") == "completed"
        and report.get("fixture_unchanged")
        and report.get("action_execution_records") == 0
        else 2
    )


if __name__ == "__main__":
    raise SystemExit(main())
