"""Deterministic test fixture. No LLM inference occurs in this module.

Fixed diagnostic order and threshold rules exercise the graph and MCP plumbing only.
They are deliberately separate from real provider selection and never a failure fallback.
"""

from opspilot.agent.providers import ModelReply


class FixtureDecisionModel:
    mode = "fixture"
    provider = "deterministic-test-fixture"
    model = "worker-observation-fixture-v1"

    async def generate(self, stage, context, schema):
        observations = context["observations"]
        by_tool = {o["tool_name"]: o for o in observations}
        if stage == "triage":
            value = {
                "summary": "Fixture: compare local capacity with dependency failures.",
                "alternatives": [
                    "Local worker capacity is insufficient.",
                    "A downstream dependency is unavailable.",
                ],
            }
        elif stage == "investigation_planning":
            order = [
                "get_service_metrics",
                "search_service_logs",
                "get_dependency_status",
                "list_recent_deployments",
            ]
            tool = next(name for name in order if name not in by_tool)
            value = {
                "tool_name": tool,
                "service_name": context["service_name"],
                "incident_id": None,
                "limit": 5,
                "query": "",
                "rationale": "Fixed fixture diagnostic order; this is not LLM reasoning.",
            }
        else:
            metric_obs = by_tool.get("get_service_metrics")
            logs = by_tool.get("search_service_logs")
            deps = by_tool.get("get_dependency_status")
            metrics = metric_obs["data"]["items"] if metric_obs else []
            metric = metrics[0] if metrics else {}
            saturated = (
                metric.get("worker_utilization", 0) >= 0.95 and metric.get("error_rate", 0) >= 0.2
            )
            healthy_deps = bool(deps) and all(
                d["status"] == "healthy" for d in deps["data"]["dependencies"]
            )
            refs = [o["id"] for o in [metric_obs, logs, deps] if o]
            supported = saturated and healthy_deps and bool(logs and logs["data"]["items"])
            uncertainty = ["A single simulated measurement window does not prove causality."]
            if stage == "evidence_assessment":
                enough = all(
                    name in by_tool
                    for name in [
                        "get_service_metrics",
                        "search_service_logs",
                        "get_dependency_status",
                        "list_recent_deployments",
                    ]
                )
                value = {
                    "hypotheses": [
                        {
                            "id": "h1",
                            "description": "Checkout worker capacity is saturated.",
                            "supporting_evidence": refs if saturated else [],
                            "contradicting_evidence": [],
                        },
                        {
                            "id": "h2",
                            "description": "A payment or inventory dependency failed.",
                            "supporting_evidence": [],
                            "contradicting_evidence": [deps["id"]] if healthy_deps else [],
                        },
                    ],
                    "decision": ("propose" if supported else "abstain")
                    if enough
                    else "investigate",
                    "justification": "Fixture threshold checks on projected operational evidence.",
                    "confidence": 0.8 if supported else 0.2,
                    "uncertainty": uncertainty,
                }
            elif stage == "root_cause_proposal":
                value = {
                    "hypothesis_id": "h1",
                    "service_name": context["service_name"],
                    "explanation": "Observed worker utilization reaches capacity while checkout "
                    "requests fail; sampled dependency windows are healthy.",
                    "evidence_refs": refs,
                    "confidence": 0.8,
                    "uncertainty": uncertainty,
                }
            elif stage == "remediation_planning":
                value = {
                    "action": "restart_simulated_worker",
                    "service_name": context["service_name"],
                    "rationale": "Propose restarting the simulated saturated checkout worker.",
                    "evidence_refs": refs,
                    "risks": ["In-flight work could be interrupted."],
                    "verification_steps": [
                        "After separate approval and execution, repeat the "
                        "same workload and compare errors and utilization."
                    ],
                    "human_approval_required": True,
                }
            else:
                raise ValueError("unknown fixture stage")
        return ModelReply(schema.model_validate(value))
