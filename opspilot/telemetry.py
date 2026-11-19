import math
from collections import Counter
from statistics import mean

from sqlalchemy import select
from sqlalchemy.orm import Session

from opspilot.db import SERVICE_FIXTURES
from opspilot.faults import lock_services
from opspilot.incidents import observe
from opspilot.models import Fault, MetricSummary, SimulationLog, uid
from opspilot.schemas import WorkloadRequest
from opspilot.simulator.engine import FaultState, Fixture, Simulator


def execute_workload(session: Session, service: str, body: WorkloadRequest) -> dict:
    names = list(SERVICE_FIXTURES) if service == "checkout-service" else [service]
    services = lock_services(session, names)
    active_faults = {
        fault.service_name: FaultState(fault.id, fault.scenario_id)
        for fault in session.scalars(
            select(Fault).where(Fault.active.is_(True), Fault.service_name.in_(names))
        )
    }
    simulator = Simulator(
        {
            row.name: Fixture(row.seed, row.cursor, row.generation, active_faults.get(row.name))
            for row in services
        }
    )
    results = simulator.run(service, body.count, body.arrival_interval_ms)
    run_id = uid()
    metrics = []
    for row in services:
        row.cursor = simulator.fixtures[row.name].cursor
        samples = simulator.samples.get(row.name, [])
        if not samples:
            continue
        latency = sorted(sample.latency_ms for sample in samples)
        errors = sum(sample.status_code >= 400 for sample in samples)
        cause = next((sample.fault for sample in samples if sample.fault), None)
        worker_util, db_util = simulator.utilization(row.name)
        metric = MetricSummary(
            id=uid(),
            run_id=run_id,
            service_name=row.name,
            fault_id=cause.id if cause else None,
            scenario_id=cause.scenario_id if cause else "healthy-baseline",
            generation=row.generation,
            seed=row.seed,
            requests=len(samples),
            errors=errors,
            error_rate=errors / len(samples),
            avg_latency_ms=round(mean(latency), 3),
            p95_latency_ms=latency[math.ceil(len(latency) * 0.95) - 1],
            max_latency_ms=max(latency),
            worker_utilization=worker_util,
            db_pool_utilization=db_util,
            window_ms=simulator.window_ms,
            status_counts=dict(Counter(str(sample.status_code) for sample in samples)),
        )
        incident = observe(session, metric)
        metric.incident_id = incident.id if incident else None
        session.add(metric)
        metrics.append(metric)
        session.add_all(
            [
                SimulationLog(
                    run_id=run_id,
                    service_name=row.name,
                    incident_id=metric.incident_id,
                    fault_id=sample.fault.id if sample.fault else None,
                    request_index=sample.request_index,
                    level="ERROR" if sample.status_code >= 400 else "INFO",
                    code=sample.code,
                    status_code=sample.status_code,
                    latency_ms=sample.latency_ms,
                )
                for sample in samples
            ]
        )
    session.flush()
    return {
        "run_id": run_id,
        "service_name": service,
        "simulated_window_ms": simulator.window_ms,
        "results": [
            {
                key: getattr(sample, key)
                for key in ("service_name", "request_index", "status_code", "latency_ms", "code")
            }
            for sample in results
        ],
        "metrics": metrics,
    }
