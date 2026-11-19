"""Discrete event service simulator with dependency calls and finite resource pools.

Virtual milliseconds are replayed by the API as real elapsed wall time. Resource
exhaustion stays inside this model; it cannot exhaust PostgreSQL or host workers.
"""

import hashlib
from collections import defaultdict
from dataclasses import dataclass, field


@dataclass(frozen=True)
class FaultState:
    id: str
    scenario_id: str


@dataclass
class Fixture:
    seed: int
    cursor: int
    generation: int
    fault: FaultState | None = None


@dataclass
class Sample:
    service_name: str
    request_index: int
    status_code: int
    latency_ms: float
    code: str
    arrival_ms: float
    fault: FaultState | None = None

    @property
    def finish_ms(self) -> float:
        return self.arrival_ms + self.latency_ms


@dataclass
class Resources:
    workers: list[float] = field(default_factory=lambda: [0.0] * 8)
    connections: list[float] = field(default_factory=lambda: [0.0] * 4)
    worker_busy_ms: float = 0.0
    db_busy_ms: float = 0.0


class Simulator:
    def __init__(self, fixtures: dict[str, Fixture]):
        self.fixtures = fixtures
        self.samples: dict[str, list[Sample]] = defaultdict(list)
        self.resources = {name: Resources() for name in fixtures}
        for name, fixture in fixtures.items():
            if fixture.fault and fixture.fault.scenario_id == "worker-saturation":
                self.resources[name].workers = [0.0] + [800.0] * 7
            if fixture.fault and fixture.fault.scenario_id == "inventory-db-exhaustion":
                self.resources[name].connections = [1000.0] * 4

    def jitter(self, name: str, index: int) -> int:
        seed = self.fixtures[name].seed
        digest = hashlib.sha256(f"{seed}:{name}:{index}".encode()).digest()
        return 8 + digest[0] % 9

    def call(self, name: str, arrival: float) -> Sample:
        fixture = self.fixtures[name]
        index = fixture.cursor
        fixture.cursor += 1
        resource = self.resources[name]
        lane = min(range(8), key=resource.workers.__getitem__)
        start = max(arrival, resource.workers[lane])
        fault = fixture.fault
        scenario = fault.scenario_id if fault else None

        def finish(status: int, end: float, code: str, cause: FaultState | None = fault):
            sample = Sample(name, index, status, round(end - arrival, 3), code, arrival, cause)
            self.samples[name].append(sample)
            return sample

        if start - arrival > 100:
            return finish(503, arrival + 100, "worker_queue_timeout")

        duration = float(self.jitter(name, index))
        status, code, cause = 200, "ok", fault
        if scenario == "payment-unavailable":
            duration += 40
            status, code = 503, "payment_dependency_unavailable"
        elif scenario == "bad-config":
            duration += 5
            status, code = 500, "invalid_checkout_configuration"
        elif name == "inventory-service":
            connection = min(range(4), key=resource.connections.__getitem__)
            db_start = max(start, resource.connections[connection])
            if db_start - start > 80:
                duration += 80
                status, code = 503, "database_pool_timeout"
            else:
                db_work = 6.0
                duration += db_start - start + db_work
                resource.connections[connection] = db_start + db_work
                resource.db_busy_ms += db_work
        elif name == "checkout-service":
            if scenario == "slow-checkout":
                duration += 550
            # A real dependency graph in the simulation: fail fast on dependency errors.
            for dependency in ("payment-service", "inventory-service"):
                sample = self.call(dependency, start + duration)
                duration += sample.latency_ms
                if sample.status_code >= 400:
                    status, code, cause = 502, "checkout_dependency_failed", sample.fault
                    break

        resource.workers[lane] = start + duration
        resource.worker_busy_ms += duration
        return finish(status, start + duration, code, cause)

    def run(self, service: str, count: int, interval: int) -> list[Sample]:
        return [self.call(service, float(i * interval)) for i in range(count)]

    @property
    def window_ms(self) -> float:
        return max(sample.finish_ms for samples in self.samples.values() for sample in samples)

    def utilization(self, service: str) -> tuple[float, float]:
        resource = self.resources[service]
        fault = self.fixtures[service].fault
        scenario = fault.scenario_id if fault else None
        window = max(self.window_ms, 1)
        worker_busy = resource.worker_busy_ms
        db_busy = resource.db_busy_ms
        if scenario == "worker-saturation":
            worker_busy += 7 * min(800, window)
        if scenario == "inventory-db-exhaustion":
            db_busy += 4 * min(1000, window)
        return round(min(1, worker_busy / (8 * window)), 6), round(
            min(1, db_busy / (4 * window)), 6
        )
