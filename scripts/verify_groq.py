"""Explicit Groq verification: real HTTP model, real MCP, isolated PG, no actions/fallback."""

import argparse
import asyncio
import hashlib
import json
import os
import re
import time
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import httpx2
from dotenv import dotenv_values
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from evaluations.runners.benchmark import source_fingerprint
from evaluations.runners.dataset import load
from evaluations.runners.environment import Environment
from opspilot.agent.mcp import connect
from opspilot.agent.providers import HTTPDecisionModel, ModelFailure
from opspilot.agent.schemas import RunRequest, Triage
from opspilot.agent.workflow import Investigation
from opspilot.models import ActionExecution
from scripts.review_stage9 import environment

ROOT = Path(__file__).resolve().parents[1]
BASE_URL = "https://api.groq.com/openai/v1"
MODEL = "qwen/qwen3.8-27b"
CASE_IDS = ["op5-001", "op5-031", "op5-061", "op5-055", "op5-091"]


def save(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False), encoding="utf-8")


class MeteredTransport(httpx2.AsyncBaseTransport):
    """Record status/quota counters only; never request headers or raw provider bodies."""

    def __init__(self, requests):
        self.actual = httpx2.AsyncHTTPTransport(retries=0)
        self.requests = requests

    async def handle_async_request(self, request):
        if str(request.url) != BASE_URL + "/chat/completions":
            raise ModelFailure("PROVIDER_ENDPOINT_REJECTED")
        body = json.loads(request.content)
        if body.get("model") != MODEL:
            raise ModelFailure("PROVIDER_MODEL_REJECTED")
        row = {"http_status": None, "model": MODEL}
        self.requests.append(row)
        response = await self.actual.handle_async_request(request)
        row["http_status"] = response.status_code
        row["quota_headers"] = {
            name: response.headers[name][:100]
            for name in [
                "retry-after",
                "x-ratelimit-limit-requests",
                "x-ratelimit-limit-tokens",
                "x-ratelimit-remaining-requests",
                "x-ratelimit-remaining-tokens",
                "x-ratelimit-reset-requests",
                "x-ratelimit-reset-tokens",
            ]
            if name in response.headers
        }
        if response.status_code != 200:
            raw = bytearray()
            async for chunk in response.aiter_bytes():
                raw.extend(chunk)
                if len(raw) > 8192:
                    break
            await response.aclose()
            try:
                error = json.loads(raw).get("error", {})
                for name in ["code", "type"]:
                    value = error.get(name)
                    if isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9_-]{1,80}", value):
                        row["error_" + name] = value
                # Whitelisted schema diagnostic keywords, not raw generations/reasoning.
                message = str(error.get("message", ""))
                row["generation_flags"] = {
                    "generation_rejected": "generate" in message.lower(),
                    "schema_mentioned": "schema" in message.lower(),
                }
                failed = error.get("failed_generation")
                if isinstance(failed, str):
                    row["failed_generation_length"] = len(failed)
                    row["failed_generation_had_thinking_tags"] = "<think>" in failed
                    row["failed_generation_shape"] = {
                        "starts_object": failed.lstrip().startswith("{"),
                        "ends_object": failed.rstrip().endswith("}"),
                        "markdown_fence": "```" in failed,
                        "json_label": failed.lstrip().startswith("json"),
                    }
                    try:
                        candidate = json.loads(failed)
                        row["failed_generation_json_type"] = type(candidate).__name__
                        if isinstance(candidate, dict) and set(candidate) <= {
                            "summary",
                            "alternatives",
                        }:
                            try:
                                Triage.model_validate(candidate)
                                row["triage_shape_valid_but_http_rejected"] = True
                            except Exception as validation:
                                if hasattr(validation, "errors"):
                                    row["validation_types"] = [
                                        e["type"] for e in validation.errors()
                                    ]
                    except ValueError:
                        row["failed_generation_json_type"] = "not_json"
                row["schema_keywords"] = [
                    s
                    for s in [
                        "minLength",
                        "maxLength",
                        "minimum",
                        "maximum",
                        "pattern",
                        "strict",
                        "tool_choice",
                        "json_schema",
                        "max_tokens",
                    ]
                    if s in message
                ]
            except (ValueError, AttributeError):
                row["error_type"] = "unparsed_provider_error"
        return response

    async def aclose(self):
        await self.actual.aclose()


class RecordedModel:
    mode, provider, model = "real", "groq-openai-compatible", MODEL

    def __init__(self, key):
        self.key = key
        self.decisions, self.requests = [], []

    async def generate(self, stage, context, schema):
        row = {
            "stage": stage,
            "received_observation_refs": [o["id"] for o in context.get("observations", [])],
            "context_sha256": hashlib.sha256(
                json.dumps(context, sort_keys=True).encode()
            ).hexdigest(),
        }
        self.decisions.append(row)
        started = time.monotonic()
        adapter = HTTPDecisionModel(
            "openai-compatible",
            MODEL,
            BASE_URL,
            self.key,
            transport=MeteredTransport(self.requests),
        )
        try:
            reply = await adapter.generate(stage, context, schema)
            row.update(
                output=reply.value.model_dump(mode="json"),
                input_tokens=reply.input_tokens,
                output_tokens=reply.output_tokens,
            )
            return reply
        except ModelFailure as exc:
            row["error_code"] = exc.code
            raise
        finally:
            row["elapsed_ms"] = round((time.monotonic() - started) * 1000, 3)


async def execute(args, folder, key):
    model = RecordedModel(key)
    report = {
        "mode": "real",
        "provider": "Groq",
        "model": MODEL,
        "phase": args.phase,
        "started_at": datetime.now(UTC).isoformat(),
        "runs": [],
        "billing": "Free Plan requested; account tier not remotely verified; no upgrade/fallback.",
        "source_lock_dataset_sha256": source_fingerprint(),
        "model_requests": model.requests,
        "decisions": model.decisions,
        "fixture_fallback": False,
        "automatic_actions": False,
    }
    save(
        folder / "plan.json",
        {
            "phase": args.phase,
            "model": MODEL,
            "case_ids": []
            if args.phase == "probe"
            else CASE_IDS[:1]
            if args.phase == "smoke"
            else CASE_IDS,
            "source_lock_dataset_sha256": report["source_lock_dataset_sha256"],
            "limits": {"tools": 8, "model_calls": 14, "seconds": 180, "per_call_seconds": 15},
        },
    )
    try:
        if args.phase == "probe":
            reply = await model.generate(
                "triage",
                {"goal": "Connection contract check. No real incident evidence supplied."},
                Triage,
            )
            report["probe"] = reply.value.model_dump(mode="json")
            report["passed"] = True
        else:
            env = environment()
            cases = {c.id: c for c in load("calibration")}
            with Environment(env["OPSPILOT_TEST_DATABASE_URL"]).start() as controller:
                for identity in CASE_IDS[:1] if args.phase == "smoke" else CASE_IDS:
                    public = controller.prepare(cases[identity])
                    decision_start = len(model.decisions)
                    async with connect(controller.url, controller.token) as mcp:
                        result = await Investigation(
                            model,
                            mcp,
                            RunRequest.model_validate(public.model_dump()),
                        ).run()
                    value = result.model_dump(mode="json")
                    save(folder / (identity + ".json"), value)
                    with Session(controller.engine) as session:
                        effects = session.scalar(select(func.count()).select_from(ActionExecution))
                    received_new_evidence = any(
                        len(d["received_observation_refs"]) >= 2
                        for d in model.decisions[decision_start:]
                    )
                    passed = (
                        result.run_status == "completed"
                        and len(result.tool_call_history) >= 2
                        and received_new_evidence
                        and effects == 0
                    )
                    report["runs"].append(
                        {
                            "case_id": identity,
                            "run_id": str(result.run_id),
                            "incident_id": str(result.incident_id),
                            "status": result.run_status,
                            "passed_integration": passed,
                            "committed_action_effects": effects,
                            "received_new_mcp_evidence": received_new_evidence,
                            "tool_names": [t.tool_name for t in result.tool_call_history],
                            "errors": [e.code for e in result.errors],
                        }
                    )
                    save(folder / "report.json", report)
                    if any(r["http_status"] in {401, 403, 429} for r in model.requests):
                        report["stopped_on_provider_limit_or_access_error"] = True
                        break
            expected_count = 1 if args.phase == "smoke" else 5
            report["passed"] = len(report["runs"]) == expected_count and all(
                r["passed_integration"] for r in report["runs"]
            )
    except ModelFailure as exc:
        report.update(passed=False, error_code=exc.code)
    except Exception as exc:
        # Do not serialize exception strings: driver messages may contain credentials.
        report.update(passed=False, error_type=type(exc).__name__)
    finally:
        report["finished_at"] = datetime.now(UTC).isoformat()
        save(folder / "report.json", report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=["probe", "smoke", "five"], default="probe")
    parser.add_argument("--smoke-report", type=Path)
    args = parser.parse_args()
    if args.phase == "five":
        if not args.smoke_report:
            parser.error("A passed real smoke report is required before five cases")
        path = args.smoke_report.resolve()
        if not path.is_relative_to(ROOT / "artifacts/stage9a"):
            parser.error("Smoke report must be inside Stage 9A artifacts")
        smoke = json.loads(path.read_text(encoding="utf-8"))
        if smoke.get("phase") != "smoke" or smoke.get("model") != MODEL or not smoke.get("passed"):
            parser.error("Smoke did not pass for this exact model")
    key = os.environ.get("GROQ_API_KEY") or dotenv_values(ROOT / ".groq.env").get("GROQ_API_KEY")
    if not key or not key.startswith("gsk_"):
        print(json.dumps({"status": "GROQ_KEY_MISSING", "message": "Configure .groq.env locally."}))
        return 2
    os.environ["LANGSMITH_TRACING"] = "false"
    os.environ["LANGCHAIN_TRACING_V2"] = "false"
    folder = (
        ROOT
        / "artifacts/stage9a"
        / ("groq-" + datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:6])
    )
    folder.mkdir(parents=True, exist_ok=False)
    report = asyncio.run(execute(args, folder, key))
    print(
        json.dumps(
            {
                "report": (folder / "report.json").relative_to(ROOT).as_posix(),
                "phase": args.phase,
                "passed": report["passed"],
                "http_requests": len(report["model_requests"]),
                "runs": report["runs"],
            }
        )
    )
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
