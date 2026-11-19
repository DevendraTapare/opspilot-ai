"""Plan-only by default. One real investigation ONLY after separate user approval."""

import argparse
import asyncio
import json
from datetime import UTC, datetime
from uuid import uuid4

from opspilot.agent.providers import HTTPDecisionModel, ModelFailure
from opspilot.agent.schemas import RunRequest
from opspilot.agent.workflow import Investigation
from scripts.compare_groq_models import BASE, MODELS, ROOT, Transport, load_key, save
from scripts.diagnose_stage9d import DiagnosticBudget

PLAN = {
    "version": "9e-1",
    "model": MODELS[1],
    "attempts": 1,
    "maximum_provider_requests": 14,
    "maximum_output_tokens_per_call": 1600,
    "maximum_total_output_tokens": 22400,
    "maximum_request_bytes_with_reserve": 65000,
    "maximum_reserved_usd": 0.15,
    "worst_case_list_price_estimate_usd": 0.07497,
    "price_per_million_input_output_usd": [0.075, 0.30],
    "reasoning_effort": "medium",
    "include_reasoning": False,
    "temperature": 0.2,
    "stream": False,
    "automatic_retries": 0,
    "maximum_workflow_seconds": 600,
    "per_call_timeout_seconds": 30,
    "minimum_request_interval_seconds": 12,
    "maximum_read_tools": 8,
    "pacing": "Honor token-reset headers plus one-second guard before next new request",
    "early_stop": "Any provider failure, quota/access rejection, budget or deadline",
    "case": "op5-001",
    "split": "calibration",
    "held_out": False,
    "actions": "Disabled; no remediation approvals or action tools",
    "pass_conditions": [
        "Completed existing LangGraph investigation, no fixture fallback",
        "Existing schema, reference, freshness, corroboration and hypothesis gates pass",
        "Unchanged private calibration grader reports task success and required-tool coverage",
        "At most 8 read-only MCP calls and 14 model requests within time/cost reservation",
        "Unchanged fixture hash and zero action execution records",
    ],
    "failure_conditions": [
        "Abstention on this answerable case, incorrect diagnosis or insufficient tool coverage",
        "Invalid/incomplete output, unsupported citations, HTTP400/429 or provider failure",
        "Timeout, budget exhaustion or any unauthorized/duplicate side effect",
    ],
    "billing": (
        "Application reservation cap; invoice/account tier unverified. "
        "No automatic paid-plan activation."
    ),
    "scope": "One investigation, no preliminary inference probes and no benchmark expansion",
}


class ExperimentBudget(DiagnosticBudget):
    def reserve(self, body, phase):
        row = super().reserve(body, phase)
        if body:
            row["stream"] = body.get("stream")
            row["contains_tool_protocol"] = any(
                m.get("role") == "tool" or "tool_calls" in m for m in body.get("messages", [])
            )
        return row


class RecordedModel:
    mode, provider, model = "real", "groq", MODELS[1]

    def __init__(self, budget):
        self.budget, self.decisions = budget, []
        self.adapter = HTTPDecisionModel(
            "groq", self.model, BASE, budget.key.get_secret_value(), reasoning_effort="medium"
        )

    async def wait_for_capacity(self):
        # Both waits happen within the graph's total deadline, before its model-call timer.
        await self.budget.wait()
        await self.adapter.wait_for_capacity()

    async def generate(self, stage, context, schema):
        row = {"stage": stage, "received_evidence_ids": [o["id"] for o in context["observations"]]}
        self.decisions.append(row)
        self.adapter.transport = Transport(self.budget, "investigation:" + stage)
        try:
            reply = await self.adapter.generate(stage, context, schema)
            row["diagnostic"] = reply.diagnostic
            return reply
        except ModelFailure as exc:
            row.update(error_code=exc.code, diagnostic=exc.diagnostic)
            raise
        except asyncio.CancelledError:
            row["error_code"] = "MODEL_CANCELLED"
            raise


async def execute(folder):
    from sqlalchemy import func, select
    from sqlalchemy.orm import Session

    from evaluations.runners.dataset import load
    from evaluations.runners.environment import Environment
    from evaluations.runners.metrics import score
    from opspilot.agent.mcp import connect
    from opspilot.gateway.contracts import READ_TOOLS
    from opspilot.models import ActionExecution
    from scripts.review_stage9 import environment
    from scripts.run_stage9c import fixture_hash
    from scripts.verify_stage9b import prediction

    report = {
        "mode": "real",
        "plan": PLAN,
        "passed": False,
        "started_at": datetime.now(UTC).isoformat(),
    }
    budget = ExperimentBudget(folder, load_key(), request_limit=14, cost_limit=0.15)
    save(folder / "plan.json", PLAN)
    try:
        case = next(c for c in load("calibration") if c.id == PLAN["case"])
        with Environment(environment()["OPSPILOT_TEST_DATABASE_URL"]).start() as controller:
            public = controller.prepare(case)
            request = RunRequest.model_validate(public.model_dump()).model_copy(
                update={
                    "max_seconds": 600,
                    "call_timeout_seconds": 30,
                }
            )
            before = fixture_hash(controller.engine)
            model = RecordedModel(budget)
            async with connect(controller.url, controller.token) as mcp:
                state = await Investigation(model, mcp, request).run()
            save(folder / "state.json", state.model_dump(mode="json"))
            save(folder / "model-diagnostics.json", model.decisions)
            after = fixture_hash(controller.engine)
            with Session(controller.engine) as session:
                effects = session.scalar(select(func.count()).select_from(ActionExecution))
            calls = [
                {"name": c.tool_name, "arguments": c.arguments, "outcome": c.outcome}
                for c in state.tool_call_history
            ]
            trial = score(
                case, "stage9e-gptoss", "real", prediction(state), state.latency_ms, calls, effects
            )
            report.update(
                run_status=state.run_status,
                latency_ms=state.latency_ms,
                fixture_unchanged=before == after,
                action_execution_records=effects,
                trial=trial.model_dump(mode="json"),
            )
            report["passed"] = bool(
                state.run_status == "completed"
                and trial.task_success
                and trial.required_tool_coverage
                and before == after
                and effects == 0
                and len(calls) <= 8
                and all(c["name"] in READ_TOOLS for c in calls)
                and len(budget.requests) <= 14
                and not budget.stopped
            )
    except Exception as exc:
        # Never print/persist DSNs, prompts, provider messages or exception text.
        report["runner_error_type"] = type(exc).__name__
    finally:
        report.update(
            provider_requests=len(budget.requests),
            accounted_usd=budget.accounted_usd,
            cost_complete=all(r["cost_complete"] for r in budget.requests),
            finished_at=datetime.now(UTC).isoformat(),
        )
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
        / "evaluations/reports/stage9e"
        / (datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:6])
    )
    folder.mkdir(parents=True, exist_ok=False)
    try:
        result = asyncio.run(execute(folder))
    except Exception:
        print(json.dumps({"error": "LIVE_SETUP_FAILED", "report": str(folder.relative_to(ROOT))}))
        return 2
    print(str(folder.relative_to(ROOT)))
    return 0 if result["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
