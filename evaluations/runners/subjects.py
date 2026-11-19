"""Subjects see PublicCase + read-only MCP only; no controller labels or setup handles."""

import asyncio
import time

from evaluations.runners.contracts import Choice, Prediction
from opspilot.agent.evidence import arguments_for, parse_response
from opspilot.agent.schemas import DiagnosticStep, RunRequest
from opspilot.agent.workflow import Investigation


async def read(mcp, name, public, service=None):
    args = arguments_for(
        DiagnosticStep(
            tool_name=name,
            service_name=service or public.service_name,
            rationale="Read operational evidence.",
            limit=10,
        ),
        public.incident_id,
        {public.service_name.value, "payment-service", "inventory-service"}
        if public.service_name == "checkout-service"
        else {public.service_name.value},
    )
    response = await mcp.call(name, args)
    request, data, error = parse_response(name, response, args)
    return {
        "request_id": request,
        "tool_name": name,
        "service_name": service or public.service_name,
        "data": data,
        "error": error,
    }


async def baseline(public, mcp):
    """Hand-written thresholds, versioned by report source hashes. No model."""
    observations = [
        await read(mcp, name, public)
        for name in [
            "get_incident",
            "get_service_metrics",
            "search_service_logs",
            "get_dependency_status",
            "list_recent_deployments",
        ]
    ]
    by_tool = {o["tool_name"]: o for o in observations}
    if any(o["error"] for o in observations):
        return Prediction(status="abstained", error_code="MISSING_TOOL_EVIDENCE")
    metrics = by_tool["get_service_metrics"]["data"]["items"]
    if not metrics:
        return Prediction(status="abstained")
    metric = metrics[0]
    logs = by_tool["search_service_logs"]["data"]["items"]
    logs = [log for log in logs if log["run_id"] == metric["run_id"]]
    deps = by_tool["get_dependency_status"]["data"]["dependencies"]
    bad_deps = [d for d in deps if d["status"] == "degraded"]
    if metric["error_rate"] < 0.2 and metric["p95_latency_ms"] < 300:
        return Prediction(status="abstained")
    if logs and metric["error_rate"] >= 0.5 and all(log["status_code"] == 200 for log in logs):
        return Prediction(status="abstained")
    if not logs and not deps:
        return Prediction(status="abstained")
    service, mechanism = public.service_name, None
    if len(bad_deps) > 1:
        return Prediction(status="abstained")
    if bad_deps and (
        metric["db_pool_utilization"] >= 0.95
        or metric["worker_utilization"] >= 0.95
        and metric["error_rate"] >= 0.2
    ):
        # Do not overwrite independent local resource evidence with a dependency
        # explanation. These observations cannot establish a unique root cause.
        return Prediction(status="abstained")
    if bad_deps:
        service = bad_deps[0]["service_name"]
        m = bad_deps[0].get("metric") or {}
    else:
        m = metric
    if m.get("db_pool_utilization", 0) >= 0.95:
        mechanism = "database_pool"
    elif m.get("worker_utilization", 0) >= 0.95 and m.get("error_rate", 0) >= 0.2:
        mechanism = "worker_capacity"
    elif bad_deps or service == "payment-service" and m.get("error_rate", 0) >= 0.9:
        mechanism = "dependency_unavailable"
    elif any(
        d["configuration"].get("tax_mode") == "unsupported-v0"
        for d in by_tool["list_recent_deployments"]["data"]["items"][:1]
    ):
        mechanism = "configuration"
    elif m.get("p95_latency_ms", 0) >= 500:
        mechanism = "processing_latency"
    if mechanism is None:
        return Prediction(status="abstained")
    return Prediction(
        status="diagnosed",
        service=service,
        mechanism=mechanism,
        evidence_refs=["e002"] + (["e003"] if logs else []) + (["e004"] if deps else []),
        evidence_supported=bool(logs or deps),
    )


async def llm_tools(public, mcp, model):
    observations = []
    calls = 0
    inputs = outputs = 0
    complete = True
    started = time.monotonic()
    for index in range(public.max_model_calls):
        remaining = public.max_seconds - (time.monotonic() - started)
        if remaining <= 0:
            break
        reply = await asyncio.wait_for(
            model.generate(
                "investigation_planning",
                {
                    "goal": public.goal,
                    "incident_id": public.incident_id,
                    "service_name": public.service_name.value,
                    "observations": observations,
                    "remaining_tool_calls": public.max_tool_calls - calls,
                    "instructions": (
                        "Choose investigate with a read-only step, diagnose with a "
                        "mechanism and cited evidence, or abstain. A tool error is not "
                        "fault evidence."
                    ),
                },
                Choice,
            ),
            timeout=min(remaining, public.call_timeout_seconds),
        )
        inputs += reply.input_tokens or 0
        outputs += reply.output_tokens or 0
        complete &= reply.input_tokens is not None and reply.output_tokens is not None
        choice = Choice.model_validate(reply.value.model_dump())
        if choice.decision != "investigate":
            refs = {o["id"] for o in observations}
            selected = [
                o for o in observations if o["id"] in choice.evidence_refs and not o["error"]
            ]
            quantitative = any(
                o["tool_name"] == "get_service_metrics"
                and any(m["requests"] > 0 for m in o["data"]["items"])
                or o["tool_name"] == "get_service_health"
                and bool(o["data"].get("metric"))
                for o in selected
            )
            independent = any(
                o["tool_name"] == "search_service_logs"
                and bool(o["data"]["items"])
                or o["tool_name"] == "get_dependency_status"
                and bool(o["data"]["dependencies"])
                or o["tool_name"] == "list_recent_deployments"
                and any(d["configuration"] for d in o["data"]["items"])
                for o in selected
            )
            supported = (
                choice.service_name is not None
                and choice.mechanism is not None
                and len(choice.evidence_refs) >= 2
                and len(choice.evidence_refs) == len(set(choice.evidence_refs))
                and set(choice.evidence_refs) <= refs
                and quantitative
                and independent
            )
            return Prediction(
                status="diagnosed" if choice.decision == "diagnose" else "abstained",
                service=choice.service_name,
                mechanism=choice.mechanism,
                evidence_refs=choice.evidence_refs,
                evidence_supported=supported,
                input_tokens=inputs if complete else None,
                output_tokens=outputs if complete else None,
                model_calls=index + 1,
            )
        if calls >= public.max_tool_calls or not choice.step:
            break
        args = arguments_for(
            choice.step,
            public.incident_id,
            {public.service_name.value, "payment-service", "inventory-service"}
            if public.service_name == "checkout-service"
            else {public.service_name.value},
        )
        response = await asyncio.wait_for(
            mcp.call(choice.step.tool_name, args), timeout=public.call_timeout_seconds
        )
        request, data, error = parse_response(choice.step.tool_name, response, args)
        calls = len(observations) + 1
        observations.append(
            {
                "id": f"e{calls:03d}",
                "request_id": request,
                "tool_name": choice.step.tool_name,
                "data": data,
                "error": error,
                "untrusted_data": True,
            }
        )
    return Prediction(
        status="timeout",
        error_code="BUDGET_EXHAUSTED",
        input_tokens=inputs if complete else None,
        output_tokens=outputs if complete else None,
        model_calls=public.max_model_calls,
    )


async def structured(public, mcp, model):
    result = await Investigation(model, mcp, RunRequest.model_validate(public.model_dump())).run()
    cause = result.candidate_root_cause
    if cause:
        # C reserves one remaining diagnostic call for a fresh quantitative readback.
        # This is pre-action verification. Post-action verification still requires approval.
        if len(result.tool_call_history) >= public.max_tool_calls:
            return Prediction(status="timeout", error_code="NO_VERIFICATION_BUDGET")
        checked = await asyncio.wait_for(
            read(mcp, "get_service_health", public, cause.service_name),
            timeout=public.call_timeout_seconds,
        )
        if checked["error"] or checked["data"]["status"] != "degraded":
            return Prediction(status="abstained", error_code="DIAGNOSTIC_VERIFICATION_INCONCLUSIVE")
    # The existing agent emits prose + a typed remediation. Use a frozen conservative
    # mapping; no scorer model, oracle label or substring of the private fixture ID.
    mechanism = None
    if cause and result.proposed_remediation:
        action = result.proposed_remediation.action
        text = cause.explanation.lower()
        if action == "restart_simulated_worker":
            mechanism = "worker_capacity"
        elif action == "rollback_simulated_configuration":
            mechanism = "configuration"
        elif action == "reset_simulated_dependency":
            mechanism = (
                "database_pool"
                if any(w in text for w in ["database", "connection", "pool"])
                else "dependency_unavailable"
            )
        elif "slow" in text or "processing" in text:
            mechanism = "processing_latency"
    return Prediction(
        status={
            "completed": "diagnosed",
            "abstained": "abstained",
            "failed": "failed",
            "budget_exhausted": "timeout",
        }[result.run_status],
        service=cause.service_name if cause else None,
        mechanism=mechanism,
        evidence_refs=cause.evidence_refs if cause else [],
        evidence_supported=cause is not None,
        input_tokens=result.usage.input_tokens if result.usage.usage_complete else None,
        output_tokens=result.usage.output_tokens if result.usage.usage_complete else None,
        model_calls=result.usage.model_calls,
        error_code=result.errors[-1].code if result.errors else None,
    )
