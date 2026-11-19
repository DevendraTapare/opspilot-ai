"""Small genuine Groq investigations. New PG schemas, original rubric, no action authority."""

import argparse
import asyncio
import hashlib
import json
import os
import time
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from dotenv import dotenv_values
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from evaluations.runners.benchmark import source_fingerprint
from evaluations.runners.contracts import Prediction
from evaluations.runners.dataset import load
from evaluations.runners.environment import Environment
from evaluations.runners.metrics import gates, score, summarize
from opspilot.agent.mcp import connect
from opspilot.agent.providers import HTTPDecisionModel, ModelFailure
from opspilot.agent.schemas import RunRequest
from opspilot.agent.workflow import Investigation
from opspilot.models import ActionExecution
from scripts.review_stage9 import environment
from scripts.verify_groq import BASE_URL, CASE_IDS, MODEL, ROOT, MeteredTransport, save


class BoundedTransport(MeteredTransport):
    def __init__(self, requests, budget):
        super().__init__(requests)
        self.budget = budget

    async def handle_async_request(self, request):
        if len(self.requests) >= self.budget:
            raise ModelFailure("HTTP_REQUEST_BUDGET_EXHAUSTED")
        body = json.loads(request.content)
        index = len(self.requests)
        try:
            return await super().handle_async_request(request)
        finally:
            if len(self.requests) > index:
                bindings = []
                for message in body["messages"]:
                    if message["role"] == "tool":
                        result = json.loads(message["content"])
                        observation = result.get("observation", {})
                        bindings.append(
                            {
                                "tool_call_id": message["tool_call_id"],
                                "evidence_ref": observation.get("id"),
                                "request_id": observation.get("request_id"),
                                "ok": result["ok"],
                            }
                        )
                self.requests[index].update(
                    roles=[m["role"] for m in body["messages"]],
                    tool_result_bindings=bindings,
                    declares_tools="tools" in body,
                    declares_structured_output="response_format" in body,
                    reasoning_effort=body.get("reasoning_effort"),
                    reasoning_format=body.get("reasoning_format"),
                    max_output_tokens=body["max_tokens"],
                )


class RecordedModel:
    mode, provider, model = "real", "groq", MODEL

    def __init__(self, key, budget):
        self.decisions, self.requests = [], []
        self.budget = budget
        self.adapter = HTTPDecisionModel("groq", MODEL, BASE_URL, key)

    async def wait_for_capacity(self):
        await self.adapter.wait_for_capacity()

    async def generate(self, stage, context, schema):
        row = {
            "stage": stage,
            "received_observation_refs": [o["id"] for o in context.get("observations", [])],
            "context_sha256": hashlib.sha256(
                json.dumps(context, sort_keys=True).encode()
            ).hexdigest(),
        }
        self.decisions.append(row)
        self.adapter.transport = BoundedTransport(self.requests, self.budget)
        started = time.monotonic()
        try:
            reply = await self.adapter.generate(stage, context, schema)
            row.update(
                output=reply.value.model_dump(mode="json"),
                input_tokens=reply.input_tokens,
                output_tokens=reply.output_tokens,
                tool_call=reply.tool_call.model_dump(mode="json") if reply.tool_call else None,
            )
            return reply
        except ModelFailure as exc:
            row["error_code"] = exc.code
            raise
        finally:
            row["elapsed_ms"] = round((time.monotonic() - started) * 1000, 3)


def prediction(result):
    """Original structured-arm mapping, unchanged; controller-only scoring."""
    cause, proposal = result.candidate_root_cause, result.proposed_remediation
    mechanism = None
    if cause and proposal:
        action, text = proposal.action, cause.explanation.lower()
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


async def execute(args, folder, key):
    selected = [CASE_IDS[0]] * 3 if args.phase == "initial" else CASE_IDS
    model = RecordedModel(key, len(selected) * 14)
    report = {
        "phase": args.phase,
        "mode": "real",
        "provider": "Groq",
        "model": MODEL,
        "started_at": datetime.now(UTC).isoformat(),
        "runs": [],
        "decisions": model.decisions,
        "requests": model.requests,
        "automatic_retry": False,
        "fixture_fallback": False,
        "source_fingerprint": source_fingerprint(),
        "limits": {
            "tools": 8,
            "model_calls": 14,
            "seconds": 180,
            "per_call_seconds": 15,
            "minimum_request_interval_seconds": 12,
            "phase_http_requests": model.budget,
        },
        "billing": (
            "Free Plan requested; account tier/invoice unverified. "
            "Estimates are list-price equivalents, not charges."
        ),
        "price_usd_per_million_tokens": {"input": 0.80, "output": 4.00},
        "population": (
            "Calibration only; repeated initial attempts share one recipe, "
            "not independent scenarios."
        ),
    }
    save(folder / "plan.json", {**report, "case_ids": selected})
    trials = []
    try:
        cases = {c.id: c for c in load("calibration")}
        with Environment(environment()["OPSPILOT_TEST_DATABASE_URL"]).start() as controller:
            for index, identity in enumerate(selected, 1):
                case = cases[identity]
                public = controller.prepare(case)
                first = len(model.decisions)
                async with connect(controller.url, controller.token) as mcp:
                    result = await Investigation(
                        model, mcp, RunRequest.model_validate(public.model_dump())
                    ).run()
                save(folder / f"attempt-{index}.json", result.model_dump(mode="json"))
                with Session(controller.engine) as session:
                    effects = session.scalar(select(func.count()).select_from(ActionExecution))
                cost = (
                    (result.usage.input_tokens * 0.80 + result.usage.output_tokens * 4) / 1_000_000
                    if result.usage.usage_complete
                    else None
                )
                trial = score(
                    case,
                    "structured-investigation",
                    "real",
                    prediction(result),
                    result.latency_ms,
                    [
                        {"name": t.tool_name, "arguments": t.arguments, "outcome": t.outcome}
                        for t in result.tool_call_history
                    ],
                    effects,
                    cost,
                )
                trials.append(trial)
                expected_action = {
                    "worker_capacity": "restart_simulated_worker",
                    "configuration": "rollback_simulated_configuration",
                    "database_pool": "reset_simulated_dependency",
                    "dependency_unavailable": "reset_simulated_dependency",
                    "processing_latency": "manual_investigation",
                }.get(case.expected_mechanism)
                proposal = result.proposed_remediation
                report["runs"].append(
                    {
                        "attempt": index,
                        "case_id": identity,
                        "run_id": str(result.run_id),
                        "incident_id": str(result.incident_id),
                        "status": result.run_status,
                        "trial": trial.model_dump(mode="json"),
                        "proposed_action_correct": bool(
                            proposal
                            and proposal.action == expected_action
                            and proposal.service_name == case.expected_service
                        )
                        if proposal
                        else None,
                        "new_evidence_consumed": any(
                            len(d["received_observation_refs"]) >= 2
                            for d in model.decisions[first:]
                        ),
                        "model_selected_reads": sum(
                            t.model_call is not None for t in result.tool_call_history
                        ),
                        "safe_errors": [e.code for e in result.errors],
                    }
                )
                save(folder / "report.json", report)
                print(
                    json.dumps(
                        {
                            "attempt": index,
                            "status": result.run_status,
                            "task_success": trial.task_success,
                        }
                    ),
                    flush=True,
                )
                if any(r["http_status"] in {401, 403, 429} for r in model.requests):
                    report["stopped_on_access_or_quota"] = True
                    break
        report["metrics"] = summarize(trials)
        report["original_gates"] = gates(report["metrics"], real=True)
        report["phase_completed"] = len(trials) == len(selected)
        diagnostic_gates = {
            "security_no_unauthorized_effect",
            "correctness",
            "task_completion",
            "unsupported",
            "latency",
            "cost",
        }
        report["five_case_gate_passed"] = (
            args.phase == "five"
            and report["phase_completed"]
            and all(
                g["status"] == "PASS"
                for g in report["original_gates"]
                if g["name"] in diagnostic_gates
            )
        )
        report["initial_gate_passed"] = (
            args.phase == "initial"
            and len(trials) == 3
            and all(
                t.task_success and t.correct_root and t.observed_side_effects == 0 for t in trials
            )
        )
    except Exception as exc:
        report["error_type"] = type(exc).__name__
        report["initial_gate_passed"] = False
    finally:
        report["finished_at"] = datetime.now(UTC).isoformat()
        save(folder / "report.json", report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=["initial", "five"], default="initial")
    parser.add_argument("--initial-report", type=Path)
    args = parser.parse_args()
    if args.phase == "five":
        if not args.initial_report or not args.initial_report.resolve().is_relative_to(
            ROOT / "artifacts/stage9b"
        ):
            parser.error("A passed Stage 9B initial report is required")
        initial = json.loads(args.initial_report.read_text())
        if not initial.get("initial_gate_passed") or initial.get("model") != MODEL:
            parser.error("All three initial real investigations must pass for this exact model")
    key = os.environ.get("GROQ_API_KEY") or dotenv_values(ROOT / ".groq.env").get("GROQ_API_KEY")
    if not key or not key.startswith("gsk_"):
        print("GROQ_KEY_MISSING: configure the ignored .groq.env locally")
        return 2
    os.environ["LANGSMITH_TRACING"] = "false"
    os.environ["LANGCHAIN_TRACING_V2"] = "false"
    folder = (
        ROOT
        / "artifacts/stage9b"
        / (args.phase + "-" + datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:6])
    )
    folder.mkdir(parents=True, exist_ok=False)
    report = asyncio.run(execute(args, folder, key))
    print(
        json.dumps(
            {
                "report": str((folder / "report.json").relative_to(ROOT)),
                "initial_gate_passed": report.get("initial_gate_passed", False),
                "requests": len(report["requests"]),
            }
        )
    )
    passed = (
        report.get("initial_gate_passed")
        if args.phase == "initial"
        else report.get("five_case_gate_passed")
    )
    return 0 if passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
