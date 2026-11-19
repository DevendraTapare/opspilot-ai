from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from opspilot.models import DeploymentEvent, Fault, Incident, IncidentEvent, Service, now
from opspilot.schemas import FaultCreate, ResetRequest, ScenarioOut, ServiceName

SCENARIOS = [
    ScenarioOut(
        scenario_id="healthy-baseline",
        services=list(ServiceName),
        effect="Reset explicitly selected fixtures; normal worker and connection capacity",
    ),
    ScenarioOut(
        scenario_id="slow-checkout",
        services=[ServiceName.CHECKOUT],
        effect="Adds 550ms of checkout work, occupying workers and increasing queue pressure",
    ),
    ScenarioOut(
        scenario_id="payment-unavailable",
        services=[ServiceName.PAYMENT],
        effect="Payment calls return 503; dependent checkout calls return 502",
    ),
    ScenarioOut(
        scenario_id="inventory-db-exhaustion",
        services=[ServiceName.INVENTORY],
        effect="Four simulated connections are held for 1000ms; pool acquisition times out",
    ),
    ScenarioOut(
        scenario_id="worker-saturation",
        services=list(ServiceName),
        effect="Seven of eight workers are busy for 800ms; queued calls can time out",
    ),
    ScenarioOut(
        scenario_id="bad-config",
        services=[ServiceName.CHECKOUT],
        effect="Deploys an invalid checkout tax mode; checkout processing returns 500",
    ),
]


def lock_services(session: Session, names: list[str]) -> list[Service]:
    # Stable ordering prevents deadlocks between checkout, faults, and multi-fixture resets.
    return list(
        session.scalars(
            select(Service).where(Service.name.in_(names)).order_by(Service.name).with_for_update()
        )
    )


def activate(session: Session, body: FaultCreate) -> Fault:
    lock_services(session, [body.service_name])
    active = session.scalar(
        select(Fault).where(Fault.service_name == body.service_name, Fault.active.is_(True))
    )
    if active:
        raise HTTPException(
            409, "Service already has an active fault; deactivate or reset it first"
        )
    fault = Fault(service_name=body.service_name, scenario_id=body.scenario_id, active=True)
    session.add(fault)
    session.flush()
    if body.scenario_id == "bad-config":
        session.add(
            DeploymentEvent(
                service_name=body.service_name,
                fault_id=fault.id,
                scenario_id=body.scenario_id,
                kind="simulated_config_change",
                config={"tax_mode": "unsupported-v0"},
            )
        )
    return fault


def deactivate(session: Session, fault: Fault) -> None:
    fault.active = False
    fault.deactivated_at = now()
    if fault.scenario_id == "bad-config":
        session.add(
            DeploymentEvent(
                service_name=fault.service_name,
                fault_id=fault.id,
                scenario_id="healthy-baseline",
                kind="simulated_config_rollback",
                config={"tax_mode": "standard-v1"},
            )
        )


def reset(session: Session, body: ResetRequest) -> dict:
    services = lock_services(session, body.services)
    fault_ids, incident_ids = [], []
    for service in services:
        for fault in session.scalars(
            select(Fault).where(Fault.service_name == service.name, Fault.active.is_(True))
        ):
            deactivate(session, fault)
            fault_ids.append(fault.id)
        for incident in session.scalars(
            select(Incident).where(Incident.service_name == service.name, Incident.status == "open")
        ):
            incident.status, incident.resolved_at = "resolved", now()
            incident_ids.append(incident.id)
            session.add(
                IncidentEvent(
                    incident_id=incident.id,
                    kind="fixture_reset",
                    detail={"scenario_id": "healthy-baseline", "seed": body.seed},
                )
            )
        service.seed, service.cursor = body.seed, 0
        service.generation += 1
        session.add(
            DeploymentEvent(
                service_name=service.name,
                scenario_id="healthy-baseline",
                kind="fixture_reset",
                config={"seed": body.seed, "generation": service.generation},
            )
        )
    session.flush()
    return {
        "reset_services": services,
        "deactivated_fault_ids": fault_ids,
        "resolved_incident_ids": incident_ids,
    }
