"""Stage 2: human-issued action grants, exactly-once executions, and tool audits."""

import sqlalchemy as sa
from alembic import op

revision = "0002_gateway"
down_revision = "0001_stage1"
branch_labels = None
depends_on = None


def binding_columns():
    return [
        sa.Column("subject", sa.String(40), nullable=False),
        sa.Column("action", sa.String(50), nullable=False),
        sa.Column("service_name", sa.String(40), sa.ForeignKey("services.name"), nullable=False),
        sa.Column("fault_id", sa.String(36), sa.ForeignKey("faults.id"), nullable=False),
    ]


def timestamp():
    return sa.Column("created_at", sa.DateTime(timezone=True), nullable=False)


def upgrade():
    op.create_table(
        "action_approvals",
        sa.Column("id", sa.String(36), primary_key=True),
        *binding_columns(),
        sa.Column("approved_by", sa.String(120), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("signature", sa.String(64), nullable=False),
        sa.Column("consumed_by", sa.String(36)),
        timestamp(),
    )
    op.create_table(
        "action_executions",
        sa.Column("request_id", sa.String(36), primary_key=True),
        sa.Column(
            "approval_id",
            sa.String(36),
            sa.ForeignKey("action_approvals.id"),
            nullable=False,
            unique=True,
        ),
        *binding_columns(),
        timestamp(),
    )
    op.create_table(
        "gateway_audit_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("request_id", sa.String(36), nullable=False, unique=True),
        sa.Column("subject", sa.String(40), nullable=False),
        sa.Column("tool", sa.String(50), nullable=False),
        sa.Column("service_name", sa.String(40)),
        sa.Column("outcome", sa.String(40), nullable=False),
        sa.Column("approval_id", sa.String(36)),
        sa.Column("action_request_id", sa.String(36)),
        timestamp(),
    )
    op.create_index("ix_gateway_audit_events_subject", "gateway_audit_events", ["subject"])


def downgrade():
    op.drop_table("gateway_audit_events")
    op.drop_table("action_executions")
    op.drop_table("action_approvals")
