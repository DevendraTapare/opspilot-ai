"""Preflight plan by default; execute once only AFTER explicit approval of version 9e2-1."""

import argparse
import asyncio
import json
from datetime import UTC, datetime
from uuid import uuid4

from opspilot.agent.providers import HTTPDecisionModel, ModelFailure
from opspilot.agent.schemas import RunRequest
from opspilot.agent.workflow import Investigation
from scripts.compare_groq_models import ROOT, save
from scripts.stage9e2_budget import BASE, MODEL, GuardedTransport, ReservationGuard

LIMITS = {
    "max_model_calls": 11,
    "max_tool_calls": 5,
    "max_investigation_rounds": 4,
    "max_seconds": 600,
    "call_timeout_seconds": 30,
    "max_prompt_estimated_tokens": 20000,
    "max_estimated_tokens": 160000,
}
PLAN = {
    "version": "9e2-1",
    "approval": "Required; not approved",
    "investigations": 1,
    "case": "op5-001",
    "split": "calibration",
    "model": MODEL,
    "limits": LIMITS,
    "maximum_output_tokens_per_request": 1600,
    "maximum_cumulative_output_tokens": 17600,
    "reasoning_effort": "medium",
    "minimum_request_spacing_seconds": 12,
    "token_reset_guard_seconds": 1,
    "original_requested_outer_usd": 0.05,
    "local_reservation_ceiling_usd": 0.02,
    "maximum_estimated_list_price_usd": 0.01596,
    "prices_usd_per_million_input_output": [0.075, 0.30],
    "accounting": (
        "Integer nanodollars; persist before dispatch; no refunds; "
        "missing usage retains full reservation"
    ),
    "invoice_guarantee": False,
    "billing_limit": (
        "Byte-based admission estimate is not certified tokenizer/billing data; "
        "no account-wide or invoice guarantee"
    ),
    "request_slots": (
        "1 triage + up to 4*(planning + assessment) + 1 root cause + 1 remediation proposal"
    ),
    "mcp_calls": "1 bootstrap incident read + up to 4 model-selected read-only diagnostics",
    "stop_http": [400, 413, 429],
    "stop": (
        "Any non-200 response, invalid/incomplete output/citations, transport error, "
        "quota/access denial, budget/deadline, ledger failure"
    ),
    "automatic_retries": 0,
    "preliminary_inference_probes": 0,
    "remediation_execution": False,
    "default_model_change": False,
    "evidence_validation_change": False,
    "benchmark_expansion": False,
    "success": [
        "Supported final diagnosis: existing gates, evidence review and private grader pass",
        (
            "Correct evidence-based abstention: explicit model abstain, no failure, "
            "no proposal, independent review confirms genuinely insufficient/contradictory evidence"
        ),
    ],
    "not_success": (
        "Incomplete, budget exhaustion, transport/HTTP/schema/citation failure; "
        "safe abstention on sufficient answerable evidence is not successful diagnosis"
    ),
    "outputs": (
        "Plan, pre-dispatch ledger, validated decisions, final state/evidence, "
        "private grade, fixture/effect checks, review-required outcome"
    ),
}


class RecordedModel:
    mode, provider, model = "real", "groq", MODEL

    def __init__(self, guard, key):
        self.guard, self.decisions = guard, []
        self.adapter = HTTPDecisionModel("groq", MODEL, BASE, key, reasoning_effort="medium")

    def estimate_request(self, stage, context, schema):
        return self.adapter.estimate_request(stage, context, schema)

    async def wait_for_capacity(self):
        if self.guard.stopped:
            raise ModelFailure(self.guard.stopped)
        await self.adapter.wait_for_capacity()

    async def generate(self, stage, context, schema):
        self.adapter.transport = GuardedTransport(self.guard, stage)
        row = {"stage": stage, "evidence_ids": [o["id"] for o in context["observations"]]}
        self.decisions.append(row)
        try:
            reply = await self.adapter.generate(stage, context, schema)
            row.update(
                validated_decision=reply.value.model_dump(mode="json"), diagnostic=reply.diagnostic
            )
            return reply
        except BaseException:
            self.guard.stop("MODEL_DECISION_FAILURE_STOP")
            raise


def review_candidate(state, safety_ok):
    """No automatic semantic judge; never turn a failure into a successful abstention."""
    if not safety_ok or state.errors:
        return "FAILURE_OR_INCOMPLETE"
    if (
        state.run_status == "completed"
        and state.candidate_root_cause
        and state.proposed_remediation
    ):
        return "DIAGNOSIS_REQUIRES_INDEPENDENT_REVIEW"
    if (
        state.run_status == "abstained"
        and state.assessment
        and state.assessment.decision == "abstain"
        and not state.candidate_root_cause
        and not state.proposed_remediation
        and len(state.observations) > 1
    ):
        return "ABSTENTION_REQUIRES_INDEPENDENT_REVIEW"
    return "FAILURE_OR_INCOMPLETE"


async def execute(folder):
    # No inference key, database environment or network setup is loaded by plan mode.
    from sqlalchemy import func, select
    from sqlalchemy.orm import Session

    from evaluations.runners.dataset import load
    from evaluations.runners.environment import Environment
    from evaluations.runners.metrics import score
    from opspilot.agent.mcp import connect
    from opspilot.gateway.contracts import READ_TOOLS
    from opspilot.models import ActionExecution
    from scripts.compare_groq_models import load_key
    from scripts.review_stage9 import environment
    from scripts.run_stage9c import fixture_hash
    from scripts.verify_stage9b import prediction

    report = {"plan": PLAN, "success": False, "outcome": "FAILURE_OR_INCOMPLETE"}
    model, guard = None, None
    save(folder / "plan.json", PLAN)
    try:
        case = next(c for c in load("calibration") if c.id == PLAN["case"])
        with Environment(environment()["OPSPILOT_TEST_DATABASE_URL"]).start() as controller:
            public = controller.prepare(case)
            request = RunRequest.model_validate({**public.model_dump(), **LIMITS})
            before = fixture_hash(controller.engine)
            guard = ReservationGuard(folder)
            model = RecordedModel(guard, load_key().get_secret_value())
            async with connect(controller.url, controller.token) as mcp:
                state = await Investigation(model, mcp, request).run()
            save(folder / "state.json", state.model_dump(mode="json"))
            calls = [
                {"name": c.tool_name, "arguments": c.arguments, "outcome": c.outcome}
                for c in state.tool_call_history
            ]
            with Session(controller.engine) as session:
                effects = session.scalar(select(func.count()).select_from(ActionExecution))
            same = before == fixture_hash(controller.engine)
            safe = (
                same
                and effects == 0
                and not guard.stopped
                and len(calls) <= 5
                and len(guard.rows) <= 11
                and all(c["name"] in READ_TOOLS for c in calls)
                and guard.charged <= guard.ceiling
            )
            trial = score(
                case, "stage9e2-gptoss", "real", prediction(state), state.latency_ms, calls, effects
            )
            report.update(
                run_status=state.run_status,
                fixture_unchanged=same,
                action_execution_records=effects,
                outcome=review_candidate(state, safe),
                latency_ms=state.latency_ms,
                trial=trial.model_dump(mode="json"),
                independent_review="Required before any PASS; no extra model calls",
            )
    except Exception as exc:
        report["runner_error_type"] = type(exc).__name__  # No raw errors, keys or DSNs.
    finally:
        if model:
            save(folder / "decisions.json", model.decisions)
        report["budget"] = guard.snapshot() if guard else None
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
        / "evaluations/reports/stage9e2"
        / (datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:6])
    )
    folder.mkdir(parents=True, exist_ok=False)
    try:
        report = asyncio.run(execute(folder))
    except Exception:
        print(json.dumps({"outcome": "LIVE_SETUP_FAILED", "report": str(folder.relative_to(ROOT))}))
        return 2
    print(str(folder.relative_to(ROOT)))
    return 3 if report["outcome"].endswith("REVIEW") else 2


if __name__ == "__main__":
    raise SystemExit(main())
