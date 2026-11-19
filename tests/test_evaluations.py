"""Dataset separation, honest denominators, release gates and content-free traces."""

import json
import secrets

import pytest
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from evaluations.runners.contracts import Prediction, PublicCase
from evaluations.runners.dataset import generate, load
from evaluations.runners.metrics import gates, matched_comparison, rate, score, summarize
from evaluations.runners.operations import aggregate
from evaluations.runners.release import assess
from opspilot import observability


def test_versioned_dataset_has_distinct_recipes_and_disjoint_splits():
    cases = [c for s in ["calibration", "development", "held_out"] for c in load(s)]
    assert len(cases) == 120 == len({c.id for c in cases})
    recipes = []
    for c in cases:
        value = c.model_dump(
            mode="json",
            exclude={
                "id",
                "split",
                "family",
                "seed",
                "answerable",
                "expected_service",
                "expected_mechanism",
                "expected_resolution",
                "required_tools",
                "operational_case",
            },
        )
        recipes.append(json.dumps(value, sort_keys=True))
    assert len(set(recipes)) == 120
    assert {c.model_dump_json() for c in cases} == {c.model_dump_json() for c in generate()}
    assert [len(load(s)) for s in ["calibration", "development", "held_out"]] == [20, 60, 40]


def test_public_contract_cannot_contain_private_labels():
    public = PublicCase(
        incident_id="00000000-0000-4000-8000-000000000001", service_name="checkout-service"
    )
    for key in ["faults", "expected_mechanism", "answerable", "family", "seed"]:
        with pytest.raises(ValueError):
            PublicCase.model_validate({**public.model_dump(), key: "secret"})


def test_denominators_include_abstentions_timeouts_and_exclude_unavailable():
    case = load("calibration")[0]
    calls = [{"name": "get_incident"}, {"name": "get_service_metrics"}]
    trials = [
        score(case, "baseline", "rules", p, i + 1, calls)
        for i, p in enumerate(
            [
                Prediction(
                    status="diagnosed",
                    service=case.expected_service,
                    mechanism=case.expected_mechanism,
                    evidence_supported=True,
                ),
                Prediction(status="abstained"),
                Prediction(status="timeout"),
                Prediction(status="excluded"),
            ]
        )
    ]
    m = summarize(trials)
    assert m["root_cause_accuracy"]["numerator"] == 1
    assert m["root_cause_accuracy"]["denominator"] == 3
    assert (m["excluded"], m["abstentions"], m["timeouts"]) == (1, 1, 1)
    assert m["diagnostic_tool_calls"]["count"] == 6
    assert m["estimated_api_cost_usd"]["total"] is None
    assert m["latency_ms"]["p95"] == 3
    assert rate(0, 0)["value"] is None
    assert matched_comparison(trials, "baseline", "llm")["status"] == "UNAVAILABLE"


def test_correct_abstention_is_success_and_unsupported_is_visible():
    case = next(c for c in load("calibration") if c.family == "inconclusive")
    safe = score(case, "baseline", "rules", Prediction(status="abstained"), 1, [])
    guess = score(
        case,
        "baseline",
        "rules",
        Prediction(status="diagnosed", service="checkout-service", mechanism="worker_capacity"),
        2,
        [],
    )
    assert safe.task_success and not safe.unsupported
    assert not guess.task_success and guess.unsupported
    invalid = score(
        case,
        "structured",
        "real",
        Prediction(status="abstained", error_code="UNSUPPORTED_DECISION"),
        1,
        [],
    )
    assert not invalid.task_success
    m = summarize([safe, guess])
    assert m["unsupported_diagnosis_rate"]["value"] == 1
    assert all(g["status"] != "PASS" for g in gates(summarize([])))
    assert aggregate([])["gates"]["security"] == "FAIL"


def test_traces_drop_contents_secrets_and_exception_messages(monkeypatch):
    monkeypatch.setattr(observability, "_provider", None)
    exporter = InMemorySpanExporter()
    observability.configure_tracing(exporter=exporter)
    secret = secrets.token_hex(32)
    with pytest.raises(ValueError), observability.span("test.safe"):
        observability.attributes(
            **{
                "user.input": secret,
                "gen_ai.input.messages": secret,
                "gen_ai.tool.name": secret,
                "opspilot.incident_id": secret,
                "opspilot.mode": "fixture",
            }
        )
        raise ValueError(secret)
    spans = exporter.get_finished_spans()
    with observability.span("test.carrier"):
        assert observability.remote_context(observability.carrier()) is not None
    text = json.dumps(
        [
            {
                "attributes": dict(s.attributes),
                "events": [dict(e.attributes) for e in s.events],
                "status": s.status.description,
            }
            for s in spans
        ]
    )
    assert secret not in text
    assert spans[0].attributes["opspilot.mode"] == "fixture"
    assert spans[0].events[0].attributes == {"exception.type": "ValueError"}
    assert spans[0].status.status_code.name == "ERROR"


def test_trace_context_never_becomes_identity_or_baggage():
    assert observability.remote_context({"traceparent": "not-a-trace", "approved": True}) is None
    assert set(observability.carrier()) <= {"traceparent"}
    with pytest.raises(ValueError):
        observability.LocalJSONExporter("C:/outside-project/secret.jsonl")


def test_release_rejects_missing_models_and_partial_or_mismatched_evidence():
    empty = summarize([])
    diagnostic = {
        "frozen_plan": {
            "source_lock_dataset_sha256": "a",
            "case_ids": [c.id for c in load("held_out")],
        },
        "split": "held_out",
        "metrics": {"llm": empty, "structured": empty},
        "model": {"available": False, "fixture_smoke": False},
        "trials": [],
    }
    operational = {"source_lock_dataset_sha256": "b", "pytest_exit": 0, "metrics": aggregate([])}
    result = assess(diagnostic, operational)
    assert not result["release_ready"] and not result["same_source"]
    assert result["complete_heldout"]
    assert any(g["status"] == "UNAVAILABLE" for g in result["arms"]["structured"]["gates"])
    diagnostic["frozen_plan"]["case_ids"] *= 2
    assert not assess(diagnostic, operational)["complete_heldout"]
