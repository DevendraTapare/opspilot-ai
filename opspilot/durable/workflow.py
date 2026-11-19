"""Persistent deterministic execution graph; resume input never grants approval."""

from contextvars import ContextVar
from typing import TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt
from langsmith import tracing_context
from sqlalchemy.orm import Session

from opspilot.durable.contracts import ExecutionError
from opspilot.durable.policy import check_live_approval
from opspilot.durable.repository import Repository
from opspilot.gateway.contracts import GatewayError
from opspilot.models import ActionExecution
from opspilot.observability import attributes, observed


class DurableState(TypedDict):
    run_id: str
    approval_id: str
    status: str


class DurableExecution:
    def __init__(self, engine, persistence, saver, mcp, crash_hook=None):
        self.repo = Repository(engine)
        self.persistence, self.saver, self.mcp = persistence, saver, mcp
        # Test-only injection of a callable; no environment, CLI or MCP crash controls.
        self.crash_hook = crash_hook or (lambda _: None)
        self.lock_connection = ContextVar("durable_run_lock", default=None)
        self.graph = self._compile()

    async def _guard(self, state):
        connection = self.lock_connection.get()
        if not connection or connection.closed:
            raise ExecutionError("RUN_LOCK_LOST")
        await connection.execute("SELECT 1")
        request = self.repo.request(state["run_id"])
        if request.id != state["approval_id"]:
            raise ExecutionError("CHECKPOINT_BINDING_MISMATCH")
        return request

    async def await_approval(self, state):
        request = await self._guard(state)
        # This return value is deliberately discarded, including {'approved': True}.
        interrupt(
            {
                "kind": "human_approval_required",
                "approval_id": request.id,
                "run_id": request.run_id,
                "fingerprint": request.fingerprint,
            }
        )
        self._require_permission(request.run_id)
        return {"status": "executing"}

    def _require_permission(self, run_id):
        with Session(self.repo.engine) as session:
            request = self.repo._request(session, run_id)
            execution = session.get(ActionExecution, request.arguments["request_id"])
            if execution:
                if execution.approval_id != request.id:
                    raise ExecutionError("EXECUTION_BINDING_MISMATCH")
                return
            check_live_approval(session, request)

    async def _status(self, request):
        try:
            value = await self.mcp.call("get_action_execution", request.arguments)
            if value["ok"]:
                return value["data"]
            self.repo.event(
                request.run_id, "reconciliation_error", {"code": value["error"]["code"]}
            )
        except Exception:
            self.repo.event(request.run_id, "reconciliation_unavailable")
        return None

    def _committed(self, request, status):
        self.repo.reconcile_attempts(request.run_id, "action")
        self.repo.update(
            request.run_id, status="action_committed", action_result=status["action_result"]
        )
        self.repo.event(
            request.run_id,
            "action_result_reconciled",
            {"request_id": request.arguments["request_id"]},
        )

    async def execute(self, state):
        request = await self._guard(state)
        # Always reconcile before delivering a side effect, even after a pre-send crash.
        status = await self._status(request)
        if status is None:
            self.repo.update(request.run_id, status="awaiting_reconciliation")
            return {"status": "awaiting_reconciliation"}
        if status["committed"]:
            self._committed(request, status)
            return {"status": "action_committed"}
        try:
            self._require_permission(request.run_id)
        except (GatewayError, ExecutionError):
            self.repo.update(request.run_id, status="blocked")
            self.repo.event(request.run_id, "action_policy_rejected")
            return {"status": "blocked"}
        if self.repo.attempt_count(request.run_id, "action") >= 3:
            self.repo.update(request.run_id, status="inconclusive")
            return {"status": "inconclusive"}
        attempt = self.repo.attempt(request.run_id, request.arguments["request_id"], "action")
        self.repo.update(request.run_id, status="executing")
        self.crash_hook("before_tool_execution")
        try:
            value = await self.mcp.call(request.tool, request.arguments)
            self.crash_hook("after_tool_before_acknowledgment")
            if value["ok"]:
                self.repo.finish_attempt(attempt, "acknowledged")
                self.repo.update(
                    request.run_id, status="action_committed", action_result=value["data"]
                )
                return {"status": "action_committed"}
            self.repo.finish_attempt(attempt, value["error"]["code"].lower())
        except Exception:
            self.repo.finish_attempt(attempt, "uncertain")
        status = await self._status(request)
        if status and status["committed"]:
            self._committed(request, status)
            return {"status": "action_committed"}
        # No blind retry. A later resume must first obtain an authoritative ledger read.
        self.repo.update(request.run_id, status="awaiting_reconciliation")
        return {"status": "awaiting_reconciliation"}

    async def verify(self, state):
        request = await self._guard(state)
        status = await self._status(request)
        result = status["verification"] if status else None
        if result is None and status and status["committed"]:
            if self.repo.attempt_count(request.run_id, "verification") >= 3:
                self.repo.update(request.run_id, status="inconclusive")
                return {"status": "inconclusive"}
            attempt = self.repo.attempt(
                request.run_id, request.arguments["request_id"], "verification"
            )
            try:
                value = await self.mcp.call("verify_simulated_remediation", request.arguments)
                self.crash_hook("after_verification_before_acknowledgment")
                if value["ok"]:
                    result = value["data"]
                    self.repo.finish_attempt(attempt, "acknowledged")
                else:
                    self.repo.finish_attempt(attempt, value["error"]["code"].lower())
            except Exception:
                self.repo.finish_attempt(attempt, "uncertain")
            if result is None:
                status = await self._status(request)
                result = status["verification"] if status else None
        if result:
            self.repo.reconcile_attempts(request.run_id, "verification")
            self.repo.update(request.run_id, status=result["outcome"], verification=result)
            self.repo.event(
                request.run_id, "verification_result_recorded", {"outcome": result["outcome"]}
            )
            return {"status": result["outcome"]}
        self.repo.update(request.run_id, status="awaiting_reconciliation")
        return {"status": "awaiting_reconciliation"}

    async def await_reconciliation(self, state):
        await self._guard(state)
        interrupt({"kind": "reconciliation_required", "run_id": state["run_id"]})
        return {"status": "executing"}

    async def finish(self, state):
        await self._guard(state)
        self.repo.event(state["run_id"], "workflow_finished", {"status": state["status"]})
        return {}

    def _compile(self):
        graph = StateGraph(DurableState)
        for name in ["await_approval", "execute", "verify", "await_reconciliation", "finish"]:
            graph.add_node(name, getattr(self, name))
        graph.add_edge(START, "await_approval")
        graph.add_edge("await_approval", "execute")
        graph.add_conditional_edges(
            "execute",
            lambda s: (
                "verify"
                if s["status"] == "action_committed"
                else "await_reconciliation"
                if s["status"] == "awaiting_reconciliation"
                else "finish"
            ),
            ["verify", "await_reconciliation", "finish"],
        )
        graph.add_conditional_edges(
            "verify",
            lambda s: (
                "await_reconciliation" if s["status"] == "awaiting_reconciliation" else "finish"
            ),
            ["await_reconciliation", "finish"],
        )
        graph.add_edge("await_reconciliation", "execute")
        graph.add_edge("finish", END)
        return graph.compile(checkpointer=self.saver)

    @observed("invoke_agent opspilot-durable", operation="invoke_agent")
    async def drive(self, run_id, *, start=False):
        attributes(**{"gen_ai.agent.name": "opspilot-durable", "opspilot.run_id": run_id})
        request = self.repo.request(run_id)
        config = {"configurable": {"thread_id": run_id}, "recursion_limit": 30}
        token = None
        try:
            async with self.persistence.run_lock(run_id) as lock:
                token = self.lock_connection.set(lock)
                snapshot = await self.graph.aget_state(config)
                if start and not snapshot.values:
                    argument = {
                        "run_id": run_id,
                        "approval_id": request.id,
                        "status": "awaiting_approval",
                    }
                elif start:
                    return self.repo.report(run_id)
                else:
                    if not snapshot.values:
                        raise ExecutionError("CHECKPOINT_NOT_FOUND")
                    if not snapshot.next:
                        raise ExecutionError("RUN_TERMINAL")
                    self._require_permission(run_id)
                    self.repo.event(run_id, "resume_requested")
                    self.crash_hook("after_approval")
                    argument = (
                        Command(resume={"wake_up": True})
                        if any(task.interrupts for task in snapshot.tasks)
                        else None
                    )
                with tracing_context(enabled=False):
                    await self.graph.ainvoke(argument, config, durability="sync")
                return self.repo.report(run_id)
        except (GatewayError, ExecutionError) as exc:
            self.repo.event(run_id, "resume_rejected", {"code": exc.code})
            raise
        finally:
            if token is not None:
                self.lock_connection.reset(token)
