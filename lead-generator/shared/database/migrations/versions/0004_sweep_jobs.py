"""sweep_jobs — tabela de persistência de varreduras IA

Revision ID: 0004_sweep_jobs
Revises: 0003_multi_offer
Create Date: 2026-04-29
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0004_sweep_jobs"
down_revision = "0003_multi_offer"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sweep_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("campanha_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("campanha_name", sa.String(255), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="running"),
        sa.Column("total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("analyzed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("compatible", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("insufficient", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("feed", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("operator", sa.String(3), nullable=False, server_default="OR"),
        sa.Column("threshold", sa.Integer(), nullable=False, server_default="70"),
        sa.Column("offers_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["campanha_id"], ["campanhas.id"], ondelete="CASCADE"),
    )
    op.create_index("idx_sweep_jobs_campanha", "sweep_jobs", ["campanha_id"])


def downgrade() -> None:
    op.drop_index("idx_sweep_jobs_campanha", table_name="sweep_jobs")
    op.drop_table("sweep_jobs")
