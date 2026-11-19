"""Stage 4: immutable approvals, durable runs, attempts, verification and audit."""

import sqlalchemy as sa
from alembic import op

revision = "0003_durable"
down_revision = "0002_gateway"
branch_labels = None
depends_on = None


def col(name, type_, **kwargs):
    return sa.Column(name, type_, **kwargs)


def timestamp(name="created_at", nullable=False):
    return col(name, sa.DateTime(timezone=True), nullable=nullable)


def upgrade():
    op.add_column("action_approvals", col("durable_request_id", sa.String(36)))
    op.add_column("action_approvals", col("durable_fingerprint", sa.String(64)))
    op.create_table(
        "durable_runs",
        col("id", sa.String(36), primary_key=True),
        sa.Column("incident_id", sa.String(36), sa.ForeignKey("incidents.id"), nullable=False),
        sa.Column("service_name", sa.String(40), sa.ForeignKey("services.name"), nullable=False),
        col("investigation", sa.JSON(), nullable=False),
        col("input_digest", sa.String(64), nullable=False),
        sa.Column("recovery_of", sa.String(36), sa.ForeignKey("durable_runs.id")),
        col("status", sa.String(40), nullable=False),
        col("action_result", sa.JSON()),
        col("verification", sa.JSON()),
        timestamp(),
        timestamp("updated_at"),
    )
    op.create_table(
        "remediation_approvals",
        col("id", sa.String(36), primary_key=True),
        sa.Column(
            "run_id", sa.String(36), sa.ForeignKey("durable_runs.id"), nullable=False, unique=True
        ),
        sa.Column("incident_id", sa.String(36), sa.ForeignKey("incidents.id"), nullable=False),
        col("tool", sa.String(50), nullable=False),
        col("arguments", sa.JSON(), nullable=False),
        sa.Column("service_name", sa.String(40), sa.ForeignKey("services.name"), nullable=False),
        col("risk", sa.String(20), nullable=False),
        col("evidence", sa.JSON(), nullable=False),
        col("preconditions", sa.JSON(), nullable=False),
        col("verification_plan", sa.JSON(), nullable=False),
        timestamp("expires_at"),
        col("fingerprint", sa.String(64), nullable=False, unique=True),
        col("state", sa.String(20), nullable=False, server_default="pending"),
        col("approved_by", sa.String(120), server_default=""),
        timestamp("approved_at", True),
        col("revoked_by", sa.String(120)),
        timestamp("revoked_at", True),
        timestamp(),
    )
    op.create_table(
        "durable_attempts",
        col("id", sa.String(36), primary_key=True),
        sa.Column("run_id", sa.String(36), sa.ForeignKey("durable_runs.id"), nullable=False),
        col("request_id", sa.String(36), nullable=False),
        col("kind", sa.String(20), nullable=False),
        col("outcome", sa.String(40), nullable=False),
        timestamp(),
        timestamp("finished_at", True),
    )
    op.create_index("ix_durable_attempts_run_id", "durable_attempts", ["run_id"])
    op.create_table(
        "remediation_verifications",
        sa.Column(
            "request_id",
            sa.String(36),
            sa.ForeignKey("action_executions.request_id"),
            primary_key=True,
        ),
        sa.Column(
            "run_id", sa.String(36), sa.ForeignKey("durable_runs.id"), nullable=False, unique=True
        ),
        col("result", sa.JSON(), nullable=False),
        timestamp(),
    )
    op.create_table(
        "durable_audit_events",
        col("id", sa.Integer(), primary_key=True),
        sa.Column("run_id", sa.String(36), sa.ForeignKey("durable_runs.id"), nullable=False),
        col("actor", sa.String(120), nullable=False),
        col("kind", sa.String(50), nullable=False),
        col("detail", sa.JSON(), nullable=False),
        timestamp(),
    )
    op.create_index("ix_durable_audit_events_run_id", "durable_audit_events", ["run_id"])
    if op.get_bind().dialect.name == "postgresql":
        op.execute("""CREATE FUNCTION protect_remediation_approval() RETURNS trigger
        LANGUAGE plpgsql AS $$ BEGIN
          IF TG_OP = 'DELETE' THEN RAISE EXCEPTION 'immutable approval'; END IF;
          IF (to_jsonb(NEW) - ARRAY['state','approved_by','approved_at','revoked_by','revoked_at'])
             IS DISTINCT FROM
             (to_jsonb(OLD) - ARRAY['state','approved_by','approved_at','revoked_by','revoked_at'])
          THEN RAISE EXCEPTION 'immutable approval binding'; END IF;
          IF NEW.state <> OLD.state AND NOT (
            (OLD.state = 'pending' AND NEW.state IN ('approved','revoked','rejected')) OR
            (OLD.state = 'approved' AND NEW.state IN ('consumed','revoked')))
          THEN RAISE EXCEPTION 'invalid approval transition'; END IF;
          IF OLD.state <> 'pending' AND
             (NEW.approved_by, NEW.approved_at) IS DISTINCT FROM
             (OLD.approved_by, OLD.approved_at)
          THEN RAISE EXCEPTION 'immutable approver'; END IF;
          RETURN NEW;
        END $$""")
        op.execute("""CREATE TRIGGER immutable_remediation_approval BEFORE UPDATE OR DELETE
        ON remediation_approvals FOR EACH ROW EXECUTE FUNCTION protect_remediation_approval()""")
        op.execute("""CREATE FUNCTION protect_durable_audit() RETURNS trigger LANGUAGE plpgsql
        AS $$ BEGIN RAISE EXCEPTION 'append only audit'; END $$""")
        op.execute("""CREATE TRIGGER append_only_durable_audit BEFORE UPDATE OR DELETE
        ON durable_audit_events FOR EACH ROW EXECUTE FUNCTION protect_durable_audit()""")


def downgrade():
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP TRIGGER append_only_durable_audit ON durable_audit_events")
        op.execute("DROP FUNCTION protect_durable_audit()")
        op.execute("DROP TRIGGER immutable_remediation_approval ON remediation_approvals")
        op.execute("DROP FUNCTION protect_remediation_approval()")
    for table in [
        "durable_audit_events",
        "remediation_verifications",
        "durable_attempts",
        "remediation_approvals",
        "durable_runs",
    ]:
        op.drop_table(table)
    op.drop_column("action_approvals", "durable_fingerprint")
    op.drop_column("action_approvals", "durable_request_id")
