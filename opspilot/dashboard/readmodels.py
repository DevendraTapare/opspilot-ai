"""Bounded, positively projected views. Never return fixture answers or provider secrets."""

import json
from pathlib import Path

from fastapi.encoders import jsonable_encoder
from sqlalchemy import select
from sqlalchemy.orm import Session

from opspilot.agent.evidence import INCIDENT_FIELDS, LOG_FIELDS, METRIC_FIELDS
from opspilot.agent.evidence import health as projected_health
from opspilot.durable.policy import effective_state
from opspilot.durable.repository import Repository
from opspilot.gateway.observations import health
from opspilot.models import (
    DashboardRun,
    DurableRun,
    Incident,
    IncidentEvent,
    MetricSummary,
    RemediationApproval,
    Service,
    SimulationLog,
)

ROOT = Path(__file__).resolve().parents[2]


def display_status(session, run):
    if run.status == "awaiting_approval":
        approval = session.scalar(
            select(RemediationApproval).where(RemediationApproval.run_id == run.id)
        )
        if approval:
            state = effective_state(approval)
            if state in {"expired", "revoked"}:
                return "rejected" if state == "revoked" else "expired"
    return run.status


def project(row, fields):
    return jsonable_encoder({name: getattr(row, name) for name in fields})


def incident(row):
    return project(row, INCIDENT_FIELDS)


def services(engine):
    with Session(engine) as session:
        return [
            {
                "name": row.name,
                "description": row.description,
                **projected_health(health(session, row.name).model_dump(mode="json")),
            }
            for row in session.scalars(select(Service).order_by(Service.name))
        ]


def incidents(engine):
    with Session(engine) as session:
        return [
            incident(row)
            for row in session.scalars(
                select(Incident).order_by(Incident.opened_at.desc()).limit(100)
            )
        ]


def incident_detail(engine, identity):
    with Session(engine) as session:
        row = session.get(Incident, identity)
        if not row:
            return None
        metrics = session.scalars(
            select(MetricSummary)
            .where(MetricSummary.service_name == row.service_name)
            .order_by(MetricSummary.created_at.desc())
            .limit(20)
        )
        logs = session.scalars(
            select(SimulationLog)
            .where(SimulationLog.incident_id == row.id)
            .order_by(SimulationLog.created_at.desc())
            .limit(100)
        )
        events = session.scalars(
            select(IncidentEvent)
            .where(IncidentEvent.incident_id == row.id)
            .order_by(IncidentEvent.created_at.desc())
            .limit(50)
        )
        return {
            **incident(row),
            "metrics": [project(m, METRIC_FIELDS) for m in metrics],
            "logs": [project(log, LOG_FIELDS) for log in logs],
            "events": [project(e, {"id", "kind", "created_at"}) for e in events],
            "limits": {"metrics": 20, "logs": 100, "events": 50},
        }


def runs(engine):
    with Session(engine) as session:
        rows = list(
            session.scalars(select(DashboardRun).order_by(DashboardRun.created_at.desc()).limit(50))
        )
        items = [
            project(
                r,
                {
                    "id",
                    "incident_id",
                    "service_name",
                    "mode",
                    "status",
                    "created_at",
                    "updated_at",
                    "error_code",
                },
            )
            for r in rows
        ]
        for item in items:
            durable = session.get(DurableRun, item["id"])
            if durable:
                item["status"] = display_status(session, durable)
        # Older CLI runs remain reviewable alongside dashboard investigations.
        for row in session.scalars(
            select(DurableRun).order_by(DurableRun.created_at.desc()).limit(50)
        ):
            if row.id not in {r["id"] for r in items}:
                items.append(
                    {
                        **project(
                            row,
                            {
                                "id",
                                "incident_id",
                                "service_name",
                                "status",
                                "created_at",
                                "updated_at",
                            },
                        ),
                        "mode": row.investigation["mode"],
                        "status": display_status(session, row),
                    }
                )
        return sorted(items, key=lambda r: r["created_at"], reverse=True)[:50]


def run_detail(engine, identity):
    with Session(engine) as session:
        row = session.get(DashboardRun, identity)
        durable = session.get(DurableRun, identity)
        if not row and not durable:
            return None
        snapshot = row.snapshot if row else durable.investigation
        result = {
            "id": identity,
            "snapshot": snapshot,
            "status": display_status(session, durable) if durable else row.status,
            "error_code": row.error_code if row else None,
            "durable": None,
        }
    if durable:
        result["durable"] = Repository(engine).report(identity, limit=100)
    return result


def approvals(engine):
    with Session(engine) as session:
        identities = list(
            session.scalars(
                select(RemediationApproval.run_id)
                .order_by(RemediationApproval.created_at.desc())
                .limit(50)
            )
        )
    return [Repository(engine).report(identity, limit=100) for identity in identities]


def evaluations():
    # Only aggregate recorded results; held-out answers/trials never leave this endpoint.
    reports = {}
    for name in ("calibration", "development", "held-out"):
        value = json.loads((ROOT / f"evaluations/reports/{name}-final.json").read_text())
        reports[name] = {
            key: value.get(key)
            for key in (
                "dataset_version",
                "split",
                "started_at",
                "finished_at",
                "model",
                "metrics",
                "comparisons",
                "gates",
                "release_ready",
                "excluded_reasons",
            )
        }
    release = json.loads((ROOT / "evaluations/reports/release-final.json").read_text())
    operations = json.loads((ROOT / "evaluations/reports/operational-final.json").read_text())
    return {
        "historical_stage": 5,
        "reports": reports,
        "release": release,
        "operations": {k: operations.get(k) for k in ("metrics", "summary", "environment")},
        "version_comparison": "Only one recorded benchmark version; no superiority claim.",
    }
