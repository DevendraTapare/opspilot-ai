"""Stage 1 schema and three isolated fictional service fixtures."""

import sqlalchemy as sa
from alembic import op

revision = "0001_stage1"
down_revision = None
branch_labels = None
depends_on = None


def pk():
    return sa.Column("id", sa.String(36), primary_key=True)


def service():
    return sa.Column("service_name", sa.String(40), sa.ForeignKey("services.name"), nullable=False)


def timestamp():
    return sa.Column("created_at", sa.DateTime(timezone=True), nullable=False)


def fk(name, table):
    return sa.Column(name, sa.String(36), sa.ForeignKey(f"{table}.id"), nullable=True)


def upgrade():
    services = op.create_table(
        "services",
        sa.Column("name", sa.String(40), primary_key=True),
        sa.Column("description", sa.String(160), nullable=False),
        sa.Column("seed", sa.Integer, nullable=False),
        sa.Column("cursor", sa.Integer, nullable=False),
        sa.Column("generation", sa.Integer, nullable=False),
    )
    op.create_table(
        "faults",
        pk(),
        service(),
        sa.Column("scenario_id", sa.String(50), nullable=False),
        sa.Column("active", sa.Boolean, nullable=False),
        timestamp(),
        sa.Column("deactivated_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_faults_service_name", "faults", ["service_name"])
    op.create_index(
        "uq_fault_active_service",
        "faults",
        ["service_name"],
        unique=True,
        postgresql_where=sa.text("active = true"),
        sqlite_where=sa.text("active = 1"),
    )
    op.create_table(
        "incidents",
        pk(),
        service(),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("title", sa.String(160), nullable=False),
        sa.Column("scenario_id", sa.String(50)),
        fk("fault_id", "faults"),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_incidents_service_name", "incidents", ["service_name"])
    op.create_index(
        "uq_incident_open_service",
        "incidents",
        ["service_name"],
        unique=True,
        postgresql_where=sa.text("status = 'open'"),
        sqlite_where=sa.text("status = 'open'"),
    )
    op.create_table(
        "incident_events",
        pk(),
        sa.Column("incident_id", sa.String(36), sa.ForeignKey("incidents.id"), nullable=False),
        sa.Column("kind", sa.String(40), nullable=False),
        sa.Column("detail", sa.JSON, nullable=False),
        timestamp(),
    )
    op.create_index("ix_incident_events_incident_id", "incident_events", ["incident_id"])
    op.create_table(
        "deployment_events",
        pk(),
        service(),
        fk("fault_id", "faults"),
        sa.Column("scenario_id", sa.String(50), nullable=False),
        sa.Column("kind", sa.String(40), nullable=False),
        sa.Column("config", sa.JSON, nullable=False),
        timestamp(),
    )
    op.create_index("ix_deployment_events_service_name", "deployment_events", ["service_name"])
    op.create_table(
        "metric_summaries",
        pk(),
        sa.Column("run_id", sa.String(36), nullable=False),
        service(),
        fk("incident_id", "incidents"),
        fk("fault_id", "faults"),
        sa.Column("scenario_id", sa.String(50), nullable=False),
        sa.Column("generation", sa.Integer, nullable=False),
        sa.Column("seed", sa.Integer, nullable=False),
        sa.Column("requests", sa.Integer, nullable=False),
        sa.Column("errors", sa.Integer, nullable=False),
        *[
            sa.Column(name, sa.Float, nullable=False)
            for name in (
                "error_rate",
                "avg_latency_ms",
                "p95_latency_ms",
                "max_latency_ms",
                "worker_utilization",
                "db_pool_utilization",
                "window_ms",
            )
        ],
        sa.Column("status_counts", sa.JSON, nullable=False),
        timestamp(),
    )
    for name in ("run_id", "service_name", "incident_id"):
        op.create_index(f"ix_metric_summaries_{name}", "metric_summaries", [name])
    op.create_table(
        "simulation_logs",
        pk(),
        sa.Column("run_id", sa.String(36), nullable=False),
        service(),
        fk("incident_id", "incidents"),
        fk("fault_id", "faults"),
        sa.Column("request_index", sa.Integer, nullable=False),
        sa.Column("level", sa.String(10), nullable=False),
        sa.Column("code", sa.String(50), nullable=False),
        sa.Column("status_code", sa.Integer, nullable=False),
        sa.Column("latency_ms", sa.Float, nullable=False),
        timestamp(),
    )
    for name in ("run_id", "service_name", "incident_id"):
        op.create_index(f"ix_simulation_logs_{name}", "simulation_logs", [name])
    op.bulk_insert(
        services,
        [
            {
                "name": "checkout-service",
                "description": "Checkout orchestration; depends on payment and inventory",
                "seed": 42,
                "cursor": 0,
                "generation": 0,
            },
            {
                "name": "payment-service",
                "description": "Fictional payment authorization dependency",
                "seed": 42,
                "cursor": 0,
                "generation": 0,
            },
            {
                "name": "inventory-service",
                "description": "Fictional stock reservation with a bounded database pool",
                "seed": 42,
                "cursor": 0,
                "generation": 0,
            },
        ],
    )


def downgrade():
    for table in (
        "simulation_logs",
        "metric_summaries",
        "deployment_events",
        "incident_events",
        "incidents",
        "faults",
        "services",
    ):
        op.drop_table(table)
