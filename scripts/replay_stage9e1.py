"""Offline recorded-control-flow replay. No keys, inference, MCP server or action access.

Assessment bodies 1-4 were not retained: explicit placeholders reproduce only their
known `investigate` transitions. This is not a faithful replay of missing LLM prose,
new model reasoning, or a measurement of post-change provider tokens/accuracy.
"""

import argparse
import asyncio
import hashlib
import importlib.util
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import httpx2

from opspilot.agent.budgets import estimate_input_tokens
from opspilot.agent.evidence import arguments_for
from opspilot.agent.providers import HTTPDecisionModel, ModelFailure
from opspilot.agent.schemas import InvestigationState, Observation, ToolCall
from opspilot.agent.workflow import Investigation

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "evaluations/reports/stage9e/20261119T045601Z-b7d83b"


def digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def historical_rows():
    rows = json.loads((SOURCE / "requests.json").read_text())
    state = InvestigationState.model_validate_json((SOURCE / "state.json").read_text())
    decisions = json.loads((SOURCE / "model-diagnostics.json").read_text())
    selections = iter(state.tool_call_history[1:])
    verifier = Investigation(None, None, state.request)
    result = []
    for row, decision in zip(rows, decisions, strict=True):
        tool = next(selections, None) if row["phase"].endswith(":investigation_planning") else None
        # Original reservation was (UTF8 JSON bytes + 512) * input price + 1600 * output price.
        byte_equivalent = round((row["reserved_usd"] * 1_000_000 - 1600 * 0.30) / 0.075)
        result.append(
            {
                "number": row["number"],
                "stage": decision["stage"],
                "tool_selected": tool.tool_name if tool else None,
                "estimated_input_byte_equivalents": byte_equivalent,
                "estimated_input_tokens": byte_equivalent,
                "estimate_note": ("Conservative UTF8 byte-equivalent reserve, not tokenizer usage"),
                "reported_input_tokens": row.get("input_tokens"),
                "reported_output_tokens": row.get("output_tokens"),
                "http_status": row["http_status"],
                "provider_latency_ms": row["latency_ms"],
                "decision": (
                    "select_diagnostic_tool"
                    if tool
                    else "investigate"
                    if decision["stage"] == "evidence_assessment"
                    else "triage"
                    if decision["stage"] == "triage"
                    else "none: provider rejection"
                ),
                "received_evidence_ids": decision["received_evidence_ids"],
                "corroboration_inputs_available": verifier._corroborated(
                    state, decision["received_evidence_ids"]
                ),
                "new_evidence_after_request": tool.evidence_ref if tool else None,
                "existing_evidence_repeated": row["number"] > 1,
                "semantic_repetition": "same metric sample as e002"
                if tool and tool.evidence_ref == "e006"
                else None,
                "stopping_assessment": (
                    "Abstention available; earlier hypothesis bodies missing, eligibility unknown."
                    if row["number"] < 11
                    else "Abstention available; e002 alone fails final corroboration."
                ),
            }
        )
    return result


def module_from_snapshot(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def fixture_replay(workflow_class, model_class, saved, historical):
    captures, reads = [], []
    plans, assessments = 0, 0
    model_records = [r for r in saved.tool_call_history if r.model_call]

    def response(request):
        nonlocal plans, assessments
        body = json.loads(request.content)
        payload = json.loads(body["messages"][-1]["content"])
        stage = payload["stage"]
        original = historical[len(captures)]
        assert stage == original["stage"], "Recorded control flow diverged"
        context = payload["untrusted_investigation_context"]
        captures.append(
            {
                "number": len(captures) + 1,
                "stage": stage,
                "serialized_utf8_bytes": len(request.content),
                "estimated_input_tokens": estimate_input_tokens(body),
                "estimate_kind": "UTF8 byte-equivalents plus 512, not tokenizer usage",
                "evidence_hashes": {o["id"]: digest(o) for o in context["observations"]},
                "schema_hash": digest(body.get("response_format") or body.get("tools")),
                "actual_provider_tokens": None,
            }
        )
        if original["http_status"] == 413:
            return httpx2.Response(
                413, json={"error": {"code": "rate_limit_exceeded", "type": "tokens"}}
            )
        if stage == "triage":
            value = saved.triage.model_dump(mode="json")
        elif stage == "investigation_planning":
            call = model_records[plans].model_call
            plans += 1
            return httpx2.Response(
                200,
                json={
                    "choices": [
                        {
                            "finish_reason": "tool_calls",
                            "message": {
                                "tool_calls": [
                                    {
                                        "id": call.id,
                                        "type": "function",
                                        "function": {
                                            "name": call.name,
                                            "arguments": call.arguments.model_dump_json(),
                                        },
                                    }
                                ]
                            },
                        }
                    ]
                },
            )
        else:
            assessments += 1
            if assessments == 5:
                value = saved.assessment.model_dump(mode="json")
            else:
                value = {
                    "hypotheses": [
                        {
                            "id": f"h{i}",
                            "description": "Replay placeholder; original body unavailable.",
                            "supporting_evidence": ["e002"],
                            "contradicting_evidence": [],
                        }
                        for i in [1, 2]
                    ],
                    "decision": "investigate",
                    "justification": "Recorded investigate transition; missing prose unavailable.",
                    "confidence": 0,
                    "uncertainty": ["Original assessment payload was not retained."],
                }
        return httpx2.Response(
            200,
            json={
                "choices": [{"finish_reason": "stop", "message": {"content": json.dumps(value)}}]
            },
        )

    class RestoredEvidence(workflow_class):
        async def _read(self, state, step):
            # Restore already projected evidence, not invented raw gateway envelopes.
            record = saved.tool_call_history[len(reads)]
            assert record.arguments == arguments_for(
                step, str(state.incident_id), self.allowed_services
            )
            observation = next(o for o in saved.observations if o.id == record.evidence_ref)
            if state.proposed_model_call:
                assert state.proposed_model_call == record.model_call
            reads.append(record.model_dump(mode="json"))
            state.tool_call_history.append(ToolCall.model_validate(record.model_dump()))
            state.observations.append(Observation.model_validate(observation.model_dump()))
            state.evidence_references.append(observation.id)
            return True

    model = model_class(
        "groq",
        "openai/gpt-oss-20b",
        "https://api.groq.com/openai/v1",
        "offline-synthetic",
        request_interval_seconds=0,
        transport=httpx2.MockTransport(response),
    )
    model.mode = "fixture"
    result = asyncio.run(RestoredEvidence(model, None, saved.request).run())
    return {
        "mode": "offline_recorded_control_flow",
        "model_requests": len(captures),
        "tool_reads_restored": len(reads),
        "actual_mcp_calls": 0,
        "actual_provider_requests": 0,
        "estimated_input_tokens": sum(r["estimated_input_tokens"] for r in captures),
        "serialized_prompt_bytes": sum(r["serialized_utf8_bytes"] for r in captures),
        "duplicate_tool_calls": len(reads)
        - len({digest([r["tool_name"], r["arguments"]]) for r in reads}),
        "evidence_hashes": {o.id: digest(o.model_dump(mode="json")) for o in result.observations},
        "run_status": result.run_status,
        "errors": [e.model_dump() for e in result.errors],
        "finalized": result.candidate_root_cause is not None,
        "remediation": result.proposed_remediation is not None,
        "explicit_incomplete": result.run_status == "budget_exhausted",
        "explicit_model_abstention": result.run_status == "abstained",
        "validation_failures": sum(e.code == "UNSUPPORTED_DECISION" for e in result.errors),
        "requests": captures,
    }


def execute(baseline):
    manifest = json.loads((baseline.parent / "protected-hashes.json").read_text())
    historical_hashes = {
        p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in SOURCE.glob("*.json")
    }
    if any(manifest.get(k) != v for k, v in historical_hashes.items()):
        raise ValueError("Historical source trace changed since baseline capture")
    saved = InvestigationState.model_validate_json((SOURCE / "state.json").read_text())
    historical = historical_rows()
    legacy_provider = module_from_snapshot("stage9e1_legacy_provider", baseline / "providers.py")
    legacy_workflow = module_from_snapshot("stage9e1_legacy_workflow", baseline / "workflow.py")
    # Snapshot and current exception types must share identity during the local replay.
    legacy_provider.ModelFailure = ModelFailure
    before = fixture_replay(
        legacy_workflow.Investigation, legacy_provider.HTTPDecisionModel, saved, historical
    )
    after = fixture_replay(Investigation, HTTPDecisionModel, saved, historical)
    matched = min(len(before["requests"]), len(after["requests"]))
    return {
        "version": "9e1-offline-1",
        "source_trace": SOURCE.relative_to(ROOT).as_posix(),
        "historical_source_unchanged": True,
        "historical_source_sha256": historical_hashes,
        "baseline_source_hashes": {
            p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in baseline.glob("*.py")
        },
        "limitations": [
            "Assessment bodies 1-4 unavailable; placeholders reproduce transitions only",
            "No post-change real-provider tokens, latency or diagnosis accuracy measured",
            "Validated projected evidence restored; no new MCP protocol exercised by replay",
            "UTF8 byte-equivalent estimates are admission accounting, not exact tokenization",
        ],
        "historical_requests": historical,
        "before": before,
        "after": after,
        "matched_prefix": {
            "requests": matched,
            "before_bytes": sum(r["serialized_utf8_bytes"] for r in before["requests"][:matched]),
            "after_bytes": sum(r["serialized_utf8_bytes"] for r in after["requests"][:matched]),
            "evidence_identical": all(
                a["evidence_hashes"] == b["evidence_hashes"]
                for a, b in zip(
                    before["requests"][:matched], after["requests"][:matched], strict=True
                )
            ),
        },
        "historical_evidence_retained": all(
            after["evidence_hashes"][key] == before["evidence_hashes"][key]
            for key in after["evidence_hashes"]
        ),
        "default_model_changed": False,
        "provider_requests": 0,
        "spend_usd": 0,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-dir", type=Path, required=True)
    args = parser.parse_args()
    baseline = args.baseline_dir.resolve()
    if not baseline.is_relative_to(ROOT / "artifacts/stage9e1"):
        parser.error("Only this stage's preserved local baseline snapshot may be loaded")
    report = execute(baseline)
    folder = (
        ROOT
        / "evaluations/reports/stage9e1"
        / (datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:6])
    )
    folder.mkdir(parents=True, exist_ok=False)
    (folder / "replay.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "report": folder.relative_to(ROOT).as_posix(),
                "before_requests": report["before"]["model_requests"],
                "after_requests": report["after"]["model_requests"],
                "matched_prefix": report["matched_prefix"],
            }
        )
    )


if __name__ == "__main__":
    main()
