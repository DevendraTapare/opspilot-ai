"""Real PostgreSQL + TCP MCP benchmark; unavailable real models stay excluded."""

import argparse
import asyncio
import hashlib
import json
import os
import platform
import sys
import time
from collections import Counter
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from evaluations.runners import subjects
from evaluations.runners.contracts import Prediction
from evaluations.runners.dataset import DATA, ROOT, load
from evaluations.runners.environment import Environment
from evaluations.runners.metrics import gates, matched_comparison, score, summarize
from opspilot.agent.fixtures import FixtureDecisionModel
from opspilot.agent.mcp import connect
from opspilot.agent.providers import HTTPDecisionModel, ModelFailure
from opspilot.gateway.contracts import READ_TOOLS
from opspilot.logging import configure_logging
from opspilot.models import ActionExecution
from opspilot.observability import attributes, configure_tracing, span


class RecordedMCP:
    def __init__(self, actual):
        self.actual, self.calls = actual, []

    async def call(self, name, args):
        start = time.monotonic()
        row = {
            "name": name if name in READ_TOOLS else "rejected_action_or_unknown",
            "outcome": "UNAVAILABLE",
        }
        self.calls.append(row)
        try:
            if name not in READ_TOOLS:
                raise ValueError("read-only evaluation boundary")
            value = await self.actual.call(name, args)
            row["outcome"] = "OK" if value["ok"] else value["error"]["code"]
            return value
        finally:
            row["latency_ms"] = round((time.monotonic() - start) * 1000, 3)


def provider_ready():
    if not all(os.environ.get("OPSPILOT_AGENT_" + s) for s in ["PROVIDER", "MODEL", "BASE_URL"]):
        return False
    try:
        HTTPDecisionModel.from_environment()
    except ValueError:
        return False
    return True


def source_fingerprint():
    digest = hashlib.sha256()
    for folder in [ROOT / "opspilot", ROOT / "evaluations/runners", ROOT / "tests"]:
        for p in sorted(folder.rglob("*.py")):
            digest.update(str(p.relative_to(ROOT)).replace("\\", "/").encode())
            digest.update(p.read_bytes())
    digest.update((ROOT / "uv.lock").read_bytes())
    digest.update((DATA / "manifest.json").read_bytes())
    return digest.hexdigest()


async def run(args, output):
    cases = load(args.split)
    if args.limit:
        cases = cases[: args.limit]
    ready = provider_ready()
    trials = []
    excluded = Counter()
    start = datetime.now(UTC).isoformat()
    # Freeze source and dataset before any selected case, including held-out, executes.
    frozen = source_fingerprint()
    plan = {
        "source_lock_dataset_sha256": frozen,
        "split": args.split,
        "case_ids": [c.id for c in cases],
        "arms": args.arms,
        "limits": {"tools": 8, "model_calls": 14, "seconds": 180, "per_call_seconds": 15},
        "created_at": start,
        "fixture_smoke": args.fixture_smoke,
    }
    output.with_suffix(".plan.json").write_text(json.dumps(plan, indent=2), encoding="utf-8")
    if not os.environ.get("OPSPILOT_TEST_DATABASE_URL"):
        raise ValueError("dedicated test database configuration required")
    with Environment(os.environ["OPSPILOT_TEST_DATABASE_URL"]).start() as environment:
        for case in cases:
            for arm in args.arms:
                mode = "rules" if arm == "baseline" else "fixture" if args.fixture_smoke else "real"
                if arm != "baseline" and not args.fixture_smoke and not ready:
                    prediction = Prediction(status="excluded", error_code="REAL_MODEL_UNAVAILABLE")
                    excluded["REAL_MODEL_UNAVAILABLE"] += 1
                    trials.append(score(case, arm, mode, prediction, 0, []))
                    continue
                public = environment.prepare(case)
                calls = []
                trace_id = None
                started = time.monotonic()
                try:
                    with span("evaluation.subject") as current:
                        trace_id = f"{current.get_span_context().trace_id:032x}"
                        attributes(
                            **{
                                "opspilot.incident_id": public.incident_id,
                                "opspilot.service": public.service_name,
                                "opspilot.mode": "baseline" if mode == "rules" else mode,
                            }
                        )
                        async with asyncio.timeout(public.max_seconds):
                            async with connect(environment.url, environment.token) as actual:
                                mcp = RecordedMCP(actual)
                                calls = mcp.calls
                                if arm == "baseline":
                                    prediction = await subjects.baseline(public, mcp)
                                else:
                                    model = (
                                        FixtureDecisionModel()
                                        if args.fixture_smoke
                                        else HTTPDecisionModel.from_environment()
                                    )
                                    prediction = await (
                                        subjects.structured(public, mcp, model)
                                        if arm == "structured"
                                        else subjects.llm_tools(public, mcp, model)
                                    )
                except TimeoutError:
                    prediction = Prediction(status="timeout", error_code="DEADLINE_EXCEEDED")
                except ModelFailure as exc:
                    prediction = Prediction(status="failed", error_code=exc.code)
                except Exception:
                    prediction = Prediction(status="failed", error_code="SUBJECT_ERROR")
                elapsed = round((time.monotonic() - started) * 1000, 3)
                with Session(environment.engine) as session:
                    effects = session.scalar(select(func.count()).select_from(ActionExecution))
                cost = None
                if arm == "baseline" or args.fixture_smoke:
                    cost = 0.0
                    if arm == "baseline":
                        prediction.input_tokens = prediction.output_tokens = 0
                elif prediction.input_tokens is not None and prediction.output_tokens is not None:
                    if args.input_price is not None and args.output_price is not None:
                        cost = (
                            prediction.input_tokens * args.input_price
                            + prediction.output_tokens * args.output_price
                        ) / 1_000_000
                trial = score(case, arm, mode, prediction, elapsed, calls, effects, cost)
                trial.trace_id = trace_id
                trials.append(trial)
                # Only safe counters/opaque IDs, no expected answer or diagnostic bodies.
                print(
                    json.dumps(
                        {
                            "event": "evaluation_trial",
                            "case_id": case.id,
                            "arm": arm,
                            "mode": mode,
                            "status": prediction.status,
                            "elapsed_ms": elapsed,
                        }
                    ),
                    flush=True,
                )
    metrics = {arm: summarize([t for t in trials if t.arm == arm]) for arm in args.arms}
    comparisons = [
        matched_comparison(trials, a, b)
        for a, b in [("baseline", "llm"), ("baseline", "structured"), ("llm", "structured")]
        if a in args.arms and b in args.arms
    ]
    report = {
        "schema_version": "1.0.0",
        "dataset_version": "1.0.0",
        "split": args.split,
        "started_at": start,
        "finished_at": datetime.now(UTC).isoformat(),
        "frozen_plan": plan,
        "environment": {
            "python": platform.python_version(),
            "platform": sys.platform,
            "packages": {
                p: version(p)
                for p in ["langgraph", "mcp", "opentelemetry-sdk", "sqlalchemy", "psycopg"]
            },
            "database": "dedicated Docker PostgreSQL; isolated generated schema; removed after run",
            "transport": (
                "real MCP discovery/tools-call over local TCP; bounded 10s gateway profile"
            ),
        },
        "model": {
            "available": ready,
            "provider": os.environ.get("OPSPILOT_AGENT_PROVIDER") if ready else None,
            "configured_model_sha256": hashlib.sha256(
                os.environ.get("OPSPILOT_AGENT_MODEL", "").encode()
            ).hexdigest()
            if ready
            else None,
            "fixture_smoke": args.fixture_smoke,
            "input_price_per_million": args.input_price,
            "output_price_per_million": args.output_price,
        },
        "metrics": metrics,
        "excluded_reasons": dict(excluded),
        "comparisons": comparisons,
        "gates": {
            arm: gates(m, real=arm != "baseline" and ready and not args.fixture_smoke)
            for arm, m in metrics.items()
        },
        "trials": [t.model_dump(mode="json") for t in trials],
        "release_ready": False,
        "release_note": (
            "Diagnostic report alone cannot pass approval/recovery gates. "
            "Combine with fresh operational evidence; UNAVAILABLE gates fail "
            "closed."
        ),
    }
    output.write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
    print(
        json.dumps(
            {
                "report": str(output.relative_to(ROOT)),
                "attempted": sum(m["attempted"] for m in metrics.values()),
                "excluded": sum(m["excluded"] for m in metrics.values()),
                "release_ready": False,
            }
        )
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--split", choices=["calibration", "development", "held_out"], required=True
    )
    parser.add_argument(
        "--arms",
        nargs="+",
        choices=["baseline", "llm", "structured"],
        default=["baseline", "llm", "structured"],
    )
    parser.add_argument("--limit", type=int)
    parser.add_argument(
        "--fixture-smoke",
        action="store_true",
        help="Explicit structured workflow plumbing only; never a real-model comparison",
    )
    parser.add_argument(
        "--input-price",
        type=float,
        help="Trusted USD per million input tokens; no automatic pricing assumptions",
    )
    parser.add_argument("--output-price", type=float)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    output = Path(args.output).resolve()
    if (
        not output.is_relative_to(ROOT / "evaluations/reports")
        or output.suffix != ".json"
        or output.exists()
        or output.with_suffix(".plan.json").exists()
    ):
        parser.error("choose a new JSON report inside evaluations/reports")
    if (
        len(args.arms) != len(set(args.arms))
        or args.limit is not None
        and not 1 <= args.limit <= 120
    ):
        parser.error("unique arms and limit 1..120 required")
    if args.fixture_smoke and (args.split == "held_out" or args.arms != ["structured"]):
        parser.error("fixture smoke uses --arms structured and never held-out")
    if any(v is not None and (not 0 <= v <= 10000) for v in [args.input_price, args.output_price]):
        parser.error("prices must be finite nonnegative USD per million")
    output.parent.mkdir(parents=True, exist_ok=True)
    configure_logging()
    configure_tracing(output.with_suffix(".traces.jsonl"))
    try:
        asyncio.run(run(args, output))
    except Exception:
        print(
            json.dumps(
                {
                    "status": "RUNNER_UNAVAILABLE",
                    "message": (
                        "No benchmark result was fabricated; inspect local services/configuration."
                    ),
                }
            ),
            file=sys.stderr,
        )
        raise SystemExit(2) from None


if __name__ == "__main__":
    main()
