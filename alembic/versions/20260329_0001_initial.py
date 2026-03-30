from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20260329_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "copilot_sessions",
        sa.Column("session_id", sa.String(length=64), primary_key=True),
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("user_id", sa.String(length=128), nullable=False),
        sa.Column("machine_id", sa.String(length=128), nullable=False),
        sa.Column("work_order_id", sa.String(length=128), nullable=True),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("state", sa.JSON(), nullable=False),
        sa.Column("last_context_summary", sa.Text(), nullable=True),
    )
    op.create_index(
        "ix_copilot_sessions_tenant_id",
        "copilot_sessions",
        ["tenant_id"],
        unique=False,
    )
    op.create_index(
        "ix_copilot_sessions_machine_id",
        "copilot_sessions",
        ["machine_id"],
        unique=False,
    )

    op.create_table(
        "assets",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("site_id", sa.String(length=128), nullable=False),
        sa.Column("machine_id", sa.String(length=128), nullable=False),
        sa.Column("machine_model", sa.String(length=128), nullable=False),
        sa.Column("machine_family", sa.String(length=128), nullable=True),
        sa.Column("criticality", sa.String(length=16), nullable=False),
        sa.Column("active_manual_version", sa.String(length=64), nullable=True),
        sa.Column("aliases", sa.JSON(), nullable=False),
    )
    op.create_index("ix_assets_tenant_id", "assets", ["tenant_id"], unique=False)
    op.create_index("ix_assets_site_id", "assets", ["site_id"], unique=False)
    op.create_index("ix_assets_machine_id", "assets", ["machine_id"], unique=False)
    op.create_index("ix_assets_machine_model", "assets", ["machine_model"], unique=False)

    op.create_table(
        "manual_model_bindings",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("machine_model", sa.String(length=128), nullable=False),
        sa.Column("machine_family", sa.String(length=128), nullable=True),
        sa.Column("doc_id", sa.String(length=128), nullable=False),
        sa.Column("manual_version", sa.String(length=64), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_manual_model_bindings_tenant_id",
        "manual_model_bindings",
        ["tenant_id"],
        unique=False,
    )
    op.create_index(
        "ix_manual_model_bindings_machine_model",
        "manual_model_bindings",
        ["machine_model"],
        unique=False,
    )

    op.create_table(
        "manual_ingest_jobs",
        sa.Column("job_id", sa.String(length=64), primary_key=True),
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("request_json", sa.JSON(), nullable=False),
        sa.Column("result_json", sa.JSON(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_manual_ingest_jobs_tenant_id",
        "manual_ingest_jobs",
        ["tenant_id"],
        unique=False,
    )
    op.create_index(
        "ix_manual_ingest_jobs_status",
        "manual_ingest_jobs",
        ["status"],
        unique=False,
    )

    op.create_table(
        "work_order_notes",
        sa.Column("note_id", sa.String(length=64), primary_key=True),
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("work_order_id", sa.String(length=128), nullable=False),
        sa.Column("session_id", sa.String(length=64), nullable=True),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_work_order_notes_tenant_id",
        "work_order_notes",
        ["tenant_id"],
        unique=False,
    )
    op.create_index(
        "ix_work_order_notes_work_order_id",
        "work_order_notes",
        ["work_order_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_work_order_notes_work_order_id", table_name="work_order_notes")
    op.drop_index("ix_work_order_notes_tenant_id", table_name="work_order_notes")
    op.drop_table("work_order_notes")

    op.drop_index("ix_manual_ingest_jobs_status", table_name="manual_ingest_jobs")
    op.drop_index("ix_manual_ingest_jobs_tenant_id", table_name="manual_ingest_jobs")
    op.drop_table("manual_ingest_jobs")

    op.drop_index(
        "ix_manual_model_bindings_machine_model",
        table_name="manual_model_bindings",
    )
    op.drop_index(
        "ix_manual_model_bindings_tenant_id",
        table_name="manual_model_bindings",
    )
    op.drop_table("manual_model_bindings")

    op.drop_index("ix_assets_machine_model", table_name="assets")
    op.drop_index("ix_assets_machine_id", table_name="assets")
    op.drop_index("ix_assets_site_id", table_name="assets")
    op.drop_index("ix_assets_tenant_id", table_name="assets")
    op.drop_table("assets")

    op.drop_index("ix_copilot_sessions_machine_id", table_name="copilot_sessions")
    op.drop_index("ix_copilot_sessions_tenant_id", table_name="copilot_sessions")
    op.drop_table("copilot_sessions")
