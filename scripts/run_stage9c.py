"""Trusted isolated fixture setup and grading, outside the read-only comparison client."""

import argparse
import asyncio
import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from evaluations.runners.benchmark import source_fingerprint
from evaluations.runners.dataset import load
from evaluations.runners.environment import Environment
from evaluations.runners.metrics import gates, score, summarize
from opspilot.agent.mcp import connect
from opspilot.agent.schemas import RunRequest
from opspilot.agent.workflow import Investigation
from opspilot.models import ActionExecution, Base
from scripts.compare_groq_models import (
    MODELS,
    ROOT,
    Budget,
    ComparisonModel,
    collect_packet,
    digest,
    load_key,
    probe,
    save,
    settings,
)
from scripts.review_stage9 import environment
from scripts.verify_stage9b import prediction

CASES = ["op5-001", "op5-031", "op5-091"]


def fixture_hash(engine):
    names = {
        "services",
        "faults",
        "incidents",
        "incident_events",
        "deployment_events",
        "metric_summaries",
        "simulation_logs",
    }
    values = {}
    with engine.connect() as connection:
        for name in sorted(names):
            table = Base.metadata.tables[name]
            rows = [dict(row) for row in connection.execute(select(table)).mappings()]
            values[name] = sorted(json.dumps(r, sort_keys=True, default=str) for r in rows)
    return digest(values)


async def run(folder, prior=None):
    report = {
        "mode": "real",
        "started_at": datetime.now(UTC).isoformat(),
        "models": list(MODELS),
        "case_ids": CASES,
        "probes": [],
        "investigations": [],
        "source_fingerprint": source_fingerprint(),
        "limits": {
            "provider_requests": 30,
            "usd": 0.50,
            "output_tokens": 1600,
            "tools": 8,
            "model_calls": 14,
            "investigation_seconds": 180,
            "call_seconds": 15,
        },
        "settings": {m: settings(m) for m in MODELS},
        "automatic_retries": False,
        "billing": "List-price estimates; requested Free Plan, account tier/invoice unverified.",
        "fixture_policy": (
            "Fresh UUID schema per case; trusted fixture setup precedes reads. "
            "No existing schema reset. MCP audit writes remain enabled."
        ),
        "held_out": False,
    }
    save(folder / "plan.json", report)
    protected = [
        *ROOT.glob("docs/STAGE_9*.md"),
        *ROOT.glob("evaluations/reports/*.json"),
        *ROOT.glob("evaluations/datasets/v1/*"),
        ROOT / "uv.lock",
        ROOT / "pyproject.toml",
    ]
    save(
        folder / "protected-hashes.json",
        {
            p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in protected
            if p.is_file()
        },
    )
    budget = None
    trials = {model: [] for model in MODELS}
    try:
        budget = Budget(folder, load_key())
        if prior:
            previous = json.loads(prior.read_text(encoding="utf-8"))
            requests = json.loads((prior.parent / "requests.json").read_text(encoding="utf-8"))
            if (
                previous.get("error_type") != "DecodingError"
                or len(requests) != 1
                or requests[0].get("model") is not None
                or requests[0].get("phase") != "availability"
            ):
                raise ValueError("Only the pre-model compression failure can be continued")
            budget.requests = requests
            report["continuation_of"] = prior.relative_to(ROOT).as_posix()
            report["carried_provider_requests"] = len(requests)
        availability = await budget.call(None, "availability")
        available = {m["id"]: m for m in availability["data"]}
        report["availability"] = {
            m: {
                k: available.get(m, {}).get(k)
                for k in ["id", "active", "context_window", "max_completion_tokens"]
            }
            for m in MODELS
        }
        save(folder / "report.json", report)
        cases = {c.id: c for c in load("calibration")}
        raw_url = environment()["OPSPILOT_TEST_DATABASE_URL"]
        for case_index, identity in enumerate(CASES):
            if budget.stopped:
                break
            if case_index and not report.get("eligible_models"):
                break
            with Environment(raw_url).start() as controller:
                public = controller.prepare(cases[identity])
                before = fixture_hash(controller.engine)
                async with connect(controller.url, controller.token) as mcp:
                    if case_index == 0:
                        packet = await collect_packet(mcp, public)
                        save(
                            folder / "shared-probe-packet.json",
                            {
                                "request": public.model_dump(mode="json"),
                                "observations": [
                                    o.model_dump(mode="json") for o in packet.observations
                                ],
                            },
                        )
                        results = {m: {} for m in MODELS}
                        for phase in ["A", "B", "C", "D"]:
                            for model in MODELS:
                                if budget.stopped:
                                    result = {
                                        "model": model,
                                        "probe": phase,
                                        "passed": False,
                                        "not_run": budget.stopped,
                                    }
                                elif model not in available or not available[model].get(
                                    "active", True
                                ):
                                    result = {
                                        "model": model,
                                        "probe": phase,
                                        "passed": False,
                                        "not_run": "MODEL_NOT_ACCESSIBLE",
                                    }
                                elif phase != "A" and not results[model]["A"].get("passed"):
                                    result = {
                                        "model": model,
                                        "probe": phase,
                                        "passed": False,
                                        "not_run": "BASIC_RESPONSE_FAILED",
                                    }
                                else:
                                    result = await probe(
                                        budget, model, phase, mcp, packet, results[model].get("B")
                                    )
                                results[model][phase] = result
                                # Only projected evidence and sanitized messages are retained.
                                report["probes"].append(result)
                                save(folder / "report.json", report)
                                print(
                                    json.dumps(
                                        {
                                            "model": model,
                                            "probe": phase,
                                            "passed": result["passed"],
                                            "error": result.get("error_code")
                                            or result.get("not_run"),
                                        }
                                    ),
                                    flush=True,
                                )
                        report["eligible_models"] = [
                            m
                            for m in MODELS
                            if all(
                                results[m][phase].get("passed") for phase in ["A", "B", "C", "D"]
                            )
                        ]
                    order = list(MODELS if case_index % 2 == 0 else reversed(MODELS))
                    for model in order:
                        if model not in report.get("eligible_models", []) or budget.stopped:
                            continue
                        subject = ComparisonModel(model, budget)
                        result = await Investigation(
                            subject, mcp, RunRequest.model_validate(public.model_dump())
                        ).run()
                        with Session(controller.engine) as session:
                            effects = session.scalar(
                                select(func.count()).select_from(ActionExecution)
                            )
                        prefix = identity + "-" + ("qwen" if model == MODELS[0] else "gptoss")
                        save(folder / (prefix + ".json"), result.model_dump(mode="json"))
                        save(folder / (prefix + "-decisions.json"), subject.decisions)
                        usage = result.usage
                        from scripts.compare_groq_models import PRICES

                        price = PRICES[model]
                        cost = (
                            (usage.input_tokens * price[0] + usage.output_tokens * price[1])
                            / 1_000_000
                            if usage.usage_complete
                            else None
                        )
                        trial = score(
                            cases[identity],
                            model,
                            "real",
                            prediction(result),
                            result.latency_ms,
                            [
                                {
                                    "name": t.tool_name,
                                    "arguments": t.arguments,
                                    "outcome": t.outcome,
                                }
                                for t in result.tool_call_history
                            ],
                            effects,
                            cost,
                        )
                        trials[model].append(trial)
                        report["investigations"].append(
                            {
                                "case_id": identity,
                                "model": model,
                                "public_start_sha256": digest(public.model_dump(mode="json")),
                                "fixture_start_sha256": before,
                                "status": result.run_status,
                                "trial": trial.model_dump(mode="json"),
                                "safe_errors": [e.code for e in result.errors],
                            }
                        )
                        save(folder / "report.json", report)
                        print(
                            json.dumps(
                                {
                                    "case": identity,
                                    "model": model,
                                    "status": result.run_status,
                                    "correct_root": trial.correct_root,
                                }
                            ),
                            flush=True,
                        )
                after = fixture_hash(controller.engine)
                report.setdefault("fixture_integrity", []).append(
                    {
                        "case_id": identity,
                        "before": before,
                        "after": after,
                        "unchanged": before == after,
                    }
                )
                if before != after:
                    budget.stopped = "FIXTURE_MUTATION_DETECTED"
                    break
                if not report.get("eligible_models"):
                    break
        report["metrics"] = {m: summarize(trials[m]) for m in MODELS}
        report["original_gates"] = {m: gates(report["metrics"][m], real=True) for m in MODELS}
    except Exception as exc:
        report["error_type"] = type(exc).__name__
    finally:
        if budget:
            report.update(
                request_count=len(budget.requests),
                stop_reason=budget.stopped,
                accounted_cost_usd=budget.accounted_usd,
                known_estimated_cost_usd=sum(r.get("estimated_usd", 0) for r in budget.requests),
                missing_usage_requests=sum(not r["cost_complete"] for r in budget.requests),
            )
        report["finished_at"] = datetime.now(UTC).isoformat()
        save(folder / "report.json", report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prior-failed-report", type=Path)
    args = parser.parse_args()
    if args.prior_failed_report:
        args.prior_failed_report = args.prior_failed_report.resolve()
        if not args.prior_failed_report.is_relative_to(ROOT / "evaluations/reports/stage9c"):
            parser.error("Continuation must reference a retained Stage 9C report")
    os.environ["LANGSMITH_TRACING"] = "false"
    os.environ["LANGCHAIN_TRACING_V2"] = "false"
    folder = (
        ROOT
        / "evaluations/reports/stage9c"
        / (datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:6])
    )
    folder.mkdir(parents=True, exist_ok=False)
    report = asyncio.run(run(folder, args.prior_failed_report))
    print(
        json.dumps(
            {
                "report": (folder / "report.json").relative_to(ROOT).as_posix(),
                "requests": report.get("request_count", 0),
                "eligible_models": report.get("eligible_models", []),
                "error_type": report.get("error_type"),
            }
        )
    )
    return 0 if len(report.get("investigations", [])) == 6 else 2


if __name__ == "__main__":
    raise SystemExit(main())
