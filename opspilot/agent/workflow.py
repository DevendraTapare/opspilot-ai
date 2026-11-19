"""Bounded LangGraph investigation, with citations and independent read-only enforcement."""

import asyncio
import time
from datetime import datetime
from uuid import uuid4

from langgraph.graph import END, START, StateGraph
from langsmith import tracing_context
from pydantic import ValidationError

from opspilot.agent.budgets import OUTPUT_RESERVATION, estimate_input_tokens
from opspilot.agent.evidence import arguments_for, parse_response
from opspilot.agent.providers import ModelFailure
from opspilot.agent.schemas import (
    Assessment,
    DiagnosticStep,
    ErrorInfo,
    InvestigationState,
    Observation,
    Recommendation,
    Remediation,
    RootCause,
    RunRequest,
    ToolCall,
    Triage,
)
from opspilot.observability import attributes, observed


class BudgetExceeded(Exception):
    def __init__(self, code="BUDGET_EXHAUSTED"):
        self.code = code


class Investigation:
    """One instance per run; model and MCP client are supplied explicitly."""

    def __init__(
        self,
        model,
        mcp,
        request: RunRequest,
        allowed_services=None,
        run_id=None,
        progress_callback=None,
    ):
        self.model, self.mcp, self.request = model, mcp, request
        self.run_id = run_id or uuid4()
        self.progress_callback = progress_callback
        # Scoped to the target and its known simulator dependencies, not arbitrary resources.
        scope = {request.service_name.value}
        if request.service_name == "checkout-service":
            scope |= {"payment-service", "inventory-service"}
        self.allowed_services = scope if allowed_services is None else scope & set(allowed_services)
        self.started = 0.0
        self.graph = self._compile()

    def _remaining(self):
        remaining = self.request.max_seconds - (time.monotonic() - self.started)
        if remaining <= 0:
            raise BudgetExceeded
        return min(remaining, self.request.call_timeout_seconds)

    async def _bounded(self, operation, timeout, code):
        # The selected deadline, rather than a second clock sample, determines
        # whether cancellation exhausts the total budget. Windows timer rounding
        # can wake just before a separately sampled monotonic cutoff.
        total_budget_limited = timeout < self.request.call_timeout_seconds
        timer = asyncio.timeout(timeout)
        try:
            async with timer:
                return await operation
        except TimeoutError:
            if timer.expired() and total_budget_limited:
                raise BudgetExceeded(code) from None
            raise

    def _context(self, state):
        references = [o.id for o in state.observations]
        bound = [t.evidence_ref for t in state.tool_call_history if t.outcome == "OK"]
        if (
            len(references) != len(set(references))
            or references != state.evidence_references
            or bound != references
            or len(references) > state.request.max_tool_calls
        ):
            raise ValueError("evidence registry integrity rejected")
        return {
            "incident_id": str(state.incident_id),
            "goal": state.goal,
            "service_name": state.request.service_name.value,
            "allowed_services": sorted(self.allowed_services),
            "observations": [o.model_dump(mode="json") for o in state.observations],
            "evidence_registry": [
                {
                    "id": o.id,
                    "tool_name": o.tool_name,
                    "service_name": o.service_name,
                    "request_id": o.request_id,
                }
                for o in state.observations
            ],
            "hypotheses": [h.model_dump(mode="json") for h in state.current_hypotheses],
            "triage": state.triage.model_dump() if state.triage else None,
            "assessment": state.assessment.model_dump() if state.assessment else None,
            "candidate_root_cause": (
                state.candidate_root_cause.model_dump(mode="json")
                if state.candidate_root_cause
                else None
            ),
            "tool_history": [t.model_dump(mode="json") for t in state.tool_call_history],
            "remaining_tool_calls": self.request.max_tool_calls - len(state.tool_call_history),
            "remaining_model_calls": self.request.max_model_calls - state.usage.model_calls,
            "remaining_investigation_rounds": max(
                0,
                self.request.max_investigation_rounds
                - state.transitions.count("evidence_assessment"),
            ),
            "remaining_estimated_tokens": max(
                0, self.request.max_estimated_tokens - state.usage.estimated_token_reservation
            ),
        }

    @observed("agent.decision")
    async def _decide(self, state, stage, schema):
        if state.usage.model_calls >= self.request.max_model_calls:
            raise BudgetExceeded
        self._remaining()
        context = self._context(state)
        if hasattr(self.model, "estimate_request"):
            estimate = self.model.estimate_request(stage, context, schema)
        else:
            estimate = estimate_input_tokens(
                {"stage": stage, "context": context, "schema": schema.model_json_schema()}
            )
        if type(estimate) is not int or estimate < 1:
            raise ValueError("invalid request estimate")
        if estimate > self.request.max_prompt_estimated_tokens:
            raise BudgetExceeded("PROMPT_ESTIMATE_EXHAUSTED")
        reservation = estimate + OUTPUT_RESERVATION
        if (
            state.usage.estimated_token_reservation + reservation
            > self.request.max_estimated_tokens
        ):
            raise BudgetExceeded("TOKEN_ESTIMATE_EXHAUSTED")
        if hasattr(self.model, "wait_for_capacity"):
            # Client-side pacing is charged to the unchanged total investigation
            # budget, separately from the per-request provider timeout.
            remaining = self.request.max_seconds - (time.monotonic() - self.started)
            try:
                async with asyncio.timeout(remaining):
                    await self.model.wait_for_capacity()
            except TimeoutError:
                raise BudgetExceeded from None
        timeout = self._remaining()
        # Reserve before dispatch, retain the reservation even on uncertain failures.
        state.usage.estimated_input_tokens += estimate
        state.usage.estimated_token_reservation += reservation
        state.usage.model_calls += 1
        try:
            reply = await self._bounded(
                self.model.generate(stage, context, schema), timeout, "MODEL_TIMEOUT"
            )
            # Validate even injected provider implementations, not just HTTP adapters.
            value = schema.model_validate(reply.value.model_dump())
            if stage == "investigation_planning":
                call = reply.tool_call
                if call is not None and (
                    call.arguments != value
                    or any(
                        t.model_call and t.model_call.id == call.id for t in state.tool_call_history
                    )
                ):
                    raise ValueError("model function identity or arguments rejected")
                state.proposed_model_call = call
            if reply.input_tokens is None or reply.output_tokens is None:
                state.usage.usage_complete = False
            state.usage.input_tokens += reply.input_tokens or 0
            state.usage.output_tokens += reply.output_tokens or 0
            return value
        except Exception:
            state.usage.usage_complete = False
            raise

    @observed("agent.diagnostic")
    async def _read(self, state, step):
        if len(state.tool_call_history) >= self.request.max_tool_calls:
            raise BudgetExceeded
        args = arguments_for(step, str(state.incident_id), self.allowed_services)
        if any(
            t.tool_name == step.tool_name and t.arguments == args for t in state.tool_call_history
        ):
            raise ValueError("duplicate diagnostic rejected")
        timeout = self._remaining()
        started = time.monotonic()
        record = ToolCall(
            tool_name=step.tool_name,
            arguments=args,
            outcome="TOOL_UNAVAILABLE",
            latency_ms=0,
            model_call=state.proposed_model_call,
        )
        state.tool_call_history.append(record)
        try:
            response = await self._bounded(
                self.mcp.call(step.tool_name, args), timeout, "TOOL_TIMEOUT"
            )
            request_id, data, error = parse_response(step.tool_name, response, args)
            record.request_id = request_id
            if error:
                record.outcome = error
                state.errors.append(
                    ErrorInfo(
                        node="readonly_mcp_execution",
                        code=error,
                        message="Diagnostic tool returned an error.",
                    )
                )
                return False
            ref = f"e{len(state.observations) + 1:03d}"
            state.observations.append(
                Observation(
                    id=ref,
                    tool_name=step.tool_name,
                    service_name=step.service_name,
                    request_id=request_id,
                    data=data,
                )
            )
            state.evidence_references.append(ref)
            record.outcome, record.evidence_ref = "OK", ref
            return True
        except BudgetExceeded:
            record.outcome = "TOOL_TIMEOUT"
            raise
        except TimeoutError:
            record.outcome = "TOOL_TIMEOUT"
            if time.monotonic() - self.started >= self.request.max_seconds:
                raise BudgetExceeded from None
            state.errors.append(
                ErrorInfo(
                    node="readonly_mcp_execution",
                    code="TOOL_TIMEOUT",
                    message="Diagnostic tool timed out.",
                )
            )
            return False
        except (ValueError, ValidationError):
            record.outcome = "TOOL_RESPONSE_INVALID"
            state.errors.append(
                ErrorInfo(
                    node="readonly_mcp_execution",
                    code="TOOL_RESPONSE_INVALID",
                    message="Diagnostic response was rejected.",
                )
            )
            return False
        except Exception:
            state.errors.append(
                ErrorInfo(
                    node="readonly_mcp_execution",
                    code="TOOL_UNAVAILABLE",
                    message="Diagnostic tool was unavailable.",
                )
            )
            return False
        finally:
            record.latency_ms = round((time.monotonic() - started) * 1000, 3)

    def _refs(self, state, refs):
        if len(refs) != len(set(refs)) or not set(refs) <= set(state.evidence_references):
            raise ValueError("unknown or repeated evidence citation")

    def _corroborated(self, state, refs):
        self._refs(state, refs)
        observations = [o for o in state.observations if o.id in refs]
        # Empty pages and pre-incident metrics cannot corroborate a diagnosis.
        incident = state.observations[0].data["incident"]
        opened = datetime.fromisoformat(incident["opened_at"])
        quantitative, independent = False, False
        for observation in observations:
            data, tool = observation.data, observation.tool_name
            if tool in {"get_service_metrics", "get_service_health"}:
                metrics = (
                    data.get("items", [])
                    if tool == "get_service_metrics"
                    else ([data["metric"]] if data.get("metric") else [])
                )
                quantitative |= any(
                    datetime.fromisoformat(m["created_at"]) >= opened and m["requests"] > 0
                    for m in metrics
                )
            elif tool == "get_dependency_status":
                independent |= bool(data["dependencies"]) and all(
                    d.get("metric") and datetime.fromisoformat(d["metric"]["created_at"]) >= opened
                    for d in data["dependencies"]
                )
            elif tool == "search_service_logs":
                independent |= any(
                    datetime.fromisoformat(log["created_at"]) >= opened for log in data["items"]
                )
            elif tool == "list_recent_deployments":
                independent |= any(d["configuration"] for d in data["items"])
        return quantitative and independent

    async def triage(self, state):
        found = await self._read(
            state,
            DiagnosticStep(
                tool_name="get_incident",
                service_name=state.request.service_name,
                incident_id=state.incident_id,
                rationale="Establish the requested incident without privileged fixture metadata.",
            ),
        )
        if not found:
            state.run_status = "failed"
            return
        incident = state.observations[0].data["incident"]
        if incident["id"] != str(state.incident_id) or (
            incident["service_name"] != state.request.service_name
        ):
            raise ValueError("incident scope mismatch")
        state.triage = await self._decide(state, "triage", Triage)

    async def investigation_planning(self, state):
        if len(state.tool_call_history) >= self.request.max_tool_calls:
            raise BudgetExceeded
        step = await self._decide(state, "investigation_planning", DiagnosticStep)
        arguments_for(step, str(state.incident_id), self.allowed_services)
        state.proposed_next_diagnostic_step = step

    async def readonly_mcp_execution(self, state):
        await self._read(state, state.proposed_next_diagnostic_step)
        state.proposed_next_diagnostic_step = None
        state.proposed_model_call = None

    async def evidence_assessment(self, state):
        assessment = await self._decide(state, "evidence_assessment", Assessment)
        for h in assessment.hypotheses:
            self._refs(state, h.supporting_evidence)
            self._refs(state, h.contradicting_evidence)
            if set(h.supporting_evidence) & set(h.contradicting_evidence):
                raise ValueError("same evidence cannot both support and contradict a hypothesis")
        state.assessment = assessment
        state.current_hypotheses = assessment.hypotheses
        state.confidence, state.uncertainty = assessment.confidence, assessment.uncertainty
        if assessment.decision == "abstain":
            state.run_status = "abstained"

    async def additional_investigation(self, state):
        if state.transitions.count("evidence_assessment") >= self.request.max_investigation_rounds:
            raise BudgetExceeded("INVESTIGATION_ROUND_LIMIT")
        # Another diagnostic needs planning + assessment; preserve two calls for
        # an independently validated cause/proposal. Never force either output.
        if self.request.max_model_calls - state.usage.model_calls < 4:
            raise BudgetExceeded("FINALIZATION_RESERVE_EXHAUSTED")
        if len(state.tool_call_history) >= self.request.max_tool_calls:
            raise BudgetExceeded
        self._remaining()

    async def root_cause_proposal(self, state):
        cause = await self._decide(state, "root_cause_proposal", RootCause)
        hypothesis = next(
            (h for h in state.current_hypotheses if h.id == cause.hypothesis_id), None
        )
        if (
            hypothesis is None
            or hypothesis.contradicting_evidence
            or not set(cause.evidence_refs) <= set(hypothesis.supporting_evidence)
            or not self._corroborated(state, cause.evidence_refs)
            or cause.service_name not in self.allowed_services
            or cause.confidence > state.confidence
            or cause.confidence < 0.6
        ):
            state.run_status = "abstained"
            state.uncertainty.append("Proposed cause failed evidence and confidence checks.")
            return
        state.candidate_root_cause = cause
        state.confidence, state.uncertainty = cause.confidence, cause.uncertainty

    async def remediation_planning(self, state):
        proposal = await self._decide(state, "remediation_planning", Remediation)
        cause = state.candidate_root_cause
        self._refs(state, proposal.evidence_refs)
        if (
            proposal.service_name != cause.service_name
            or not set(proposal.evidence_refs) <= set(cause.evidence_refs)
            or not self._corroborated(state, proposal.evidence_refs)
            or (
                proposal.action == "rollback_simulated_configuration"
                and proposal.service_name != "checkout-service"
            )
            or (
                proposal.action == "reset_simulated_dependency"
                and proposal.service_name not in {"payment-service", "inventory-service"}
            )
        ):
            raise ValueError("unsupported remediation proposal")
        state.proposed_remediation = proposal
        state.run_status = "completed"

    async def final_recommendation(self, state):
        if state.run_status == "running":
            state.run_status = "abstained"
        completed = state.run_status == "completed"
        if not completed:
            # Never present a partial diagnosis as a supported actionable recommendation.
            state.candidate_root_cause = None
            state.proposed_remediation = None
            state.confidence = 0
        state.latency_ms = round((time.monotonic() - self.started) * 1000, 3)
        state.recommendation = Recommendation(
            status=state.run_status,
            summary=(
                state.candidate_root_cause.explanation
                if completed
                else "Investigation did not establish a supported actionable diagnosis."
            ),
            root_cause=state.candidate_root_cause,
            proposed_remediation=state.proposed_remediation,
            evidence_refs=(state.candidate_root_cause.evidence_refs if completed else []),
            uncertainty=state.uncertainty,
        )

    def _wrap(self, name):
        @observed("agent.workflow_node")
        async def run(state: InvestigationState):
            attributes(**{"opspilot.node": name, "opspilot.run_id": state.run_id})
            state.transitions.append(name)
            try:
                if name != "final_recommendation":
                    self._remaining()
                await getattr(self, name)(state)
            except BudgetExceeded as exc:
                state.run_status = "budget_exhausted"
                state.uncertainty = ["Investigation budget exhausted before a supported result."]
                state.errors.append(
                    ErrorInfo(
                        node=name,
                        code=exc.code,
                        message="Investigation budget was exhausted.",
                    )
                )
            except (TimeoutError, ModelFailure) as exc:
                timed_out = isinstance(exc, asyncio.TimeoutError)
                state.run_status = (
                    "budget_exhausted"
                    if timed_out and time.monotonic() - self.started >= self.request.max_seconds
                    else "failed"
                )
                state.errors.append(
                    ErrorInfo(
                        node=name,
                        code="MODEL_TIMEOUT" if timed_out else exc.code,
                        message="Model decision failed; no fixture substitution was made.",
                    )
                )
                state.uncertainty = ["A model decision could not be validated or completed."]
            except (ValueError, ValidationError):
                state.run_status = "abstained"
                state.errors.append(
                    ErrorInfo(
                        node=name,
                        code="UNSUPPORTED_DECISION",
                        message="Decision failed validation or grounding.",
                    )
                )
                state.uncertainty = ["A proposed decision failed validation or evidence checks."]
            except Exception:
                state.run_status = "failed"
                state.errors.append(
                    ErrorInfo(
                        node=name,
                        code="INVESTIGATION_ERROR",
                        message="Investigation could not continue.",
                    )
                )
            attributes(**{"opspilot.status": state.run_status})
            if self.progress_callback:
                self.progress_callback(state.model_dump(mode="json"))
            return {key: getattr(state, key) for key in type(state).model_fields}

        return run

    def _compile(self):
        graph = StateGraph(InvestigationState)
        names = [
            "triage",
            "investigation_planning",
            "readonly_mcp_execution",
            "evidence_assessment",
            "additional_investigation",
            "root_cause_proposal",
            "remediation_planning",
            "final_recommendation",
        ]
        for name in names:
            graph.add_node(name, self._wrap(name))
        graph.add_edge(START, "triage")
        normal = {
            "triage": "investigation_planning",
            "investigation_planning": "readonly_mcp_execution",
            "readonly_mcp_execution": "evidence_assessment",
            "additional_investigation": "investigation_planning",
            "root_cause_proposal": "remediation_planning",
        }
        for source, target in normal.items():
            graph.add_conditional_edges(
                source,
                lambda s, t=target: t if s.run_status == "running" else "final_recommendation",
                [target, "final_recommendation"],
            )

        def route_assessment(state):
            if state.run_status != "running":
                return "final_recommendation"
            return (
                "root_cause_proposal"
                if state.assessment.decision == "propose"
                else "additional_investigation"
            )

        graph.add_conditional_edges(
            "evidence_assessment",
            route_assessment,
            ["root_cause_proposal", "additional_investigation", "final_recommendation"],
        )
        graph.add_edge("remediation_planning", "final_recommendation")
        graph.add_edge("final_recommendation", END)
        return graph.compile()

    @observed("invoke_agent opspilot-investigator", operation="invoke_agent")
    async def run(self):
        attributes(
            **{
                "gen_ai.agent.name": "opspilot-investigator",
                "opspilot.mode": self.model.mode,
                "opspilot.incident_id": self.request.incident_id,
            }
        )
        self.started = time.monotonic()
        initial = InvestigationState(
            request=self.request,
            run_id=self.run_id,
            mode=self.model.mode,
            provider=self.model.provider,
            model=self.model.model,
            incident_id=self.request.incident_id,
            goal=self.request.goal,
        )
        # No paid/remote trace service receives evidence, even with ambient tracing enabled.
        with tracing_context(enabled=False):
            result = await self.graph.ainvoke(initial, {"recursion_limit": 100})
        return InvestigationState.model_validate(result)
