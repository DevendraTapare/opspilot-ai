"""Dashboard progress and revocable authenticated human sessions.

Revision ID: 0004_dashboard
Revises: 0003_durable
"""

import sqlalchemy as sa

from alembic import op

revision = "0004_dashboard"
down_revision = "0003_durable"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "dashboard_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("incident_id", sa.String(36), sa.ForeignKey("incidents.id"), nullable=False),
        sa.Column("service_name", sa.String(40), sa.ForeignKey("services.name"), nullable=False),
        sa.Column("mode", sa.String(16), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column("error_code", sa.String(64)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_dashboard_runs_incident_id", "dashboard_runs", ["incident_id"])
    op.create_table(
        "dashboard_sessions",
        sa.Column("token_sha256", sa.String(64), primary_key=True),
        sa.Column("subject", sa.String(80), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade():
    op.drop_table("dashboard_sessions")
    op.drop_index("ix_dashboard_runs_incident_id", table_name="dashboard_runs")
    op.drop_table("dashboard_runs")
