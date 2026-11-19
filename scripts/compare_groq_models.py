"""Read-only comparison client: Groq HTTP, existing MCP and existing investigation graph.

No database engine, fixture activation, reset, approval or remediation executor is
available here. The separate run_stage9c coordinator owns isolated fixture setup.
"""

import asyncio
import hashlib
import json
import os
import re
import time
from datetime import UTC, datetime
from pathlib import Path

import httpx2
from dotenv import dotenv_values
from pydantic import SecretStr

from opspilot.agent.conversation import bind_citation_schema
from opspilot.agent.evidence import parse_response
from opspilot.agent.providers import SYSTEM, HTTPDecisionModel, ModelFailure, strict_schema
from opspilot.agent.schemas import (
    Assessment,
    Contract,
    InvestigationState,
    Observation,
    Recommendation,
    RunRequest,
    ToolCall,
)
from opspilot.agent.workflow import Investigation
from opspilot.gateway.contracts import READ_TOOLS, validate_arguments

ROOT = Path(__file__).resolve().parents[1]
BASE = "https://api.groq.com/openai/v1"
MODELS = ("qwen/qwen3.8-27b", "openai/gpt-oss-20b")
PRICES = {MODELS[0]: (0.8, 4.0), MODELS[1]: (0.075, 0.30)}


def save(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False), encoding="utf-8")


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()


def load_key():
    key = os.environ.get("GROQ_API_KEY") or dotenv_values(ROOT / ".groq.env").get("GROQ_API_KEY")
    if not key or not key.startswith("gsk_"):
        raise ModelFailure("GROQ_KEY_MISSING")
    return SecretStr(key)


def settings(model):
    if model not in MODELS:
        raise ModelFailure("MODEL_NOT_ALLOWLISTED")
    common = {"reasoning_effort": "medium", "temperature": 0.2, "stream": False, "max_tokens": 1600}
    common.update(
        {"reasoning_format": "hidden"} if model == MODELS[0] else {"include_reasoning": False}
    )
    return common


class StrictDiagnosis(Contract):
    """Compose existing models; do not relax any existing diagnosis fields."""

    assessment: Assessment
    recommendation: Recommendation


class Budget:
    def __init__(self, folder, key, *, request_limit=30, cost_limit=0.50, interval=12):
        self.folder, self.key = folder, key
        self.limit, self.cost_limit, self.interval = request_limit, cost_limit, interval
        self.requests, self.accounted_usd = [], 0.0
        self.last_start, self.stopped = 0.0, None

    async def wait(self):
        if self.stopped:
            raise ModelFailure(self.stopped)
        delay = self.interval - (time.monotonic() - self.last_start)
        if delay > 0:
            await asyncio.sleep(delay)

    def reserve(self, body, phase):
        model = body.get("model") if body else None
        if model is not None and model not in MODELS:
            raise ModelFailure("MODEL_NOT_ALLOWLISTED")
        if len(self.requests) >= self.limit:
            self.stopped = "REQUEST_BUDGET_EXHAUSTED"
        estimated = 0.0
        if model:
            if body.get("tools") and body.get("response_format"):
                raise ModelFailure("TOOLS_AND_STRUCTURED_OUTPUT_REJECTED")
            if body.get("tools") and body.get("parallel_tool_calls") is not False:
                raise ModelFailure("PARALLEL_TOOLS_REJECTED")
            # Conservative byte-based input ceiling, including schema/role overhead;
            # missing usage retains this reservation rather than inventing zero cost.
            encoded = len(json.dumps(body, ensure_ascii=False).encode()) + 512
            if encoded > 65000:
                raise ModelFailure("CONTEXT_BUDGET_EXHAUSTED")
            maximum = body.get("max_tokens", 0)
            if not 1 <= maximum <= 1600:
                raise ModelFailure("OUTPUT_BUDGET_REJECTED")
            estimated = (encoded * PRICES[model][0] + maximum * PRICES[model][1]) / 1_000_000
            if self.accounted_usd + estimated > self.cost_limit:
                self.stopped = "COST_BUDGET_EXHAUSTED"
        if self.stopped:
            raise ModelFailure(self.stopped)
        row = {
            "number": len(self.requests) + 1,
            "model": model,
            "phase": phase,
            "http_status": None,
            "reserved_usd": estimated,
            "cost_complete": False,
        }
        if body:
            row.update(
                prompt_sha256=digest(body["messages"]),
                roles=[m["role"] for m in body["messages"]],
                tool_count=len(body.get("tools", [])),
                structured=bool(body.get("response_format")),
                settings={
                    k: body[k]
                    for k in [
                        "reasoning_effort",
                        "reasoning_format",
                        "include_reasoning",
                        "max_tokens",
                        "parallel_tool_calls",
                    ]
                    if k in body
                },
                schema_sha256=digest(body.get("response_format") or body.get("tools")),
            )
        self.accounted_usd += estimated
        self.requests.append(row)
        self.last_start = time.monotonic()
        return row

    async def exchange(self, request, body, phase, actual):
        expected = BASE + ("/chat/completions" if body else "/models")
        if str(request.url) != expected or request.method != ("POST" if body else "GET"):
            raise ModelFailure("PROVIDER_ENDPOINT_REJECTED")
        row = self.reserve(body, phase)
        started = time.monotonic()
        try:
            response = await actual.handle_async_request(request)
            row["http_status"] = response.status_code
            row["quota_headers"] = {
                k: response.headers[k][:100]
                for k in [
                    "retry-after",
                    "x-ratelimit-limit-requests",
                    "x-ratelimit-limit-tokens",
                    "x-ratelimit-remaining-requests",
                    "x-ratelimit-remaining-tokens",
                    "x-ratelimit-reset-requests",
                    "x-ratelimit-reset-tokens",
                ]
                if k in response.headers
            }
            raw = bytearray()
            async for chunk in response.aiter_bytes():
                raw.extend(chunk)
                if len(raw) > 131072:
                    raise ModelFailure("MODEL_RESPONSE_TOO_LARGE")
            await response.aclose()
            value = json.loads(raw)
            if body and response.status_code == 200:
                choice = (value.get("choices") or [{}])[0]
                reason = choice.get("finish_reason")
                row["finish_reason"] = (
                    reason
                    if reason in {"stop", "tool_calls", "length", "content_filter"}
                    else "unknown"
                )
                row["response_model"] = (
                    value.get("model") if value.get("model") in MODELS else "unexpected"
                )
            usage = value.get("usage") or {}
            if all(
                type(usage.get(k)) is int and usage[k] >= 0
                for k in ["prompt_tokens", "completion_tokens"]
            ):
                price = PRICES[body["model"]]
                cost = (
                    usage["prompt_tokens"] * price[0] + usage["completion_tokens"] * price[1]
                ) / 1_000_000
                self.accounted_usd += cost - row["reserved_usd"]
                row.update(
                    input_tokens=usage["prompt_tokens"],
                    output_tokens=usage["completion_tokens"],
                    estimated_usd=cost,
                    cost_complete=True,
                )
            elif body is None:
                row.update(estimated_usd=0, cost_complete=True)
            if response.status_code != 200:
                error = value.get("error", {})
                for name in ["code", "type"]:
                    field = error.get(name)
                    if isinstance(field, str) and re.fullmatch(r"[A-Za-z0-9_-]{1,80}", field):
                        row["provider_error_" + name] = field
                row["error_origin"] = "provider"
                if response.status_code in {401, 403, 429}:
                    self.stopped = "PROVIDER_ACCESS_OR_QUOTA_STOP"
            if self.accounted_usd >= self.cost_limit:
                self.stopped = "COST_BUDGET_EXHAUSTED"
            # Return in-memory bytes to the existing parser. Never persist raw
            # provider content, authentication headers or reasoning fields.
            # aiter_bytes() already decoded compression. Drop stale wire headers.
            headers = {
                k: v
                for k, v in response.headers.items()
                if k.lower() not in {"content-encoding", "content-length", "transfer-encoding"}
            }
            return httpx2.Response(response.status_code, content=bytes(raw), headers=headers)
        except (httpx2.HTTPError, OSError) as exc:
            row.update(error_origin="transport", error_type=type(exc).__name__)
            raise
        finally:
            row["latency_ms"] = round((time.monotonic() - started) * 1000, 3)
            save(self.folder / "requests.json", self.requests)

    async def call(self, body, phase):
        await self.wait()
        async with httpx2.AsyncClient(
            transport=Transport(self, phase),
            trust_env=False,
            timeout=15,
            follow_redirects=False,
        ) as client:
            response = await client.request(
                "POST" if body else "GET",
                BASE + ("/chat/completions" if body else "/models"),
                json=body if body else None,
                headers={"Authorization": "Bearer " + self.key.get_secret_value()},
            )
        if response.status_code != 200:
            raise ModelFailure(
                "MODEL_RATE_LIMITED" if response.status_code == 429 else "MODEL_HTTP_ERROR"
            )
        value = response.json()
        if body is None:
            return value
        choice = value["choices"][0]
        if value.get("model") != body["model"]:
            raise ModelFailure("RESPONSE_MODEL_MISMATCH")
        if choice.get("finish_reason") not in {"stop", "tool_calls"}:
            raise ModelFailure("MODEL_OUTPUT_INCOMPLETE")
        message = choice["message"]
        if message.get("refusal"):
            raise ModelFailure("MODEL_REFUSED")
        content = message.get("content")
        if content and "<think>" in content:
            raise ModelFailure("UNEXPECTED_REASONING_IN_CONTENT")
        return {k: message[k] for k in ["role", "content", "tool_calls"] if k in message}


class Transport(httpx2.AsyncBaseTransport):
    def __init__(self, budget, phase):
        self.budget, self.phase = budget, phase
        self.actual = httpx2.AsyncHTTPTransport(retries=0)

    async def handle_async_request(self, request):
        body = json.loads(request.content) if request.method == "POST" else None
        return await self.budget.exchange(request, body, self.phase, self.actual)

    async def aclose(self):
        await self.actual.aclose()


class ComparisonModel:
    mode, provider = "real", "groq"

    def __init__(self, model, budget):
        self.model, self.budget, self.decisions = model, budget, []
        self.adapter = HTTPDecisionModel(
            "groq",
            model,
            BASE,
            budget.key.get_secret_value(),
            request_interval_seconds=0,
            reasoning_effort="medium",
        )

    async def wait_for_capacity(self):
        await self.budget.wait()

    async def generate(self, stage, context, schema):
        row = {"stage": stage, "received_evidence_ids": [o["id"] for o in context["observations"]]}
        self.decisions.append(row)
        self.adapter.transport = Transport(self.budget, "investigation:" + stage)
        try:
            reply = await self.adapter.generate(stage, context, schema)
            row["output"] = reply.value.model_dump(mode="json")
            row["model_call"] = reply.tool_call.model_dump(mode="json") if reply.tool_call else None
            return reply
        except ModelFailure as exc:
            row["error_code"] = exc.code
            raise


async def collect_packet(mcp, public):
    observations, history = [], []
    for name in [
        "get_incident",
        "get_service_metrics",
        "search_service_logs",
        "get_dependency_status",
        "list_recent_deployments",
    ]:
        args = {"service_name": public.service_name.value}
        if name == "get_incident":
            args.update(incident_id=public.incident_id, event_limit=5)
        elif name != "get_dependency_status":
            args.update(limit=5, offset=0)
        args = validate_arguments(name, args).model_dump(mode="json")
        request_id, data, error = parse_response(name, await mcp.call(name, args), args)
        if error:
            raise ModelFailure("PACKET_TOOL_UNAVAILABLE")
        ref = f"e{len(observations) + 1:03d}"
        observations.append(
            Observation(
                id=ref,
                tool_name=name,
                service_name=public.service_name,
                request_id=request_id,
                data=data,
            )
        )
        history.append(
            ToolCall(
                tool_name=name,
                arguments=args,
                outcome="OK",
                evidence_ref=ref,
                latency_ms=0,
                request_id=request_id,
            )
        )
    return InvestigationState(
        request=RunRequest.model_validate(public.model_dump()),
        incident_id=public.incident_id,
        goal=public.goal,
        mode="real",
        provider="groq",
        model="comparison",
        run_id=__import__("uuid").uuid4(),
        observations=observations,
        tool_call_history=history,
        evidence_references=[o.id for o in observations],
    )


def validate_diagnosis(output, state):
    """Independent checks mirroring the unchanged graph's citation/corroboration gates."""
    packet = StrictDiagnosis.model_validate(output)
    assessment, recommendation = packet.assessment, packet.recommendation
    verifier = Investigation(None, None, state.request)
    for h in assessment.hypotheses:
        verifier._refs(state, h.supporting_evidence)
        verifier._refs(state, h.contradicting_evidence)
        if set(h.supporting_evidence) & set(h.contradicting_evidence):
            raise ValueError("contradictory citation binding")
    if recommendation.status == "abstained":
        if (
            recommendation.root_cause
            or recommendation.proposed_remediation
            or recommendation.evidence_refs
            or assessment.decision != "abstain"
        ):
            raise ValueError("abstention with actionable diagnosis")
        return packet
    cause, proposal = recommendation.root_cause, recommendation.proposed_remediation
    if (
        recommendation.status != "completed"
        or assessment.decision != "propose"
        or not cause
        or not proposal
    ):
        raise ValueError("incomplete final diagnosis")
    hypothesis = next((h for h in assessment.hypotheses if h.id == cause.hypothesis_id), None)
    if (
        not hypothesis
        or hypothesis.contradicting_evidence
        or not set(cause.evidence_refs) <= set(hypothesis.supporting_evidence)
        or not verifier._corroborated(state, cause.evidence_refs)
        or cause.service_name not in verifier.allowed_services
        or cause.confidence > assessment.confidence
        or cause.confidence < 0.6
    ):
        raise ValueError("unsupported root cause")
    verifier._refs(state, proposal.evidence_refs)
    verifier._refs(state, recommendation.evidence_refs)
    if (
        proposal.service_name != cause.service_name
        or not set(proposal.evidence_refs) <= set(cause.evidence_refs)
        or not verifier._corroborated(state, proposal.evidence_refs)
        or set(recommendation.evidence_refs) != set(cause.evidence_refs)
        or (
            proposal.action == "rollback_simulated_configuration"
            and proposal.service_name != "checkout-service"
        )
        or (
            proposal.action == "reset_simulated_dependency"
            and proposal.service_name not in {"payment-service", "inventory-service"}
        )
    ):
        raise ValueError("unsupported remediation")
    return packet


async def probe(budget, model, phase, mcp, state, previous=None):
    row = {
        "model": model,
        "probe": phase,
        "passed": False,
        "started_at": datetime.now(UTC).isoformat(),
    }
    start = time.monotonic()
    body = {"model": model, **settings(model)}
    try:
        if phase == "A":
            body["messages"] = [
                {
                    "role": "user",
                    "content": "Confirm briefly that you can read this text. No tools are needed.",
                }
            ]
        elif phase == "B":
            body["messages"] = [
                {"role": "system", "content": SYSTEM},
                {
                    "role": "user",
                    "content": (
                        "Retrieve checkout-service's latest observed health "
                        "using the one provided read-only tool."
                    ),
                },
            ]
            body.update(
                tools=[
                    {
                        "type": "function",
                        "function": {
                            "name": "get_service_health",
                            "description": "Read service health and quantitative evidence.",
                            "parameters": strict_schema(READ_TOOLS["get_service_health"][0]),
                        },
                    }
                ],
                parallel_tool_calls=False,
                tool_choice={"type": "function", "function": {"name": "get_service_health"}},
            )
        elif phase == "C":
            if not previous or not previous.get("passed"):
                row.update(error_origin="dependency", error_code="NO_VALID_TOOL_CALL")
                return row
            body["messages"] = previous["messages"] + [
                {"role": "assistant", "content": None, "tool_calls": [previous["tool_call"]]},
                {
                    "role": "tool",
                    "tool_call_id": previous["tool_call"]["id"],
                    "name": "get_service_health",
                    "content": json.dumps(previous["tool_result"]),
                },
                {
                    "role": "user",
                    "content": (
                        "Report the returned service, evidence ID, error_rate and "
                        "worker_utilization exactly. Do not infer a root cause."
                    ),
                },
            ]
        else:
            refs = state.evidence_references
            schema = bind_citation_schema(strict_schema(StrictDiagnosis), refs)
            packet = {
                "incident_id": str(state.incident_id),
                "service_name": state.request.service_name.value,
                "observations": [o.model_dump(mode="json") for o in state.observations],
            }
            row["evidence_sha256"] = digest(packet)
            body["messages"] = [
                {"role": "system", "content": SYSTEM},
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "goal": (
                                "Assess evidence, compare alternatives, and return a supported "
                                "final diagnosis/remediation or abstain when inconclusive."
                            ),
                            "required_output_contract": schema,
                            "untrusted_evidence": packet,
                        },
                        separators=(",", ":"),
                    ),
                },
            ]
            body["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": "StrictDiagnosis", "strict": True, "schema": schema},
            }
        message = await budget.call(body, "probe:" + phase)
        if phase in {"A", "C"}:
            content = message.get("content")
            if not isinstance(content, str) or not content.strip() or len(content) > 4000:
                raise ModelFailure("MODEL_EMPTY_OR_OVERSIZED_TEXT")
            row["content"] = content
            if phase == "C":
                observation = previous["tool_result"]["observation"]
                metric = observation["data"].get("metric") or {}
                cited = re.findall(r"\be[0-9]{3}\b", content)
                values = {}
                for name in ["error_rate", "worker_utilization"]:
                    match = re.search(name + r'[\s"`*_:=>]+([-+0-9.eE]+)', content)
                    values[name] = float(match[1]) if match else None
                if (
                    not cited
                    or set(cited) != {observation["id"]}
                    or observation["service_name"] not in content
                    or any(values[k] != metric.get(k) for k in values)
                ):
                    raise ModelFailure("CONTINUATION_EVIDENCE_NOT_ACKNOWLEDGED")
                row["bound_tool_call_id"] = previous["tool_call"]["id"]
        elif phase == "B":
            calls = message.get("tool_calls", [])
            if (
                len(calls) != 1
                or calls[0]["function"]["name"] != "get_service_health"
                or calls[0].get("type") != "function"
                or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", calls[0].get("id", ""))
            ):
                raise ModelFailure("MODEL_TOOL_CALL_INVALID")
            original = calls[0]
            call = {
                "id": original["id"],
                "type": "function",
                "function": {
                    "name": "get_service_health",
                    "arguments": original["function"]["arguments"],
                },
            }
            args = validate_arguments(
                "get_service_health", json.loads(call["function"]["arguments"])
            ).model_dump(mode="json")
            if args != {"service_name": "checkout-service"}:
                raise ModelFailure("MODEL_TOOL_SCOPE_INVALID")
            request_id, data, error = parse_response(
                "get_service_health", await mcp.call("get_service_health", args), args
            )
            if error:
                raise ModelFailure("MCP_TOOL_FAILED")
            row.update(
                messages=body["messages"],
                tool_call=call,
                tool_result={
                    "ok": True,
                    "observation": {
                        "id": "e001",
                        "tool_name": "get_service_health",
                        "service_name": "checkout-service",
                        "request_id": request_id,
                        "data": data,
                        "untrusted_data": True,
                    },
                },
            )
        else:
            parsed = StrictDiagnosis.model_validate_json(message.get("content") or "")
            row["schema_valid"] = True
            row["output"] = parsed.model_dump(mode="json")
            validate_diagnosis(parsed, state)
            row["citations_valid"] = True
            row["supported_status"] = parsed.recommendation.status
        row["passed"] = True
    except ModelFailure as exc:
        row.update(
            error_code=exc.code,
            error_origin="provider"
            if exc.code in {"MODEL_HTTP_ERROR", "MODEL_RATE_LIMITED"}
            else "application",
        )
    except (httpx2.HTTPError, OSError) as exc:
        row.update(error_code=type(exc).__name__, error_origin="transport")
    except Exception as exc:
        row.update(error_code=type(exc).__name__, error_origin="application")
    finally:
        row["latency_ms"] = round((time.monotonic() - start) * 1000, 3)
    return row
