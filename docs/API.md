# Stage 1 API contract

Base: `http://127.0.0.1:8084`. Interactive schema: `/docs`; machine-readable schema:
`/openapi.json`. JSON inputs reject unknown fields. All timestamps are UTC.

## Routes

| Method | Path | Authorization | Response |
|---|---|---|---|
| GET | `/health/live` | None | `HealthOut` |
| GET | `/health/ready` | None | `HealthOut`; 503 until DB/schema/fixtures are ready |
| GET | `/api/v1/services` | None | `ServiceOut[]` |
| GET | `/api/v1/scenarios` | None | `ScenarioOut[]` |
| GET | `/api/v1/faults` | None | `FaultOut[]` |
| POST | `/api/v1/faults` | Bearer | `FaultCreate` → `FaultOut`, 201 |
| POST | `/api/v1/faults/{fault_id}/deactivate` | Bearer | No body → `FaultOut`, 200 |
| POST | `/api/v1/fixtures/reset` | Bearer | `ResetRequest` → `ResetOut`, 200 |
| POST | `/api/v1/simulator/{service_name}/workloads` | Bearer | `WorkloadRequest` → `WorkloadOut`, 200 |
| POST | `/api/v1/simulator/{service_name}/request` | Bearer | No body → `WorkloadOut`, simulated status |
| GET | `/api/v1/incidents` | None | `IncidentOut[]` |
| GET | `/api/v1/incidents/{incident_id}` | None | `IncidentDetail` with events |
| GET | `/api/v1/incidents/{incident_id}/metrics` | None | `MetricOut[]` |
| GET | `/api/v1/incidents/{incident_id}/logs` | None | `LogOut[]` |
| GET | `/api/v1/services/{service_name}/metrics` | None | `MetricOut[]` |
| GET | `/api/v1/services/{service_name}/logs` | None | `LogOut[]` |
| GET | `/api/v1/services/{service_name}/deployments` | None | `DeploymentOut[]` |

History collections support `limit` (1–500, default 100) and `offset` (≥0, default 0),
ordered chronologically with an ID tie-breaker. Incidents filter by `service_name`
and `status=open|resolved`. Faults filter by `service_name` and `active=true|false`.
Service names are `checkout-service`, `payment-service`, `inventory-service`.

## Input schemas

`FaultCreate` requires compatible `service_name` and `scenario_id` values from the
catalog. Example:

```json
{"service_name":"payment-service","scenario_id":"payment-unavailable"}
```

`ResetRequest` requires 1–3 unique, explicitly selected service names. Optional
`seed` is a strict integer from 0 to 2147483647, default 42. No data is deleted.

```json
{"services":["payment-service"],"seed":42}
```

`WorkloadRequest` accepts strict integer `count` (1–50, default 12) and
`arrival_interval_ms` (0–100, default 25). Empty `{}` uses these defaults. Maximum
virtual workload duration stays below six seconds under the implemented models.

```json
{"count":30,"arrival_interval_ms":0}
```

## Output schemas

- `ServiceOut`: name, description, seed, cursor, generation.
- `ScenarioOut`: scenario_id, supported services, fixed effect description.
- `FaultOut`: UUID id, service_name, scenario_id, active, created_at, deactivated_at.
- `ResetOut`: scenario_id=`healthy-baseline`, reset_services (`ServiceOut[]`),
  deactivated_fault_ids, resolved_incident_ids. Repeated resets reproduce processing
  values, retain history, and increment only selected generations.
- `WorkloadOut`: run_id, service_name, simulated_window_ms, results, metrics.
  Each result has service_name, request_index, status_code, latency_ms, code.
  Results contain root requests; metrics/logs also include executed dependencies.
- `MetricOut`: id, run_id, service_name, incident_id, fault_id, scenario_id,
  generation, seed, requests, errors, error_rate, avg_latency_ms, p95_latency_ms,
  max_latency_ms, worker_utilization, db_pool_utilization, window_ms, status_counts,
  created_at. Utilization is a ratio from 0 to 1; error_rate is errors/requests.
- `IncidentOut`: id, service_name, status, title, scenario_id, fault_id, opened_at,
  resolved_at. `IncidentDetail` adds events, each with id, incident_id, kind,
  typed observation detail, created_at.
- `LogOut`: id, run_id, service_name, incident_id, fault_id, request_index, level,
  code, status_code, latency_ms, created_at.
- `DeploymentOut`: id, service_name, fault_id, scenario_id, kind, allowlisted config,
  created_at. Deployment changes are simulated, with no external deployment action.

The authoritative field types, nullability, bounds, and examples are generated
from Pydantic v2 models in `opspilot/schemas.py` and exposed in OpenAPI.

## Failure behavior

401: missing/incorrect control token. 404: unknown incident or fault UUID.
409: a service already has an active fault. 422: invalid request, target,
pagination, enum, or UUID. 503: persistence/readiness unavailable. Validation errors
contain location/type and a generic message without reflecting supplied values.
The single-request simulator route additionally emits the simulated 500/502/503
statuses with a normal `WorkloadOut` body so incident evidence remains inspectable.
