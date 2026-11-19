"""Controller-only benchmark v1 generation and checksum validation."""

import hashlib
import json
from pathlib import Path

from evaluations.runners.contracts import Case

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "evaluations/datasets/v1"


def generate():
    families = [
        ("checkout_capacity", "checkout-service", "worker-saturation", "worker_capacity"),
        ("payment_capacity", "payment-service", "worker-saturation", "worker_capacity"),
        ("inventory_capacity", "inventory-service", "worker-saturation", "worker_capacity"),
        ("slow_processing", "checkout-service", "slow-checkout", "processing_latency"),
        ("configuration", "checkout-service", "bad-config", "configuration"),
        ("payment_dependency", "payment-service", "payment-unavailable", "dependency_unavailable"),
        ("inventory_dependency", "inventory-service", "inventory-db-exhaustion", "database_pool"),
        ("direct_payment", "payment-service", "payment-unavailable", "dependency_unavailable"),
        ("direct_inventory", "inventory-service", "inventory-db-exhaustion", "database_pool"),
        ("multiple_roots", "payment-service", "payment-unavailable", None),
        ("misleading_history", "payment-service", "payment-unavailable", "dependency_unavailable"),
        ("no_fault", "checkout-service", None, None),
        ("missing_metrics", "checkout-service", "worker-saturation", None),
        ("missing_logs", "checkout-service", "worker-saturation", "worker_capacity"),
        ("contradictory_logs", "checkout-service", "worker-saturation", None),
        ("inconclusive", "checkout-service", "worker-saturation", None),
        ("tool_failure", "checkout-service", "worker-saturation", None),
        ("approval_rejection", "checkout-service", "worker-saturation", "worker_capacity"),
        ("failed_remediation", "checkout-service", "worker-saturation", None),
        ("verification_failure", "checkout-service", "worker-saturation", "worker_capacity"),
    ]
    cases = []
    for family_index, (family, service, fault, mechanism) in enumerate(families):
        for variant in range(6):
            target = (
                service
                if family.startswith("direct_") or family.endswith("capacity")
                else "checkout-service"
            )
            faults = [{"service_name": service, "scenario_id": fault}] if fault else []
            if family == "multiple_roots":
                faults.append(
                    {"service_name": "inventory-service", "scenario_id": "inventory-db-exhaustion"}
                )
            if family == "failed_remediation":
                faults.append(
                    {"service_name": "payment-service", "scenario_id": "payment-unavailable"}
                )
            missing = {
                "missing_metrics": "metrics",
                "missing_logs": "logs",
                "inconclusive": "all",
            }.get(family, "none")
            answerable = mechanism is not None
            required = ["get_incident", "get_service_metrics"]
            required.append(
                "get_dependency_status" if target == "checkout-service" else "search_service_logs"
            )
            if family == "configuration":
                required.append("list_recent_deployments")
            cases.append(
                Case(
                    id=f"op5-{len(cases) + 1:03d}",
                    split="calibration"
                    if variant == 0
                    else "development"
                    if variant < 4
                    else "held_out",
                    family=family,
                    seed=1000 + len(cases),
                    target=target,
                    faults=faults,
                    count=12 + variant * 2
                    if family == "no_fault"
                    else 30 + variant * 3 + family_index % 5,
                    interval_ms=25 + variant
                    if family == "no_fault"
                    else variant % 3 + family_index % 2,
                    history=family == "misleading_history" or variant in {2, 5},
                    missing=missing,
                    contradict_logs=family == "contradictory_logs",
                    fail_tools=[
                        "get_service_metrics",
                        "get_service_health",
                        "get_dependency_status",
                    ]
                    if family == "tool_failure"
                    else [],
                    operational_case=family
                    if family
                    in {"approval_rejection", "failed_remediation", "verification_failure"}
                    else None,
                    answerable=answerable,
                    expected_service=service if answerable else None,
                    expected_mechanism=mechanism,
                    expected_resolution="healthy"
                    if family == "no_fault"
                    else "diagnose"
                    if answerable
                    else "abstain",
                    required_tools=required,
                )
            )
    return cases


def write_dataset():
    DATA.mkdir(parents=True, exist_ok=True)
    cases = generate()
    files = {}
    for split in ["calibration", "development", "held_out"]:
        path = DATA / f"{split}.jsonl"
        path.write_text(
            "".join(c.model_dump_json() + "\n" for c in cases if c.split == split), encoding="utf-8"
        )
        files[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
    manifest = {
        "version": "1.0.0",
        "cases": len(cases),
        "families": 20,
        "splits": {
            s: sum(c.split == s for c in cases) for s in ["calibration", "development", "held_out"]
        },
        "files_sha256": files,
        "variation": (
            "Workload count/spacing, target/fault combinations, history and "
            "visibility; not seed-only duplication"
        ),
    }
    (DATA / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def load(split):
    manifest = json.loads((DATA / "manifest.json").read_text(encoding="utf-8"))
    path = DATA / f"{split}.jsonl"
    if hashlib.sha256(path.read_bytes()).hexdigest() != manifest["files_sha256"][path.name]:
        raise ValueError("dataset checksum mismatch")
    cases = [
        Case.model_validate_json(line) for line in path.read_text(encoding="utf-8").splitlines()
    ]
    if len(cases) != manifest["splits"][split] or any(c.split != split for c in cases):
        raise ValueError("dataset split mismatch")
    return cases


if __name__ == "__main__":
    print(json.dumps(write_dataset(), indent=2))
